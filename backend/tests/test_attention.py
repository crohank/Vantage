"""Attention layer, offline.

Every test here mocks the HTTP layer. The two things worth protecting are the
ones that change what the product does rather than what a number reads:

* a source that fails returns `error=` instead of raising, so a broken
  provider stays distinguishable from a genuine zero
* an unconfigured source is dropped rather than recorded as a failure, so
  never having had a Reddit key does not permanently silence alerting

Settings are built with `model_construct`, which reads neither the env file
nor the process environment. Without that, a developer with a real
FINNHUB_API_KEY in .env would run a different set of tests than CI.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr
from tenacity import wait_none

from vantage.attention import hackernews, news
from vantage.attention.base import (
    AttentionSource,
    Baseline,
    QuotaExhausted,
    RateLimiter,
    TTLCache,
    http_get,
    normalize_company_name,
    poisson_baseline,
    query_terms,
    summarize_timestamps,
)
from vantage.attention.hackernews import SEARCH_URL, HackerNewsSource
from vantage.attention.news import FINNHUB_URL, GOOGLE_NEWS_URL, MARKETAUX_URL, NewsSource
from vantage.attention.score import build_gap, score_attention
from vantage.config import Settings
from vantage.domain.attention import (
    AttentionScore,
    AttentionSignal,
    AttentionSourceName,
    Sentiment,
)
from vantage.domain.finding import Materiality

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _settings(**overrides: Any) -> Settings:
    return Settings.model_construct(**overrides)


def _at(days_ago: float) -> datetime:
    return NOW - timedelta(days=days_ago)


def _signal(**overrides: Any) -> AttentionSignal:
    fields: dict[str, Any] = {
        "source": AttentionSourceName.HACKERNEWS,
        "ticker": "AAPL",
        "window_days": 7,
        "mention_count": 0,
        "baseline_daily_mean": 0.0,
        "baseline_daily_stdev": 0.0,
    }
    fields.update(overrides)
    return AttentionSignal(**fields)


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip the pacing and the retry backoff.

    Hacker News paces at 4/s and the news providers at 1/s, and tenacity backs
    off for seconds before giving up. Sleeping through either in CI covers
    nothing that the limiter tests do not already assert directly, and the
    retry paths alone cost eight seconds at the real schedule.
    """
    unthrottled = RateLimiter(rate_per_second=10_000.0)
    monkeypatch.setattr(hackernews, "_limiter", unthrottled)
    for attr in ("_finnhub_limiter", "_marketaux_limiter", "_google_news_limiter"):
        monkeypatch.setattr(news, attr, unthrottled)
    monkeypatch.setattr(http_get.retry, "wait", wait_none())


class _FakeSource(AttentionSource):
    """An AttentionSource with no I/O, for testing the contract around it."""

    def __init__(
        self,
        source_name: AttentionSourceName,
        *,
        configured: bool = True,
        mention_count: int = 0,
        boom: Exception | None = None,
    ) -> None:
        super().__init__(_settings())
        self._name = source_name
        self._configured = configured
        self._mention_count = mention_count
        self._boom = boom
        self.calls = 0

    @property
    def name(self) -> AttentionSourceName:
        return self._name

    def is_configured(self) -> bool:
        return self._configured

    async def _collect(self, ticker: str, company_name: str, window_days: int) -> AttentionSignal:
        self.calls += 1
        if self._boom is not None:
            raise self._boom
        return self.build_signal(ticker, window_days, Baseline(self._mention_count, 1.0, 0.5))


