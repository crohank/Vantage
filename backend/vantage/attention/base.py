"""Shared plumbing for the attention sources.

Every source answers one question: how much is the public talking about this
ticker right now, against how much it normally does. The comparison is the
whole point. Forty mentions means nothing until you know the ticker usually
draws three.

Two rules hold everywhere:

1. `fetch` never raises. A source that is down returns a signal with `error`
   set, because `AttentionScore.is_degraded` gates alerting and a silent zero
   from a broken source reads as "nobody is talking about it", which is the
   exact wrong conclusion.
2. Every source paces itself and caches. The free tiers are small (Marketaux
   allows 100 requests a day), so an uncached watchlist sweep would spend a
   day's quota in minutes.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import statistics
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple, Self

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from vantage import __version__
from vantage.config import Settings, get_settings
from vantage.domain.attention import AttentionSignal, AttentionSourceName, Sentiment

log = logging.getLogger(__name__)

DEFAULT_WINDOW_DAYS = 7
# Long enough that an earnings cycle sits inside the baseline rather than
# defining it.
DEFAULT_BASELINE_DAYS = 90

USER_AGENT = f"vantage/{__version__}"

_SECONDS_PER_DAY = 86_400


class AttentionSourceError(RuntimeError):
    """Base for failures a source converts into `error=` on the signal."""


class QuotaExhausted(AttentionSourceError):
    """The provider's daily allowance is spent. Retrying today will not help."""


class TransientHttpError(AttentionSourceError):
    """A status worth retrying: 429 or a 5xx."""


def _utc_day() -> date:
    return datetime.now(UTC).date()


class RateLimiter:
    """Token bucket with an optional daily cap.

    Mirrors `vantage.ingest.edgar.RateLimiter` (pace before the request, not
    after, so concurrent callers are actually bounded) and adds the daily
    counter the news tiers need: Marketaux free is 100 requests a day, which
    a per second rate does not express.

    One instance per provider, held at module level, because the limits are
    per API key and per IP rather than per object.
    """

    def __init__(self, rate_per_second: float, max_per_day: int | None = None) -> None:
        self._min_interval = 1.0 / rate_per_second
        self._max_per_day = max_per_day
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0
        self._day = _utc_day()
        self._spent = 0

    async def acquire(self) -> None:
        async with self._lock:
            today = _utc_day()
            if today != self._day:
                self._day = today
                self._spent = 0
            if self._max_per_day is not None and self._spent >= self._max_per_day:
                raise QuotaExhausted(f"daily cap of {self._max_per_day} requests reached")
            # Reserved before the sleep, so two concurrent callers cannot both
            # take the last slot.
            self._spent += 1

            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_allowed = now + self._min_interval

    @property
    def spent_today(self) -> int:
        return self._spent


CacheKey = tuple[str, str, int]


class TTLCache:
    """In-memory signal cache, one per source.

    Successes and failures get different lifetimes. Caching a failure at all
    stops a dead provider from being hit once per finding. Caching it as long
    as a success would keep the source dark for the full TTL after one blip.
    """

    def __init__(self, ttl_seconds: float, error_ttl_seconds: float = 60.0) -> None:
        self._ttl = ttl_seconds
        self._error_ttl = error_ttl_seconds
        self._entries: dict[CacheKey, tuple[float, AttentionSignal]] = {}

    def get(self, key: CacheKey) -> AttentionSignal | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, signal = entry
        if time.monotonic() >= expires_at:
            del self._entries[key]
            return None
        return signal

    def set(self, key: CacheKey, signal: AttentionSignal) -> None:
        ttl = self._ttl if signal.available else self._error_ttl
        self._entries[key] = (time.monotonic() + ttl, signal)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


class Baseline(NamedTuple):
    mention_count: int
    daily_mean: float
    daily_stdev: float


def poisson_baseline(total: int, days: int) -> tuple[float, float]:
    """Mean and stdev when only a period total is known, with no daily detail.

    Marketaux reports `meta.found` for a period but caps the article list at
    three per request on the free tier, so per day counts cannot be recovered
    at any sane quota cost. Counts of independent arrivals are Poisson, where
    the variance equals the mean, which is the least assuming estimate
    available from a single number.

    It does understate the spread. Real chatter is bursty and clusters on
    weekdays and news events, so the true daily variance runs above the mean
    and any z-score derived from this path is larger in magnitude than one
    measured from actual daily counts. Prefer `summarize_timestamps` wherever
    the provider will hand over timestamps.
    """
    mean = total / days if days > 0 else 0.0
    return mean, math.sqrt(mean)


