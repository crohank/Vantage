"""Reddit mentions through PRAW.

Deliberately not load bearing. Reddit closed self-serve API registration in
late 2025 and approval for a new client can simply be refused, so this source
has to be treated as a bonus: when the credentials are absent it reports
itself unconfigured and the scorer drops it, which is different from an error
and leaves `is_degraded` alone.

PRAW is synchronous and does its own blocking HTTP, so every call crosses into
a worker thread.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from vantage.attention.base import (
    AttentionSource,
    RateLimiter,
    query_terms,
    summarize_timestamps,
)
from vantage.domain.attention import AttentionSignal, AttentionSourceName

log = logging.getLogger(__name__)

# Where filing-level discussion actually happens. r/SecurityAnalysis is small
# but is the one place people read the 10-K rather than the headline.
SUBREDDITS = ("stocks", "investing", "wallstreetbets", "SecurityAnalysis")

# Reddit's search listing stops returning new results somewhere around 250
# items regardless of paging, so this is the real ceiling, not a choice.
_RESULT_LIMIT = 250

# OAuth clients get 100 queries per minute averaged over ten minutes. One
# search call can page internally, so this paces the outer calls and PRAW's
# own limiter handles the rest.
_limiter = RateLimiter(rate_per_second=1.0)

# praw.Reddit fetches an OAuth token on construction, so it is built once and
# shared. threading.Lock rather than asyncio.Lock because the only code that
# touches it runs in a worker thread.
_client_lock = threading.Lock()
_client: Any = None


class RedditSource(AttentionSource):
    """Search the investing subreddits for a ticker and a company name."""

    @property
    def name(self) -> AttentionSourceName:
        return AttentionSourceName.REDDIT

    def is_configured(self) -> bool:
        return bool(self.settings.reddit_client_id and self.settings.reddit_client_secret)

    def _reddit(self) -> Any:
        """Shared read-only PRAW client. Runs in a worker thread."""
        global _client

        # Imported here, not at module scope, so a missing or broken praw
        # degrades this one source instead of breaking the whole package.
        import praw

        with _client_lock:
            if _client is None:
                client_id = self.settings.reddit_client_id
                client_secret = self.settings.reddit_client_secret
                _client = praw.Reddit(
                    client_id=client_id.get_secret_value() if client_id else None,
                    client_secret=client_secret.get_secret_value() if client_secret else None,
                    user_agent=self.settings.reddit_user_agent,
                    # PRAW warns when it sees a running event loop. This call
                    # is already inside a worker thread, so the check is a
                    # false positive.
                    check_for_async=False,
                )
                _client.read_only = True
            return _client

    async def _collect(self, ticker: str, company_name: str, window_days: int) -> AttentionSignal:
        now = datetime.now(UTC)
        since = now - timedelta(days=self.baseline_days)

        seen: dict[str, datetime] = {}
        truncated = False

        for term in query_terms(ticker, company_name):
            await _limiter.acquire()
            found, hit_limit = await asyncio.to_thread(self._search, term, since)
            seen.update(found)
            truncated = truncated or hit_limit

        baseline = summarize_timestamps(
            list(seen.values()),
            now=now,
            window_days=window_days,
            baseline_days=self.baseline_days,
            truncated=truncated,
        )
        # No sentiment. Reddit returns text and a vote count, and votes measure
        # agreement with the subreddit, not sentiment about the company.
        return self.build_signal(ticker, window_days, baseline)

    def _search(self, term: str, since: datetime) -> tuple[dict[str, datetime], bool]:
        """Blocking PRAW search. Returns submissions by id and whether the
        listing was cut off at the result limit."""
        reddit = self._reddit()
        # One multireddit query rather than four, which is a quarter of the
        # requests and one shared result limit.
        subreddit = reddit.subreddit("+".join(SUBREDDITS))

        found: dict[str, datetime] = {}
        count = 0
        # time_filter is coarse, so "year" is the narrowest bucket that still
        # covers a 90 day baseline. Anything older is dropped here.
        for submission in subreddit.search(
            term, sort="new", time_filter="year", limit=_RESULT_LIMIT
        ):
            count += 1
            created = getattr(submission, "created_utc", None)
            submission_id = str(getattr(submission, "id", "") or "")
            if created is None or not submission_id:
                continue
            try:
                posted = datetime.fromtimestamp(float(created), UTC)
            except (OSError, OverflowError, ValueError):
                continue
            if posted >= since:
                found[submission_id] = posted
        return found, count >= _RESULT_LIMIT