class TestBaseline:
    def test_quiet_days_stay_in_the_sample(self) -> None:
        # Four mentions on one baseline day and nothing on the other 82. The
        # mean has to be 4/83, not 4.0.
        result = summarize_timestamps([_at(20.5)] * 4, now=NOW, window_days=7, baseline_days=90)
        assert result.mention_count == 0
        assert result.daily_mean == pytest.approx(4 / 83)

    def test_window_is_excluded_from_its_own_baseline(self) -> None:
        stamps = [_at(1)] * 50 + [_at(30.5), _at(31.5)]
        result = summarize_timestamps(stamps, now=NOW, window_days=7, baseline_days=90)
        assert result.mention_count == 50
        # 50 mentions inside the window, 2 in the 83 baseline days.
        assert result.daily_mean == pytest.approx(2 / 83)

    def test_mean_and_stdev_over_known_daily_counts(self) -> None:
        # Three baseline days holding 3, 3 and 0 mentions.
        stamps = [_at(8.5)] * 3 + [_at(9.5)] * 3
        result = summarize_timestamps(stamps, now=NOW, window_days=7, baseline_days=10)
        assert result.daily_mean == pytest.approx(2.0)
        assert result.daily_stdev == pytest.approx(math.sqrt(3.0))

    def test_truncation_clips_the_baseline_to_what_was_seen(self) -> None:
        stamps = [_at(8.5), _at(9.5), _at(10.5)]
        full = summarize_timestamps(stamps, now=NOW, window_days=7, baseline_days=90)
        clipped = summarize_timestamps(
            stamps, now=NOW, window_days=7, baseline_days=90, truncated=True
        )
        # Untruncated, the 80 unseen days count as zeros and flatten the mean.
        assert full.daily_mean == pytest.approx(3 / 83)
        assert clipped.daily_mean == pytest.approx(1.0)

    def test_one_day_of_history_is_not_a_baseline(self) -> None:
        result = summarize_timestamps([_at(0.5)] * 14, now=NOW, window_days=7, baseline_days=8)
        assert result.mention_count == 14
        assert result.daily_mean == pytest.approx(2.0)
        # Reporting the window's own rate puts the z-score at zero: no claim.
        assert _signal(
            mention_count=result.mention_count,
            baseline_daily_mean=result.daily_mean,
            baseline_daily_stdev=result.daily_stdev,
        ).z_score == pytest.approx(0.0)

    def test_no_mentions_at_all(self) -> None:
        result = summarize_timestamps([], now=NOW, window_days=7, baseline_days=90)
        assert result == Baseline(0, 0.0, 0.0)

    def test_poisson_variance_equals_the_mean(self) -> None:
        mean, stdev = poisson_baseline(90, 90)
        assert mean == pytest.approx(1.0)
        assert stdev == pytest.approx(1.0)
        assert poisson_baseline(5, 0) == (0.0, 0.0)


class TestZScore:
    def test_normalizes_against_the_ticker_baseline(self) -> None:
        signal = _signal(mention_count=40, baseline_daily_mean=2.0, baseline_daily_stdev=1.0)
        assert signal.z_score == pytest.approx((40 - 14) / math.sqrt(7))

    def test_zero_stdev_with_a_spike_saturates(self) -> None:
        # Every baseline day was identical, so there is no spread to divide
        # by. Any excess is treated as a strong spike rather than a NaN.
        assert _signal(mention_count=5).z_score == 3.0

    def test_zero_stdev_at_or_below_baseline_is_not_a_spike(self) -> None:
        assert _signal(mention_count=14, baseline_daily_mean=2.0).z_score == 0.0
        assert _signal(mention_count=3, baseline_daily_mean=2.0).z_score == 0.0


class TestQueryTerms:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Apple Inc.", "Apple"),
            ("NVIDIA CORP", "NVIDIA"),
            ("The Home Depot, Inc.", "Home Depot"),
            ("Meta Platforms, Inc.", "Meta Platforms"),
        ],
    )
    def test_strips_the_legal_form(self, raw: str, expected: str) -> None:
        assert normalize_company_name(raw) == expected

    def test_short_tickers_are_dropped(self) -> None:
        # "A" is Agilent and also the most common word in English.
        assert query_terms("A", "Agilent Technologies, Inc.") == ["Agilent Technologies"]

    def test_ticker_is_kept_alongside_the_name(self) -> None:
        assert query_terms("AAPL", "Apple Inc.") == ["Apple", "AAPL"]

    def test_a_name_of_only_generic_words_is_kept_whole(self) -> None:
        # Stripping "The" and "Group" leaves nothing, so the original stands
        # rather than searching for an empty string.
        assert query_terms("IT", "The Group") == ["The Group"]

    def test_no_name_and_a_short_ticker_still_queries(self) -> None:
        # A noisy query beats reporting a false zero.
        assert query_terms("IT", "") == ["IT"]


