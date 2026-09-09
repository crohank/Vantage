"""Press coverage, aggregated from three providers into one NEWS signal.

Roles are not symmetric, because the free tiers are not:

* Google News RSS needs no key and returns roughly 100 headlines with dates.
  It is the reason this source is always configured.
* Finnhub `/company-news` is 60 calls a minute and returns every article in a
  date range with a unix timestamp, which is the best daily history available
  here. It carries no sentiment. Finnhub's sentiment lives on `/news-sentiment`
  which is a premium endpoint, so it is not called.
* Marketaux free is 100 requests a day and three articles a response, so it
  cannot supply daily history. It reports `meta.found` for a period and a
  per entity `sentiment_score`, so it is used for sentiment and only falls
  back to supplying counts when neither timestamp provider returned anything.

One provider failing does not fail the signal. `error` is set only when every
provider that was tried failed, because marking NEWS degraded on a Marketaux
quota blip would trip `is_degraded` and silence alerting across the product
for a reason that has nothing to do with the reading.
"""

from __future__ import annotations

import asyncio
import calendar
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from vantage.attention.base import (
    AttentionSourceError,
    Baseline,
    HttpAttentionSource,
    RateLimiter,
    classify_sentiment,
    http_get,
    poisson_baseline,
    query_terms,
    summarize_timestamps,
)
from vantage.domain.attention import AttentionSignal, AttentionSourceName, Sentiment

log = logging.getLogger(__name__)

FINNHUB_URL = "https://finnhub.io/api/v1/company-news"
MARKETAUX_URL = "https://api.marketaux.com/v1/news/all"
GOOGLE_NEWS_URL = "https://news.google.com/rss/search"

# Free tier is 60 calls a minute.
_finnhub_limiter = RateLimiter(rate_per_second=1.0)
# Free tier is 100 requests a day, which is the binding constraint in this
# whole module. Once spent, acquire() raises and Marketaux drops out while the
# other two keep working.
_marketaux_limiter = RateLimiter(rate_per_second=1.0, max_per_day=100)
# Google publishes no limit for the RSS endpoint, so this is politeness.
_google_news_limiter = RateLimiter(rate_per_second=1.0)

# Marketaux free returns at most three articles per response.
_MARKETAUX_PAGE = 3
# Google News RSS stops at about 100 items whatever the query.
_GOOGLE_NEWS_CAP = 100

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _dedupe_key(title: str, url: str) -> str:
    """Join key for the same story arriving from two providers.

    Has to be the headline, not the URL: Google News rewrites every link to a
    news.google.com redirect, so URLs never match across providers.
    """
    # Google News appends " - Publisher" to every headline.
    stripped = title.rsplit(" - ", 1)[0] if " - " in title else title
    normalized = _NON_ALNUM.sub("", stripped.lower())[:120]
    return normalized or url


@dataclass(frozen=True)
class _ProviderResult:
    provider: str
    # Published time keyed by dedupe key.
    articles: dict[str, datetime] = field(default_factory=dict)
    # Period total when the provider reports one without the articles.
    total_found: int | None = None
    sentiment_scores: tuple[float, ...] = ()
    truncated: bool = False


