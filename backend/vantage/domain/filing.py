"""Filings, sections, spans, chunks.

`Span` is the load-bearing type. Every finding the system emits must point at
one, and a span that does not resolve to its exact quoted text in the stored
section is a bug rather than a low score. That invariant is what makes the
diff engine gradeable without an LLM in the loop.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, computed_field, model_validator


class Form(StrEnum):
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    EIGHT_K = "8-K"
    FORM_4 = "4"


class SectionId(StrEnum):
    """Canonical section identity, stable across years.

    Filings renumber and retitle items between years, so the raw heading is
    not a usable key. The parser maps whatever the document says onto one of
    these, and cross-year alignment joins on it.
    """

    BUSINESS = "item_1_business"
    RISK_FACTORS = "item_1a_risk_factors"
    UNRESOLVED_STAFF_COMMENTS = "item_1b_unresolved_staff_comments"
    # Required by SEC rule for fiscal years ending on or after 2023-12-15,
    # so it is present in FY2024 filings and absent from FY2023.
    CYBERSECURITY = "item_1c_cybersecurity"
    PROPERTIES = "item_2_properties"
    LEGAL_PROCEEDINGS = "item_3_legal_proceedings"
    MDA = "item_7_mda"
    MARKET_RISK = "item_7a_market_risk"
    FINANCIAL_STATEMENTS = "item_8_financial_statements"
    CONTROLS = "item_9a_controls"
    # 10-Q numbering differs from 10-K.
    QUARTERLY_MDA = "part1_item2_mda"
    QUARTERLY_RISK_FACTORS = "part2_item1a_risk_factors"
    QUARTERLY_LEGAL = "part2_item1_legal_proceedings"
    OTHER = "other"


def normalize_cik(raw: str | int) -> str:
    """SEC CIKs are canonically zero-padded to 10 digits."""
    return str(raw).strip().lstrip("CIK").lstrip("cik").strip().zfill(10)


def normalize_accession(raw: str) -> str:
    """Accession numbers appear both dashed and undashed. Store dashed."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 18:
        raise ValueError(f"accession must have 18 digits, got {raw!r}")
    return f"{digits[:10]}-{digits[10:12]}-{digits[12:]}"


class Filing(BaseModel):
    model_config = ConfigDict(frozen=True)

    accession: str
    cik: str
    ticker: str
    form: Form
    filing_date: date
    period_of_report: date | None = None
    primary_doc_url: str
    # Set once the document body has been fetched and stored.
    fetched_at: datetime | None = None
    char_length: int | None = None

    @model_validator(mode="after")
    def _normalize(self) -> Filing:
        object.__setattr__(self, "cik", normalize_cik(self.cik))
        object.__setattr__(self, "accession", normalize_accession(self.accession))
        object.__setattr__(self, "ticker", self.ticker.upper())
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fiscal_label(self) -> str:
        """Human label used to describe which filing a finding came from."""
        d = self.period_of_report or self.filing_date
        if self.form is Form.TEN_K:
            return f"FY{d.year}"
        return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class FilingSection(BaseModel):
    """One canonical section of one filing, stored untruncated.

    The previous pipeline capped each section at 5,000 characters before
    chunking and then capped assembled context at 3,000 more. A real Item 1A
    runs 20k to 50k words, so diffing under those caps is not possible.
    """

    model_config = ConfigDict(frozen=True)

    accession: str
    cik: str
    section_id: SectionId
    # The heading exactly as the filing writes it, kept for display and for
    # debugging parser mistakes.
    heading: str
    order: int
    text: str

    @property
    def key(self) -> str:
        return f"{self.accession}:{self.section_id.value}"

    def slice(self, start: int, end: int) -> str:
        return self.text[start:end]