class TestTTLCache:
    def test_returns_a_stored_signal(self) -> None:
        cache = TTLCache(ttl_seconds=60.0)
        cache.set(("AAPL", "apple", 7), _signal(mention_count=3))
        stored = cache.get(("AAPL", "apple", 7))
        assert stored is not None
        assert stored.mention_count == 3

    def test_expired_entries_are_dropped(self) -> None:
        cache = TTLCache(ttl_seconds=0.0)
        cache.set(("AAPL", "apple", 7), _signal())
        assert cache.get(("AAPL", "apple", 7)) is None
        assert len(cache) == 0

    def test_failures_expire_sooner_than_successes(self) -> None:
        # One blip must not keep a source dark for a full success TTL.
        cache = TTLCache(ttl_seconds=600.0, error_ttl_seconds=0.0)
        cache.set(("AAPL", "apple", 7), _signal(error="boom"))
        cache.set(("MSFT", "microsoft", 7), _signal())
        assert cache.get(("AAPL", "apple", 7)) is None
        assert cache.get(("MSFT", "microsoft", 7)) is not None


class TestRateLimiter:
    async def test_daily_cap_is_enforced(self) -> None:
        limiter = RateLimiter(rate_per_second=10_000.0, max_per_day=2)
        await limiter.acquire()
        await limiter.acquire()
        with pytest.raises(QuotaExhausted, match="daily cap of 2"):
            await limiter.acquire()
        assert limiter.spent_today == 2

    async def test_no_cap_means_no_ceiling(self) -> None:
        limiter = RateLimiter(rate_per_second=10_000.0)
        for _ in range(10):
            await limiter.acquire()
        assert limiter.spent_today == 10


class TestFetchContract:
    async def test_a_failing_source_returns_an_error_not_an_exception(self) -> None:
        source = _FakeSource(AttentionSourceName.REDDIT, boom=RuntimeError("429 from reddit"))
        signal = await source.fetch("AAPL", "Apple Inc.", 7)
        assert not signal.available
        assert signal.error is not None
        assert "429 from reddit" in signal.error
        # A dead source must not read as a genuine zero.
        assert signal.mention_count == 0

    async def test_unconfigured_never_reaches_the_provider(self) -> None:
        source = _FakeSource(AttentionSourceName.BLUESKY, configured=False)
        signal = await source.fetch("AAPL", "Apple Inc.", 7)
        assert source.calls == 0
        assert signal.error == "source is not configured"

    async def test_cache_prevents_a_second_call(self) -> None:
        source = _FakeSource(AttentionSourceName.HACKERNEWS, mention_count=11)
        first = await source.fetch("AAPL", "Apple Inc.", 7)
        second = await source.fetch("aapl", "Apple Inc.", 7)
        assert source.calls == 1
        assert second is first

    async def test_a_different_window_is_a_different_reading(self) -> None:
        source = _FakeSource(AttentionSourceName.HACKERNEWS)
        await source.fetch("AAPL", "Apple Inc.", 7)
        await source.fetch("AAPL", "Apple Inc.", 30)
        assert source.calls == 2


def _hn_payload(stamps: list[datetime], start_id: int = 0) -> dict[str, Any]:
    hits = [
        {"objectID": str(start_id + i), "created_at_i": int(ts.timestamp())}
        for i, ts in enumerate(stamps)
    ]
    return {"hits": hits, "nbHits": len(hits)}