def summarize_timestamps(
    timestamps: Sequence[datetime],
    *,
    now: datetime,
    window_days: int,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    truncated: bool = False,
) -> Baseline:
    """Turn raw mention times into a window count and a trailing baseline.

    The baseline stops at the start of the window. Letting the window feed its
    own baseline damps exactly the spike this score exists to find.

    `truncated` says the caller hit a provider result cap. Every source here
    returns newest first, so a cap drops the oldest days, and treating those
    missing days as zero would drag the mean down and manufacture a spike. The
    baseline is clipped to the span actually observed instead.
    """
    window_start = now - timedelta(days=window_days)
    mention_count = sum(1 for ts in timestamps if ts >= window_start)

    baseline_start = now - timedelta(days=baseline_days)
    if truncated and timestamps:
        baseline_start = max(baseline_start, min(timestamps))

    covered_days = int((window_start - baseline_start).total_seconds() // _SECONDS_PER_DAY)
    if covered_days < 2:
        # statistics.stdev needs two points, and one day of history is not a
        # baseline anyway. Reporting the window's own rate puts the z-score
        # near zero, which says "cannot tell" rather than "spike".
        rate = mention_count / window_days if window_days > 0 else 0.0
        return Baseline(mention_count, rate, math.sqrt(rate))

    # Buckets are rolling 24 hour periods anchored on `now`, not calendar days,
    # so a partial first or last day cannot skew the mean.
    counts = [0] * covered_days
    for ts in timestamps:
        if ts < baseline_start or ts >= window_start:
            continue
        index = int((ts - baseline_start).total_seconds() // _SECONDS_PER_DAY)
        if 0 <= index < covered_days:
            counts[index] += 1

    # Quiet days are real zeros and stay in the sample. Averaging only the days
    # that had a mention would make every dormant ticker look busy.
    return Baseline(mention_count, statistics.fmean(counts), statistics.stdev(counts))


def classify_sentiment(score: float, deadband: float = 0.15) -> Sentiment:
    """Map a provider's [-1, 1] polarity onto the domain enum.

    The deadband is a choice, not a measurement. Provider scores cluster near
    zero and without it almost everything lands in positive or negative on
    rounding noise.
    """
    if score > deadband:
        return Sentiment.POSITIVE
    if score < -deadband:
        return Sentiment.NEGATIVE
    return Sentiment.NEUTRAL


# Legal form and generic tail words, stripped so "NVIDIA CORP" searches as
# "NVIDIA". EDGAR names carry the suffix, humans never type it.
_CORPORATE_TAIL = re.compile(
    r"\b(?:inc|incorporated|corp|corporation|co|company|companies|ltd|limited|"
    r"llc|l\.?l\.?c|lp|plc|holdings?|group|the|s\.?a|n\.?v|a\.?g|s\.?e|ab|oyj|"
    r"class\s+[abc])\b\.?",
    re.IGNORECASE,
)
_PUNCTUATION = re.compile(r"[^\w\s&]+")

# One and two character tickers ("A", "IT", "ALL", "ON") are also ordinary
# words, and free text search on them returns almost entirely noise.
_MIN_TICKER_LENGTH = 3


def normalize_company_name(name: str) -> str:
    """Strip the legal form so the name matches how people write it.

    Falls back to the original when stripping leaves nothing usable, which
    happens for names built entirely from generic words.
    """
    cleaned = _PUNCTUATION.sub(" ", _CORPORATE_TAIL.sub(" ", name))
    collapsed = " ".join(cleaned.split())
    return collapsed if len(collapsed) >= 3 else " ".join(name.split())


def query_terms(ticker: str, company_name: str) -> list[str]:
    """Search terms for one company, most specific first, deduplicated."""
    terms: list[str] = []
    normalized = normalize_company_name(company_name)
    if normalized:
        terms.append(normalized)
    symbol = ticker.strip().upper()
    if len(symbol) >= _MIN_TICKER_LENGTH and symbol.lower() != normalized.lower():
        terms.append(symbol)
    if not terms and symbol:
        # No usable name and a short ticker. A noisy query beats no query,
        # since the alternative is reporting a false zero.
        terms.append(symbol)
    return terms


class AttentionSource(ABC):
    """One place the public might be talking about a ticker.

    Subclasses implement `_collect`. `fetch` wraps it with the cache and the
    never raises guarantee, so that contract is enforced in one place instead
    of being re-argued in every source.
    """

    cache_ttl_seconds: float = 900.0
    error_cache_ttl_seconds: float = 60.0
    baseline_days: int = DEFAULT_BASELINE_DAYS

    def __init__(self, settings: Settings | None = None, *, cache: TTLCache | None = None) -> None:
        self.settings = settings if settings is not None else get_settings()
        self.cache = (
            cache
            if cache is not None
            else TTLCache(self.cache_ttl_seconds, self.error_cache_ttl_seconds)
        )

    @property
    @abstractmethod
    def name(self) -> AttentionSourceName:
        """Which source this is, for the signal and for logging."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Whether the credentials this source needs are present in Settings."""

    @abstractmethod
    async def _collect(self, ticker: str, company_name: str, window_days: int) -> AttentionSignal:
        """Do the real work. Free to raise, `fetch` converts it."""

    async def fetch(
        self,
        ticker: str,
        company_name: str,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> AttentionSignal:
        symbol = ticker.strip().upper()
        if not self.is_configured():
            # Not cached. Re-checking costs nothing and the answer flips the
            # moment a key lands in the environment.
            return self.error_signal(symbol, window_days, "source is not configured")

        key: CacheKey = (symbol, company_name.strip().lower(), window_days)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        try:
            signal = await self._collect(symbol, company_name, window_days)
        except Exception as exc:
            log.warning("%s attention fetch failed for %s: %s", self.name.value, symbol, exc)
            signal = self.error_signal(symbol, window_days, f"{type(exc).__name__}: {exc}")

        self.cache.set(key, signal)
        return signal

    def error_signal(self, ticker: str, window_days: int, message: str) -> AttentionSignal:
        return AttentionSignal(
            source=self.name,
            ticker=ticker,
            window_days=window_days,
            mention_count=0,
            baseline_daily_mean=0.0,
            baseline_daily_stdev=0.0,
            error=message,
        )

    def build_signal(
        self,
        ticker: str,
        window_days: int,
        baseline: Baseline,
        sentiment_counts: dict[Sentiment, int] | None = None,
    ) -> AttentionSignal:
        return AttentionSignal(
            source=self.name,
            ticker=ticker,
            window_days=window_days,
            mention_count=baseline.mention_count,
            baseline_daily_mean=baseline.daily_mean,
            baseline_daily_stdev=baseline.daily_stdev,
            sentiment_counts=sentiment_counts or {},
        )


class HttpAttentionSource(AttentionSource):
    """Base for sources that speak HTTP.

    Usable as an async context manager to share one connection pool across a
    watchlist sweep. Used without one, each fetch opens and closes its own
    client, which is what a single ad hoc call wants.
    """

    timeout = httpx.Timeout(15.0, connect=5.0)

    def __init__(self, settings: Settings | None = None, *, cache: TTLCache | None = None) -> None:
        super().__init__(settings, cache=cache)
        self._client: httpx.AsyncClient | None = None

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            timeout=self.timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )

    async def __aenter__(self) -> Self:
        self._client = self._new_client()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @asynccontextmanager
    async def _http(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
            return
        async with self._new_client() as client:
            yield client


@retry(
    retry=retry_if_exception_type((httpx.TransportError, TransientHttpError)),
    wait=wait_exponential_jitter(initial=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def http_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    limiter: RateLimiter,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    """Paced GET that retries only what is worth retrying.

    Any 4xx other than 429 means the request itself is wrong, so retrying it
    only burns quota against a cap that is already the binding constraint.
    """
    await limiter.acquire()
    response = await client.get(url, params=params)
    if response.status_code == 429 or response.status_code >= 500:
        raise TransientHttpError(f"{response.status_code} from {url}")
    return response