class Span(BaseModel):
    """A verbatim, offset-addressed quotation from a stored section.

    `quote` is redundant with (accession, section_id, start, end) by design.
    Storing both lets `verify` prove after the fact that the offsets still
    resolve to the text a finding claimed, which is the citation-validity
    gate in CI.
    """

    model_config = ConfigDict(frozen=True)

    accession: str
    section_id: SectionId
    start: int
    end: int
    quote: str

    @model_validator(mode="after")
    def _check_bounds(self) -> Span:
        if self.start < 0 or self.end <= self.start:
            raise ValueError(f"invalid span bounds: [{self.start}, {self.end})")
        if len(self.quote) != self.end - self.start:
            raise ValueError(
                f"quote length {len(self.quote)} does not match span width {self.end - self.start}"
            )
        return self

    def verify(self, section: FilingSection) -> bool:
        """True when the offsets still resolve to exactly `quote`."""
        if section.accession != self.accession or section.section_id != self.section_id:
            return False
        return section.text[self.start : self.end] == self.quote

    @classmethod
    def from_section(cls, section: FilingSection, start: int, end: int) -> Span:
        return cls(
            accession=section.accession,
            section_id=section.section_id,
            start=start,
            end=end,
            quote=section.text[start:end],
        )

    def excerpt(self, limit: int = 300) -> str:
        if len(self.quote) <= limit:
            return self.quote
        return self.quote[: limit - 3].rstrip() + "..."


class Chunk(BaseModel):
    """A retrievable unit, carrying the offsets needed to cite it.

    `context_prefix` holds the one-line document context prepended before
    embedding (contextual retrieval). It is excluded from `start`/`end`, which
    address the raw section text, so a chunk can still produce an exact span.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    accession: str
    cik: str
    ticker: str
    section_id: SectionId
    ordinal: int
    text: str
    start: int
    end: int
    context_prefix: str = ""
    filing_date: date
    form: Form

    @staticmethod
    def make_id(accession: str, section_id: SectionId, ordinal: int) -> str:
        raw = f"{accession}:{section_id.value}:{ordinal}"
        return hashlib.sha1(raw.encode()).hexdigest()

    @property
    def embedding_text(self) -> str:
        """What actually gets embedded."""
        return f"{self.context_prefix}\n\n{self.text}".strip() if self.context_prefix else self.text

    def to_span(self, section: FilingSection) -> Span:
        return Span.from_section(section, self.start, self.end)


class RetrievedChunk(BaseModel):
    """A chunk plus the scores that surfaced it, kept for eval traces."""

    chunk: Chunk
    vector_score: float | None = None
    lexical_score: float | None = None
    fused_score: float | None = None
    rerank_score: float | None = None

    @property
    def final_score(self) -> float:
        for s in (self.rerank_score, self.fused_score, self.vector_score, self.lexical_score):
            if s is not None:
                return s
        return 0.0


class Company(BaseModel):
    model_config = ConfigDict(frozen=True)

    cik: str
    ticker: str
    name: str
    sic: str | None = None
    sic_description: str | None = None

    @model_validator(mode="after")
    def _normalize(self) -> Company:
        object.__setattr__(self, "cik", normalize_cik(self.cik))
        object.__setattr__(self, "ticker", self.ticker.upper())
        return self


class FilingPair(BaseModel):
    """Two comparable filings of the same form, adjacent in time.

    Comparability is the precondition for diffing: a 10-K only diffs against
    the prior 10-K, never against a 10-Q, because the section taxonomies differ.
    """

    current: Filing
    prior: Filing

    @model_validator(mode="after")
    def _check_comparable(self) -> FilingPair:
        if self.current.form is not self.prior.form:
            raise ValueError(
                f"cannot diff {self.current.form} against {self.prior.form}: "
                "section taxonomies differ between forms"
            )
        if self.current.cik != self.prior.cik:
            raise ValueError("cannot diff filings from different filers")
        if self.current.filing_date <= self.prior.filing_date:
            raise ValueError("current filing must be newer than prior")
        return self

    @property
    def label(self) -> str:
        return f"{self.prior.fiscal_label} to {self.current.fiscal_label}"