class TestHackerNews:
    @respx.mock
    async def test_counts_the_window_and_measures_the_baseline(self) -> None:
        now = datetime.now(UTC)
        # One mention in each of the 83 baseline days, ten inside the window.
        stamps = [now - timedelta(days=7.5 + k) for k in range(83)]
        stamps += [now - timedelta(days=1)] * 10
        respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=_hn_payload(stamps)))

        signal = await HackerNewsSource(_settings()).fetch("AAPL", "Apple Inc.", 7)

        assert signal.available
        assert signal.mention_count == 10
        assert signal.baseline_daily_mean == pytest.approx(1.0)
        # No sentiment API on Algolia, so the counts stay empty rather than
        # being invented.
        assert signal.sentiment_counts == {}
        assert signal.net_sentiment == 0.0

    @respx.mock
    async def test_the_same_thread_is_not_counted_twice(self) -> None:
        # "Apple" and "AAPL" are two queries that hit the same threads.
        now = datetime.now(UTC)
        stamps = [now - timedelta(days=1)] * 6
        route = respx.get(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_hn_payload(stamps))
        )

        signal = await HackerNewsSource(_settings()).fetch("AAPL", "Apple Inc.", 7)

        assert route.call_count == 2
        assert signal.mention_count == 6

    @respx.mock
    async def test_a_truncated_page_falls_back_to_exact_counts(self) -> None:
        # Above ~1000 mentions the returned hits only cover the last few days,
        # which is inside the window, so there is no history left to enumerate.
        # The source switches to hitsPerPage=0 count requests instead.
        now = datetime.now(UTC)
        now_ts = int(now.timestamp())

        def handler(request: httpx.Request) -> httpx.Response:
            params = request.url.params
            cutoff = int(str(params["numericFilters"]).split(">")[1])
            if str(params["hitsPerPage"]) == "0":
                is_window = (now_ts - cutoff) < 30 * 86_400
                return httpx.Response(200, json={"hits": [], "nbHits": 100 if is_window else 1000})
            # The enumerated page is capped well below the true total.
            payload = _hn_payload([now - timedelta(days=0.5)] * 3)
            payload["nbHits"] = 5000
            return httpx.Response(200, json=payload)

        route = respx.get(SEARCH_URL).mock(side_effect=handler)

        signal = await HackerNewsSource(_settings()).fetch("AAPL", "Apple Inc.", 7)

        # Two terms: one enumeration plus two counts each.
        assert route.call_count == 6
        # Totals are summed over both terms, not deduplicated.
        assert signal.mention_count == 200
        # 2000 over the period less 200 in the window, spread over 83 days.
        assert signal.baseline_daily_mean == pytest.approx(1800 / 83)
        assert signal.z_score > 1.0

    @respx.mock
    async def test_a_dead_endpoint_yields_an_error_signal(self) -> None:
        respx.get(SEARCH_URL).mock(return_value=httpx.Response(404))
        signal = await HackerNewsSource(_settings()).fetch("AAPL", "Apple Inc.", 7)
        assert not signal.available
        assert signal.error is not None
        assert "404" in signal.error

    @respx.mock
    async def test_a_transport_failure_yields_an_error_signal(self) -> None:
        respx.get(SEARCH_URL).mock(side_effect=httpx.ConnectError("no route to host"))
        signal = await HackerNewsSource(_settings()).fetch("AAPL", "Apple Inc.", 7)
        assert not signal.available
        assert signal.error is not None
        assert "ConnectError" in signal.error


def _rss(items: list[tuple[str, datetime]]) -> bytes:
    body = "".join(
        f"<item><title>{title}</title>"
        f"<link>https://news.google.com/rss/articles/{i}</link>"
        f"<pubDate>{format_datetime(published)}</pubDate></item>"
        for i, (title, published) in enumerate(items)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel><title>Google News</title>'
        f"{body}</channel></rss>"
    ).encode()


