"""Request and response contracts.

These are the single source of truth for the wire format. The frontend's
TypeScript is generated from the OpenAPI schema they produce, which replaces
four hand-maintained copies of the same objects (two TypeScript interface
sets, a camelCase Mongo shape, and the field names the writer agent used) and
the lossy hand-written mapper that reconciled them while silently dropping
timing and telemetry.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from vantage.domain.attention import AttentionScore
from vantage.domain.filing import Filing, SectionId, Span
from vantage.domain.finding import ChangeType, FindingKind, Materiality
from vantage.graph.state import RequestKind

# A ticker, not a sentence. Rejecting at the edge keeps a bad value out of the
# EDGAR rate limiter and out of the attention sources' daily quotas.
TICKER_PATTERN = r"^[A-Za-z]{1,5}(-[A-Za-z]{1,2})?$"


class AnalyzeRequest(BaseModel):
    ticker: str = Field(pattern=TICKER_PATTERN, description="US-listed ticker, for example AAPL")
    kind: RequestKind = RequestKind.FULL
    max_sections: int = Field(4, ge=1, le=6)

    @field_validator("ticker")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class JobRef(BaseModel):
    """What a submit returns. The work continues after the response."""

    job_id: str
    ticker: str
    kind: RequestKind
    status: str
    created_at: datetime
    stream_url: str


class JobSummary(BaseModel):
    job_id: str
    ticker: str
    kind: RequestKind
    status: str
    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    finding_count: int = 0


class SpanOut(BaseModel):
    """A citation. Every field needed to resolve it back to source text."""

    accession: str
    section_id: SectionId
    start: int
    end: int
    quote: str

    @classmethod
    def of(cls, span: Span) -> SpanOut:
        return cls(
            accession=span.accession,
            section_id=span.section_id,
            start=span.start,
            end=span.end,
            quote=span.quote,
        )


class FindingOut(BaseModel):
    id: str
    kind: FindingKind
    ticker: str
    cik: str
    section_id: SectionId
    change_type: ChangeType | None = None
    current_span: SpanOut | None = None
    prior_span: SpanOut | None = None
    current_accession: str | None = None
    prior_accession: str | None = None
    summary: str = ""
    rationale: str = ""
    materiality: Materiality
    novelty_phrase: str | None = None
    novelty_first_seen: str | None = None
    peer_ciks: list[str] = Field(default_factory=list)
    peer_total: int | None = None


class NodeTimingOut(BaseModel):
    node: str
    seconds: float


class AnalysisResult(BaseModel):
    """A completed run.

    `errors` is populated rather than hidden. Partial failure is visible to
    the caller instead of being swallowed into a plausible-looking default,
    which is how a hardcoded sentiment string shipped in every memo for the
    life of the previous system.
    """

    job_id: str
    ticker: str
    status: str
    company_name: str | None = None
    cik: str | None = None
    sic: str | None = None
    current_filing: Filing | None = None
    prior_filing: Filing | None = None
    findings: list[FindingOut] = Field(default_factory=list)
    attention: AttentionScore | None = None
    errors: list[str] = Field(default_factory=list)
    timings: list[NodeTimingOut] = Field(default_factory=list)


class SectionOut(BaseModel):
    """Section text, for resolving a citation in the UI."""

    accession: str
    section_id: SectionId
    heading: str
    text: str
    char_length: int


class HealthOut(BaseModel):
    status: str
    git_sha: str
    checkpointer: str
    attention_sources: list[str]
