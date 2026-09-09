"""Domain invariants.

The span invariant is the one that matters: a finding whose span does not
resolve to its exact quoted text is a bug, and CI must be able to say so.
"""

import pytest
from pydantic import ValidationError

from vantage.domain.filing import (
    Filing,
    FilingPair,
    FilingSection,
    Form,
    SectionId,
    Span,
    normalize_accession,
    normalize_cik,
)

import datetime as dt

SECTION = FilingSection(
    accession="0000320193-24-000123",
    cik="320193",
    section_id=SectionId.RISK_FACTORS,
    heading="Item 1A. Risk Factors",
    order=0,
    text="Two customers accounted for 39% of net sales.",
)


def _filing(accession: str, day: str, form: Form = Form.TEN_K) -> Filing:
    return Filing(
        accession=accession,
        cik="320193",
        ticker="aapl",
        form=form,
        filing_date=dt.date.fromisoformat(day),
        primary_doc_url="https://example.invalid/doc.htm",
    )


class TestNormalization:
    def test_cik_zero_pads_to_ten(self) -> None:
        assert normalize_cik(320193) == "0000320193"
        assert normalize_cik("CIK0000320193") == "0000320193"

    def test_accession_accepts_dashed_and_undashed(self) -> None:
        assert normalize_accession("000032019324000123") == "0000320193-24-000123"
        assert normalize_accession("0000320193-24-000123") == "0000320193-24-000123"

    def test_accession_rejects_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="18 digits"):
            normalize_accession("123")

    def test_filing_upcases_ticker(self) -> None:
        assert _filing("0000320193-24-000123", "2024-11-01").ticker == "AAPL"


class TestSpan:
    def test_from_section_round_trips(self) -> None:
        span = Span.from_section(SECTION, 0, 13)
        assert span.quote == "Two customers"
        assert span.verify(SECTION)

    def test_tampered_quote_fails_verification(self) -> None:
        span = Span(
            accession=SECTION.accession,
            section_id=SECTION.section_id,
            start=0,
            end=13,
            quote="Ten customers",
        )
        assert not span.verify(SECTION)

    def test_quote_length_must_match_offsets(self) -> None:
        with pytest.raises(ValidationError):
            Span(
                accession=SECTION.accession,
                section_id=SECTION.section_id,
                start=0,
                end=13,
                quote="short",
            )

    def test_span_from_another_section_fails(self) -> None:
        span = Span.from_section(SECTION, 0, 13)
        other = SECTION.model_copy(update={"section_id": SectionId.MDA})
        assert not span.verify(other)

    def test_excerpt_stays_within_limit(self) -> None:
        long_section = SECTION.model_copy(update={"text": "x" * 500})
        span = Span.from_section(long_section, 0, 500)
        assert len(span.excerpt(100)) == 100
        assert span.excerpt(100).endswith("...")


class TestFilingPair:
    def test_rejects_mismatched_forms(self) -> None:
        # A 10-K and a 10-Q use different section taxonomies, so diffing them
        # produces noise rather than signal.
        with pytest.raises(ValidationError, match="section taxonomies differ"):
            FilingPair(
                current=_filing("0000320193-24-000123", "2024-11-01", Form.TEN_K),
                prior=_filing("0000320193-23-000106", "2023-11-03", Form.TEN_Q),
            )

    def test_rejects_reversed_chronology(self) -> None:
        with pytest.raises(ValidationError, match="must be newer"):
            FilingPair(
                current=_filing("0000320193-23-000106", "2023-11-03"),
                prior=_filing("0000320193-24-000123", "2024-11-01"),
            )

    def test_accepts_adjacent_annual_filings(self) -> None:
        pair = FilingPair(
            current=_filing("0000320193-24-000123", "2024-11-01"),
            prior=_filing("0000320193-23-000106", "2023-11-03"),
        )
        assert pair.label == "FY2023 to FY2024"
