"""Run the sources and turn their readings into a score and a gap.

The aggregation itself lives on `AttentionScore` in the domain. This module
only decides which sources to run, runs them at the same time, and makes sure
one broken source cannot take the others down with it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from vantage.attention.base import DEFAULT_WINDOW_DAYS, AttentionSource
from vantage.attention.hackernews import HackerNewsSource
from vantage.attention.news import NewsSource
from vantage.config import Settings
from vantage.domain.attention import AttentionScore, AttentionSignal, DisclosureGap
from vantage.domain.finding import Materiality

log = logging.getLogger(__name__)


def default_sources(settings: Settings | None = None) -> list[AttentionSource]:
    """Every source the layer knows about, configured or not.

    Bluesky and Reddit are constructed through their modules, which import
    atproto and praw only inside the fetch path, so building this list costs
    nothing and cannot fail on a missing optional dependency.
    """
    from vantage.attention.bluesky import BlueskySource
    from vantage.attention.reddit import RedditSource

    return [
        HackerNewsSource(settings),
        BlueskySource(settings),
        RedditSource(settings),
        NewsSource(settings),
    ]


async def score_attention(
    ticker: str,
    company_name: str,
    window_days: int = DEFAULT_WINDOW_DAYS,
    sources: Sequence[AttentionSource] | None = None,
) -> AttentionScore:
    """Read every configured source concurrently and combine the results.

    Unconfigured sources are left out entirely rather than recorded as
    failures. Never having had a Reddit key is not a degraded reading, so it
    must not set `is_degraded` and block alerting.
    """
    symbol = ticker.strip().upper()
    pool = list(sources) if sources is not None else default_sources()
    live = [source for source in pool if source.is_configured()]
    if not live:
        log.warning("no attention source is configured, score for %s will be 0.0", symbol)
        return AttentionScore(ticker=symbol, window_days=window_days)

    results = await asyncio.gather(
        *(source.fetch(symbol, company_name, window_days) for source in live),
        return_exceptions=True,
    )

    signals: list[AttentionSignal] = []
    for source, result in zip(live, results, strict=True):
        if isinstance(result, BaseException):
            # AttentionSource.fetch is contracted not to raise, so reaching
            # here is a bug in a source rather than a provider outage. It is
            # still recorded as a degraded reading instead of dropped.
            log.error("%s.fetch raised for %s", source.name.value, symbol, exc_info=result)
            signals.append(
                source.error_signal(symbol, window_days, f"{type(result).__name__}: {result}")
            )
            continue
        signals.append(result)

    return AttentionScore(ticker=symbol, window_days=window_days, signals=signals)


def build_gap(
    finding_id: str,
    ticker: str,
    materiality: Materiality | float,
    attention: AttentionScore,
) -> DisclosureGap:
    """Pair a finding's materiality with what the public is saying about it.

    Accepts the `Materiality` a Finding carries as well as a bare float,
    because `DisclosureGap.materiality` is a float and unwrapping it at every
    call site is how the two drift apart.
    """
    score = materiality.score if isinstance(materiality, Materiality) else float(materiality)
    return DisclosureGap(
        finding_id=finding_id,
        ticker=ticker.strip().upper(),
        materiality=score,
        attention=attention,
    )
