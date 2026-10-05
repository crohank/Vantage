"""Bluesky mentions through `app.bsky.feed.searchPosts`.

Free, but authenticated: the search endpoint rejects anonymous callers, so
BLUESKY_HANDLE and BLUESKY_APP_PASSWORD have to be set. Without them the
source reports itself unconfigured and the scorer leaves it out rather than
counting it as a failure.

Use an app password from the Bluesky settings page, never the account
password. App passwords cannot change the account or read DMs.
"""

from __future__ import annotations

import asyncio
import logging
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

# searchPosts caps `limit` at 100. Ten pages per term matches the ceiling the
# Hacker News source works to, so a truncated read means the same thing on
# both.
_PAGE_SIZE = 100
_MAX_PAGES = 10

# Bluesky's public appview allows 3000 requests per five minutes per IP. Even
# a wide sweep stays far under, so this paces rather than throttles.
_limiter = RateLimiter(rate_per_second=5.0)

# createSession is capped at 300 per account per day, so the session is
# exported once and replayed. The string is loop agnostic, unlike a live
# client, which is why the cache holds the string and not the client.
_session_string: str | None = None


class BlueskySource(AttentionSource):
    """AT Protocol post search over the ticker and the company name."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Both created on first use so they bind to the running loop rather
        # than to whichever loop happened to import this module.
        self._login_lock: asyncio.Lock | None = None
        self._bsky: Any = None

    @property
    def name(self) -> AttentionSourceName:
        return AttentionSourceName.BLUESKY

    def is_configured(self) -> bool:
        return bool(self.settings.bluesky_handle and self.settings.bluesky_app_password)

    async def _client(self) -> Any:
        """Logged in AsyncClient, built once per source instance.

        atproto ships a native AsyncClient whose `search_posts` is a real
        coroutine, so there is no thread to hand this off to.

        Held rather than rebuilt because AsyncClient owns an httpx pool it
        exposes no way to close. Constructing one per fetch would leak a pool
        each time.
        """
        global _session_string

        existing = self._bsky
        if existing is not None:
            return existing

        # Imported here, not at module scope, so a missing or broken atproto
        # degrades this one source instead of breaking the whole package.
        from atproto import AsyncClient

        if self._login_lock is None:
            self._login_lock = asyncio.Lock()

        handle = self.settings.bluesky_handle or ""
        password = self.settings.bluesky_app_password
        secret = password.get_secret_value() if password is not None else ""

        async with self._login_lock:
            # Re-read: a concurrent fetch may have logged in while this one
            # waited for the lock.
            raced = self._bsky
            if raced is not None:
                return raced
            client = AsyncClient()
            if _session_string is not None:
                try:
                    await client.login(session_string=_session_string)
                    self._bsky = client
                    return client
                except Exception as exc:
                    log.info("bluesky session replay failed, logging in fresh: %s", exc)
                    _session_string = None
                    client = AsyncClient()
            await client.login(handle, secret)
            _session_string = str(client.export_session_string())
            self._bsky = client
            return client

    async def _collect(self, ticker: str, company_name: str, window_days: int) -> AttentionSignal:
        now = datetime.now(UTC)
        since = now - timedelta(days=self.baseline_days)
        client = await self._client()

        # Keyed by post URI so a post matching both the ticker and the company
        # name counts once.
        seen: dict[str, datetime] = {}
        truncated = False

        try:
            for term in query_terms(ticker, company_name):
                cursor: str | None = None
                for _ in range(_MAX_PAGES):
                    await _limiter.acquire()
                    params: dict[str, Any] = {
                        "q": term,
                        "limit": _PAGE_SIZE,
                        "since": since.isoformat().replace("+00:00", "Z"),
                        "sort": "latest",
                    }
                    if cursor:
                        params["cursor"] = cursor
                    response = await client.app.bsky.feed.search_posts(params)

                    for post in response.posts or []:
                        self._record(post, now, seen)

                    cursor = getattr(response, "cursor", None)
                    if not cursor:
                        break
                else:
                    # Left the loop with a cursor still outstanding, so older
                    # posts exist that were never read.
                    if cursor:
                        truncated = True
        except Exception:
            # Drop the held client so the next attempt logs in again, rather
            # than replaying a session the server has already rejected.
            self._bsky = None
            raise

        baseline = summarize_timestamps(
            list(seen.values()),
            now=now,
            window_days=window_days,
            baseline_days=self.baseline_days,
            truncated=truncated,
        )
        # No sentiment. AT Protocol returns post text and nothing else, and a
        # made up polarity is worse than an honest absence.
        return self.build_signal(ticker, window_days, baseline)

    @staticmethod
    def _record(post: Any, now: datetime, seen: dict[str, datetime]) -> None:
        uri = str(getattr(post, "uri", "") or "")
        if not uri:
            return
        record = getattr(post, "record", None)
        raw = getattr(record, "created_at", None) or getattr(post, "indexed_at", None)
        if not raw:
            return
        try:
            created = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            log.debug("unparseable bluesky timestamp %r on %s", raw, uri)
            return
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        # record.createdAt is whatever the posting client wrote, so it can sit
        # in the future. A post dated next year would otherwise stretch the
        # baseline window and flatten the mean.
        if created > now + timedelta(days=1):
            return
        seen[uri] = created.astimezone(UTC)