class NewsSource(HttpAttentionSource):
    """Finnhub, Marketaux and Google News combined into one reading."""

    # Marketaux allows 100 requests a day. Across a 20 ticker watchlist that
    # is five refreshes per ticker per day, so an hour of staleness is already
    # optimistic and the daily cap is what actually stops the bleeding.
    cache_ttl_seconds = 3600.0

    @property
    def name(self) -> AttentionSourceName:
        return AttentionSourceName.NEWS

    def is_configured(self) -> bool:
        # Google News RSS needs no credentials, so this source always has at
        # least one provider it can try.
        return True

    async def _collect(self, ticker: str, company_name: str, window_days: int) -> AttentionSignal:
        now = datetime.now(UTC)
        baseline_start = now - timedelta(days=self.baseline_days)
        window_start = now - timedelta(days=window_days)
        terms = query_terms(ticker, company_name)

        async with self._http() as client:
            tasks: list[Any] = [self._google_news(client, terms, baseline_start)]
            if self.settings.finnhub_api_key is not None:
                tasks.append(self._finnhub(client, ticker, baseline_start, now))
            if self.settings.marketaux_api_key is not None:
                tasks.append(self._marketaux(client, ticker, window_start))

            outcomes = await asyncio.gather(*tasks, return_exceptions=True)

            articles: dict[str, datetime] = {}
            sentiment_scores: list[float] = []
            marketaux_window_total: int | None = None
            truncated = False
            failures: list[str] = []
            succeeded = 0

            for outcome in outcomes:
                if isinstance(outcome, BaseException):
                    failures.append(f"{type(outcome).__name__}: {outcome}")
                    continue
                succeeded += 1
                for key, published in outcome.articles.items():
                    articles.setdefault(key, published)
                sentiment_scores.extend(outcome.sentiment_scores)
                truncated = truncated or outcome.truncated
                if outcome.provider == "marketaux":
                    marketaux_window_total = outcome.total_found

            if succeeded == 0:
                # Every provider tried and every one failed. This is the real
                # degraded case, so let it become error= on the signal.
                raise AttentionSourceError("all news providers failed: " + "; ".join(failures))
            if failures:
                log.warning("news partial failure for %s: %s", ticker, "; ".join(failures))

            baseline = await self._baseline(
                client,
                ticker=ticker,
                now=now,
                window_days=window_days,
                articles=articles,
                truncated=truncated,
                marketaux_window_total=marketaux_window_total,
            )

        return self.build_signal(ticker, window_days, baseline, self._counts(sentiment_scores))

    async def _baseline(
        self,
        client: httpx.AsyncClient,
        *,
        ticker: str,
        now: datetime,
        window_days: int,
        articles: dict[str, datetime],
        truncated: bool,
        marketaux_window_total: int | None,
    ) -> Baseline:
        if articles or not marketaux_window_total:
            return summarize_timestamps(
                list(articles.values()),
                now=now,
                window_days=window_days,
                baseline_days=self.baseline_days,
                truncated=truncated,
            )

        # Marketaux is the only provider with anything to say, so counts have
        # to come from it. That costs a second request, which is why it is not
        # done unless the timestamp providers came back empty.
        baseline_total = marketaux_window_total
        try:
            older = await self._marketaux_count(
                client, ticker, now - timedelta(days=self.baseline_days)
            )
            # meta.found over the baseline period includes the window, so the
            # window has to come out before the trailing rate is computed.
            baseline_total = max(older - marketaux_window_total, 0)
        except Exception as exc:
            log.warning("marketaux baseline count failed for %s: %s", ticker, exc)

        mean, stdev = poisson_baseline(baseline_total, max(self.baseline_days - window_days, 1))
        return Baseline(marketaux_window_total, mean, stdev)

    @staticmethod
    def _counts(scores: list[float]) -> dict[Sentiment, int]:
        """Bucket the polarity scores Marketaux returned.

        The sample is at most three articles on the free tier, so this says
        which way the visible coverage leans and nothing stronger.
        """
        counts: dict[Sentiment, int] = {}
        for score in scores:
            label = classify_sentiment(score)
            counts[label] = counts.get(label, 0) + 1
        return counts

    async def _finnhub(
        self,
        client: httpx.AsyncClient,
        ticker: str,
        start: datetime,
        end: datetime,
    ) -> _ProviderResult:
        key = self.settings.finnhub_api_key
        if key is None:
            return _ProviderResult("finnhub")
        response = await http_get(
            client,
            FINNHUB_URL,
            limiter=_finnhub_limiter,
            params={
                "symbol": ticker,
                "from": start.date().isoformat(),
                "to": end.date().isoformat(),
                "token": key.get_secret_value(),
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise AttentionSourceError(
                f"finnhub returned {type(payload).__name__}, expected a list"
            )

        articles: dict[str, datetime] = {}
        for item in payload:
            stamp = item.get("datetime")
            if not stamp:
                continue
            try:
                published = datetime.fromtimestamp(int(stamp), UTC)
            except (OSError, OverflowError, ValueError):
                continue
            headline = str(item.get("headline") or "")
            url = str(item.get("url") or "")
            articles.setdefault(_dedupe_key(headline, url), published)
        return _ProviderResult("finnhub", articles=articles)

    async def _marketaux(
        self,
        client: httpx.AsyncClient,
        ticker: str,
        published_after: datetime,
    ) -> _ProviderResult:
        key = self.settings.marketaux_api_key
        if key is None:
            return _ProviderResult("marketaux")
        payload = await self._marketaux_call(
            client, ticker, published_after, key.get_secret_value()
        )

        found = int(payload.get("meta", {}).get("found") or 0)
        scores: list[float] = []
        articles: dict[str, datetime] = {}
        for item in payload.get("data") or []:
            for entity in item.get("entities") or []:
                # An article can carry several tickers. Only the score
                # attached to this one is about this company.
                if str(entity.get("symbol") or "").upper() != ticker.upper():
                    continue
                score = entity.get("sentiment_score")
                if score is not None:
                    scores.append(float(score))
            published = _parse_iso(str(item.get("published_at") or ""))
            if published is not None:
                title = str(item.get("title") or "")
                url = str(item.get("url") or "")
                articles.setdefault(_dedupe_key(title, url), published)

        return _ProviderResult(
            "marketaux",
            articles=articles,
            total_found=found,
            sentiment_scores=tuple(scores),
        )

    async def _marketaux_count(
        self,
        client: httpx.AsyncClient,
        ticker: str,
        published_after: datetime,
    ) -> int:
        key = self.settings.marketaux_api_key
        if key is None:
            return 0
        payload = await self._marketaux_call(
            client, ticker, published_after, key.get_secret_value()
        )
        return int(payload.get("meta", {}).get("found") or 0)

    async def _marketaux_call(
        self,
        client: httpx.AsyncClient,
        ticker: str,
        published_after: datetime,
        token: str,
    ) -> dict[str, Any]:
        response = await http_get(
            client,
            MARKETAUX_URL,
            limiter=_marketaux_limiter,
            params={
                "symbols": ticker,
                "filter_entities": "true",
                "language": "en",
                # Marketaux wants minute precision with no offset.
                "published_after": published_after.strftime("%Y-%m-%dT%H:%M"),
                "limit": _MARKETAUX_PAGE,
                "api_token": token,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise AttentionSourceError(
                f"marketaux returned {type(payload).__name__}, expected an object"
            )
        return payload

    async def _google_news(
        self,
        client: httpx.AsyncClient,
        terms: list[str],
        start: datetime,
    ) -> _ProviderResult:
        # Imported here so a feedparser problem cannot take down the package.
        import feedparser

        query = " OR ".join(f'"{term}"' for term in terms)
        response = await http_get(
            client,
            GOOGLE_NEWS_URL,
            limiter=_google_news_limiter,
            params={
                "q": f"{query} after:{start.date().isoformat()}",
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            },
        )
        response.raise_for_status()
        # Parsed from bytes rather than handed the URL: feedparser would fetch
        # it itself with a blocking socket, inside the event loop.
        feed = feedparser.parse(response.content)

        articles: dict[str, datetime] = {}
        entries = list(feed.entries)
        for entry in entries:
            parsed = entry.get("published_parsed")
            if parsed is None:
                continue
            published = datetime.fromtimestamp(calendar.timegm(parsed), UTC)
            title = str(entry.get("title") or "")
            link = str(entry.get("link") or "")
            articles.setdefault(_dedupe_key(title, link), published)

        return _ProviderResult(
            "googlenews",
            articles=articles,
            truncated=len(entries) >= _GOOGLE_NEWS_CAP,
        )


def _parse_iso(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
