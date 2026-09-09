"""Hacker News mentions through the Algolia search index.

Free, no key, no account. This is the only source in the layer that is always
available, which makes it the floor: if every other source is unconfigured,
the attention score still has one live reading behind it.

Stories and comments both count. A thread with forty comments about a filing
is more attention than a story nobody replied to, and the question here is
whether people are talking, not whether anyone submitted a link.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from vantage.attention.base import (
    Baseline,
    HttpAttentionSource,
    RateLimiter,
    http_get,
    poisson_baseline,
    query_terms,
    summarize_timestamps,
)
from vantage.domain.attention import AttentionSignal, AttentionSourceName

log = logging.getLogger(__name__)

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"

# Algolia caps a page at 1000 hits on this index and reports nbPages as 1 even
# when nbHits is far larger, so 1000 is the hard ceiling, not a paging step.
_HITS_PER_PAGE = 1000

# hitsPerPage=0 returns nbHits with an empty hit list and, measured against the
# live index, is the only setting where exhaustiveNbHits comes back true: a
# NVIDIA query over 90 days reports 16,487 at hitsPerPage=0 and an estimated
# 16,353 at hitsPerPage=1, because Algolia stops counting once it can fill the
# page.
_COUNT_ONLY = 0

# Algolia publishes 10,000 requests per hour per IP for the HN index. A few
# requests per ticker is nowhere near it, so the pace here is politeness rather
# than a real constraint.
_limiter = RateLimiter(rate_per_second=4.0)


class HackerNewsSource(HttpAttentionSource):
    """Algolia `search_by_date`, one query per search term."""

    @property
    def name(self) -> AttentionSourceName:
        return AttentionSourceName.HACKERNEWS

    def is_configured(self) -> bool:
        return True

    async def _collect(self, ticker: str, company_name: str, window_days: int) -> AttentionSignal:
        now = datetime.now(UTC)
        baseline_cutoff = int((now - timedelta(days=self.baseline_days)).timestamp())
        terms = query_terms(ticker, company_name)

        # Keyed by objectID: "AAPL" and "Apple" hit the same thread constantly
        # and counting it twice would double the apparent attention.
        seen: dict[str, datetime] = {}
        truncated = False

        async with self._http() as client:
            for term in terms:
                payload = await self._search(client, term, baseline_cutoff, _HITS_PER_PAGE)
                hits = payload.get("hits") or []
                if int(payload.get("nbHits") or 0) > len(hits):
                    truncated = True
                for hit in hits:
                    self._record(hit, seen)

            if truncated:
                baseline = await self._counted_baseline(
                    client, terms, now=now, window_days=window_days
                )
            else:
                baseline = summarize_timestamps(
                    list(seen.values()),
                    now=now,
                    window_days=window_days,
                    baseline_days=self.baseline_days,
                )

        # No sentiment: Algolia returns text, not polarity, and inventing a
        # score from an LLM call here would be an unmeasured guess dressed up
        # as data. `net_sentiment` already reports 0.0 for unknown.
        return self.build_signal(ticker, window_days, baseline)

    async def _counted_baseline(
        self,
        client: httpx.AsyncClient,
        terms: list[str],
        *,
        now: datetime,
        window_days: int,
    ) -> Baseline:
        """Baseline from exact totals, for tickers too loud to enumerate.

        Above roughly 1000 mentions in the baseline period the returned hits
        cover only the last few days, which sits inside the window and leaves
        no history to compare against. NVIDIA hit 16,487 mentions over 90 days
        in a live check, so this is the normal path for a megacap, not an edge
        case. Counting instead of enumerating keeps a real z-score there.

        Totals are summed across search terms rather than deduplicated,
        because a count-only response carries no ids to deduplicate on. That
        overstates attention when the ticker and the company name turn up in
        different threads. Overstating attention understates the gap, which is
        the direction `DisclosureGap.is_alertable` is already biased toward.
        """
        window_cutoff = int((now - timedelta(days=window_days)).timestamp())
        baseline_cutoff = int((now - timedelta(days=self.baseline_days)).timestamp())

        window_total = 0
        period_total = 0
        for term in terms:
            in_window = await self._search(client, term, window_cutoff, _COUNT_ONLY)
            in_period = await self._search(client, term, baseline_cutoff, _COUNT_ONLY)
            window_total += int(in_window.get("nbHits") or 0)
            period_total += int(in_period.get("nbHits") or 0)

        # The period total spans the window as well, so the window comes out
        # before the trailing rate is computed.
        older = max(period_total - window_total, 0)
        mean, stdev = poisson_baseline(older, max(self.baseline_days - window_days, 1))
        return Baseline(window_total, mean, stdev)

    @staticmethod
    async def _search(
        client: httpx.AsyncClient,
        term: str,
        since: int,
        hits_per_page: int,
    ) -> dict[str, Any]:
        response = await http_get(
            client,
            SEARCH_URL,
            limiter=_limiter,
            params={
                "query": term,
                "numericFilters": f"created_at_i>{since}",
                "hitsPerPage": hits_per_page,
            },
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return payload

    @staticmethod
    def _record(hit: dict[str, Any], seen: dict[str, datetime]) -> None:
        object_id = str(hit.get("objectID") or "")
        created = hit.get("created_at_i")
        if not object_id or created is None:
            return
        try:
            seen[object_id] = datetime.fromtimestamp(int(created), UTC)
        except (OSError, OverflowError, ValueError):
            log.debug("unparseable created_at_i %r on HN object %s", created, object_id)