class TestNews:
    @respx.mock
    async def test_google_news_alone_produces_a_reading(self) -> None:
        now = datetime.now(UTC)
        items = [(f"Story {k} - Reuters", now - timedelta(days=7.5 + k)) for k in range(20)]
        items += [(f"Fresh {k} - Bloomberg", now - timedelta(days=1)) for k in range(4)]
        respx.get(GOOGLE_NEWS_URL).mock(return_value=httpx.Response(200, content=_rss(items)))

        source = NewsSource(_settings())
        assert source.is_configured(), "the RSS feed needs no key, so news is always available"
        signal = await source.fetch("AAPL", "Apple Inc.", 7)

        assert signal.available
        assert signal.mention_count == 4

    @respx.mock
    async def test_one_dead_provider_does_not_degrade_the_signal(self) -> None:
        # Marking NEWS degraded on a Finnhub blip would trip is_degraded and
        # silence alerting for a reason unrelated to the reading.
        now = datetime.now(UTC)
        respx.get(GOOGLE_NEWS_URL).mock(
            return_value=httpx.Response(
                200, content=_rss([("Only story - Reuters", now - timedelta(days=1))])
            )
        )
        respx.get(FINNHUB_URL).mock(return_value=httpx.Response(403))

        settings = _settings(finnhub_api_key=SecretStr("k"))
        signal = await NewsSource(settings).fetch("AAPL", "Apple Inc.", 7)

        assert signal.available
        assert signal.mention_count == 1

    @respx.mock
    async def test_every_provider_failing_is_an_error(self) -> None:
        respx.get(GOOGLE_NEWS_URL).mock(return_value=httpx.Response(503))
        respx.get(FINNHUB_URL).mock(return_value=httpx.Response(403))

        settings = _settings(finnhub_api_key=SecretStr("k"))
        signal = await NewsSource(settings).fetch("AAPL", "Apple Inc.", 7)

        assert not signal.available
        assert signal.error is not None
        assert "all news providers failed" in signal.error

    @respx.mock
    async def test_finnhub_and_google_news_are_deduplicated_by_headline(self) -> None:
        # Google News rewrites links, so the headline is the only join key.
        now = datetime.now(UTC)
        headline = "Apple discloses a new customer concentration"
        respx.get(GOOGLE_NEWS_URL).mock(
            return_value=httpx.Response(
                200, content=_rss([(f"{headline} - Reuters", now - timedelta(days=1))])
            )
        )
        respx.get(FINNHUB_URL).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "datetime": int((now - timedelta(days=1)).timestamp()),
                        "headline": headline,
                        "url": "https://reuters.com/a",
                    }
                ],
            )
        )

        settings = _settings(finnhub_api_key=SecretStr("k"))
        signal = await NewsSource(settings).fetch("AAPL", "Apple Inc.", 7)

        assert signal.mention_count == 1

    @respx.mock
    async def test_marketaux_scores_map_onto_the_sentiment_enum(self) -> None:
        now = datetime.now(UTC)
        respx.get(GOOGLE_NEWS_URL).mock(
            return_value=httpx.Response(
                200, content=_rss([("Something - Reuters", now - timedelta(days=1))])
            )
        )
        respx.get(MARKETAUX_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "meta": {"found": 12},
                    "data": [
                        {
                            "title": "Upbeat",
                            "url": "https://x/1",
                            "published_at": "2026-09-07T10:00:00.000000Z",
                            "entities": [{"symbol": "AAPL", "sentiment_score": 0.62}],
                        },
                        {
                            "title": "Grim",
                            "url": "https://x/2",
                            "published_at": "2026-09-07T11:00:00.000000Z",
                            "entities": [{"symbol": "AAPL", "sentiment_score": -0.44}],
                        },
                        {
                            "title": "Flat",
                            "url": "https://x/3",
                            "published_at": "2026-09-07T12:00:00.000000Z",
                            # Inside the deadband, and the MSFT entity on the
                            # same article must be ignored.
                            "entities": [
                                {"symbol": "AAPL", "sentiment_score": 0.04},
                                {"symbol": "MSFT", "sentiment_score": 0.99},
                            ],
                        },
                    ],
                },
            )
        )

        settings = _settings(marketaux_api_key=SecretStr("k"))
        signal = await NewsSource(settings).fetch("AAPL", "Apple Inc.", 7)

        assert signal.sentiment_counts == {
            Sentiment.POSITIVE: 1,
            Sentiment.NEGATIVE: 1,
            Sentiment.NEUTRAL: 1,
        }
        assert signal.net_sentiment == pytest.approx(0.0)


class TestScoreAttention:
    async def test_unconfigured_sources_are_skipped_not_recorded(self) -> None:
        live = _FakeSource(AttentionSourceName.HACKERNEWS, mention_count=4)
        dark = _FakeSource(AttentionSourceName.REDDIT, configured=False)

        score = await score_attention("AAPL", "Apple Inc.", 7, [live, dark])

        assert score.available_sources == [AttentionSourceName.HACKERNEWS]
        assert len(score.signals) == 1
        # Never having had a Reddit key is not a degraded reading.
        assert not score.is_degraded

    async def test_a_failing_source_degrades_the_score(self) -> None:
        live = _FakeSource(AttentionSourceName.HACKERNEWS, mention_count=4)
        broken = _FakeSource(AttentionSourceName.NEWS, boom=RuntimeError("upstream 500"))

        score = await score_attention("AAPL", "Apple Inc.", 7, [live, broken])

        assert score.is_degraded
        assert score.available_sources == [AttentionSourceName.HACKERNEWS]
        assert score.total_mentions == 4

    async def test_no_configured_source_scores_zero(self) -> None:
        dark = _FakeSource(AttentionSourceName.REDDIT, configured=False)
        score = await score_attention("AAPL", "Apple Inc.", 7, [dark])
        assert score.signals == []
        assert score.score == 0.0
        assert not score.is_degraded

    async def test_ticker_is_normalized_onto_every_signal(self) -> None:
        source = _FakeSource(AttentionSourceName.HACKERNEWS)
        score = await score_attention("aapl", "Apple Inc.", 7, [source])
        assert score.ticker == "AAPL"
        assert all(signal.ticker == "AAPL" for signal in score.signals)


