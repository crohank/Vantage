"""Attention signals and the disclosure gap.

What this measures: how much public discussion a topic is getting. What it
does not measure: whether the market has priced it. The UI has to say so.
Overclaiming here is the fastest way to make the whole product look naive.

Raw mention counts are meaningless on their own, because a ticker that
normally draws 3 posts a week and one that draws 3,000 are not comparable.
Everything is normalized against the ticker's own trailing baseline.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field


class AttentionSourceName(StrEnum):
    BLUESKY = "bluesky"
    HACKERNEWS = "hackernews"
    REDDIT = "reddit"
    NEWS = "news"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class AttentionSignal(BaseModel):
    """One source's reading for one ticker over one window."""

    model_config = ConfigDict(frozen=True)

    source: AttentionSourceName
    ticker: str
    window_days: int
    mention_count: int
    # Mean daily mentions over a longer trailing period, used to normalize.
    baseline_daily_mean: float
    baseline_daily_stdev: float
    sentiment_counts: dict[Sentiment, int] = Field(default_factory=dict)
    sampled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Set when the source is configured but the call failed, so a degraded
    # reading is distinguishable from a genuine zero.
    error: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def available(self) -> bool:
        return self.error is None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def z_score(self) -> float:
        """Standard deviations above the ticker's own baseline.

        Guarded against a zero stdev, which happens for quiet tickers where
        every day in the baseline window had the same count.
        """
        expected = self.baseline_daily_mean * self.window_days
        if self.baseline_daily_stdev <= 0:
            return 0.0 if self.mention_count <= expected else 3.0
        spread = self.baseline_daily_stdev * math.sqrt(self.window_days)
        return (self.mention_count - expected) / spread

    @computed_field  # type: ignore[prop-decorator]
    @property
    def net_sentiment(self) -> float:
        """Positive share minus negative share, in [-1, 1]. 0 when unknown."""
        total = sum(self.sentiment_counts.values())
        if total == 0:
            return 0.0
        pos = self.sentiment_counts.get(Sentiment.POSITIVE, 0)
        neg = self.sentiment_counts.get(Sentiment.NEGATIVE, 0)
        return (pos - neg) / total


class AttentionScore(BaseModel):
    """Aggregate across whatever sources were available."""

    ticker: str
    window_days: int
    signals: list[AttentionSignal] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def available_sources(self) -> list[AttentionSourceName]:
        return [s.source for s in self.signals if s.available]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_mentions(self) -> int:
        return sum(s.mention_count for s in self.signals if s.available)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def score(self) -> float:
        """Attention in [0, 1], from the mean z-score across live sources.

        A logistic squash keeps a single viral source from saturating the
        result while still separating "quiet" from "loud".
        """
        live = [s for s in self.signals if s.available]
        if not live:
            return 0.0
        mean_z = sum(s.z_score for s in live) / len(live)
        return 1.0 / (1.0 + math.exp(-mean_z))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def net_sentiment(self) -> float:
        live = [s for s in self.signals if s.available and sum(s.sentiment_counts.values()) > 0]
        if not live:
            return 0.0
        return sum(s.net_sentiment for s in live) / len(live)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_degraded(self) -> bool:
        """True when some configured source failed, so the score understates."""
        return any(not s.available for s in self.signals)


class DisclosureGap(BaseModel):
    """A material change that nobody is talking about.

    gap = materiality * (1 - attention). High materiality with low attention
    is the quadrant worth alerting on.
    """

    finding_id: str
    ticker: str
    materiality: float = Field(ge=0.0, le=1.0)
    attention: AttentionScore

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gap_score(self) -> float:
        return self.materiality * (1.0 - self.attention.score)

    @property
    def is_alertable(self) -> bool:
        # Deliberately conservative. A noisy alert stream is worse than none,
        # and the threshold is a tunable the backtest in the eval suite
        # exists to inform.
        return self.gap_score >= 0.5 and not self.attention.is_degraded