class TestBuildGap:
    def _attention(self, *, mention_count: int, degraded: bool = False) -> AttentionScore:
        signals = [
            _signal(
                mention_count=mention_count,
                baseline_daily_mean=2.0,
                baseline_daily_stdev=1.0,
            )
        ]
        if degraded:
            signals.append(_signal(source=AttentionSourceName.NEWS, error="upstream 500"))
        return AttentionScore(ticker="AAPL", window_days=7, signals=signals)

    def test_high_materiality_and_silence_is_the_alertable_quadrant(self) -> None:
        gap = build_gap("f1", "aapl", Materiality(score=0.9), self._attention(mention_count=0))
        assert gap.ticker == "AAPL"
        assert gap.materiality == pytest.approx(0.9)
        # Nobody is talking, so the gap keeps almost all the materiality.
        assert gap.gap_score > 0.5
        assert gap.is_alertable

    def test_loud_coverage_closes_the_gap(self) -> None:
        gap = build_gap("f1", "AAPL", Materiality(score=0.9), self._attention(mention_count=400))
        assert gap.gap_score < 0.5
        assert not gap.is_alertable

    def test_a_bare_float_is_accepted(self) -> None:
        gap = build_gap("f1", "AAPL", 0.4, self._attention(mention_count=0))
        assert gap.materiality == pytest.approx(0.4)

    def test_a_flat_baseline_cannot_reach_the_alert_threshold(self) -> None:
        # Pinning a consequence of the domain contract that is easy to trip
        # over. The zero-stdev guard returns 0.0 rather than a negative
        # z-score, the logistic squash turns that into an attention of 0.5,
        # and gap_score therefore caps at materiality/2. A ticker with no
        # measurable variance in its chatter can never clear the 0.5 bar.
        flat = AttentionScore(
            ticker="AAPL",
            window_days=7,
            signals=[_signal(mention_count=0, baseline_daily_mean=2.0)],
        )
        gap = build_gap("f1", "AAPL", Materiality(score=1.0), flat)
        assert flat.score == pytest.approx(0.5)
        assert gap.gap_score == pytest.approx(0.5)

    def test_a_degraded_reading_never_alerts(self) -> None:
        # The score understates when a source is down, so a gap computed from
        # it is not trustworthy enough to page anyone.
        gap = build_gap(
            "f1", "AAPL", Materiality(score=0.95), self._attention(mention_count=0, degraded=True)
        )
        assert gap.gap_score > 0.5
        assert not gap.is_alertable


@pytest.mark.live
async def test_hackernews_live_reading() -> None:
    """Hits the real Algolia index. Needs no key. Run with `pytest -m live`."""
    signal = await HackerNewsSource(_settings()).fetch("AAPL", "Apple Inc.", 7)
    assert signal.available, signal.error
    # Apple is discussed on HN every single day, so a zero baseline would mean
    # the query or the response shape changed.
    assert signal.baseline_daily_mean > 0.0


@pytest.mark.live
async def test_hackernews_live_megacap_still_has_a_baseline() -> None:
    """A ticker loud enough to truncate the enumerated page.

    NVIDIA returned 16,487 hits over 90 days against a 1000 hit page cap, so
    this exercises the count-only fallback. Before it existed the returned
    hits all landed inside the window and the z-score collapsed to 0.0.
    """
    async with HackerNewsSource(_settings()) as source:
        signal = await source.fetch("NVDA", "NVIDIA CORP", 7)
    assert signal.available, signal.error
    assert signal.mention_count > 0
    assert signal.baseline_daily_stdev > 0.0
