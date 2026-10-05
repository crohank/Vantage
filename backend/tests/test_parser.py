"""Section extraction.

Each test here corresponds to a way the previous regex-over-raw-HTML
implementation failed on real filings.
"""

import datetime as dt

from vantage.domain.filing import Filing, Form, SectionId
from vantage.ingest.parser import _parse_item_line, extract_sections, find_headings, html_to_lines

FILING = Filing(
    accession="0000320193-24-000123",
    cik="320193",
    ticker="AAPL",
    form=Form.TEN_K,
    filing_date=dt.date(2024, 11, 1),
    primary_doc_url="https://example.invalid/doc.htm",
)


class TestHeadingRecognition:
    def test_accepts_period_hyphen_and_en_dash_separators(self) -> None:
        for sep in (".", " -", " " + chr(0x2013)):
            parsed = _parse_item_line(f"Item 1A{sep} Risk Factors", Form.TEN_K)
            assert parsed is not None, sep
            assert parsed[1] is SectionId.RISK_FACTORS

    def test_rejects_prose_that_merely_cites_an_item(self) -> None:
        prose = (
            "Investors should review the factors described in Part I, Item 1A of "
            "this Annual Report on Form 10-K under the heading Risk Factors, which "
            "could materially affect our business and results of operations."
        )
        assert _parse_item_line(prose, Form.TEN_K) is None

    def test_rejects_item_number_with_mismatched_title(self) -> None:
        # "Item 2" is Properties. A line claiming otherwise is a coincidence.
        parsed = _parse_item_line("Item 2. Exhibits and Signatures", Form.TEN_K)
        assert parsed is not None
        assert parsed[1] is None, "unmapped, but still a boundary"

    def test_unmapped_items_are_still_boundaries(self) -> None:
        parsed = _parse_item_line("Item 5. Market for Registrant's Common Equity", Form.TEN_K)
        assert parsed is not None
        assert parsed[1] is None
        assert parsed[0] == "|5"


class TestExtraction:
    def test_finds_all_canonical_sections(self, ten_k_html: bytes) -> None:
        sections = {s.section_id: s for s in extract_sections(FILING, ten_k_html)}
        assert SectionId.BUSINESS in sections
        assert SectionId.RISK_FACTORS in sections
        assert SectionId.UNRESOLVED_STAFF_COMMENTS in sections
        assert SectionId.CYBERSECURITY in sections
        assert SectionId.PROPERTIES in sections

    def test_table_of_contents_does_not_become_a_section(self, ten_k_html: bytes) -> None:
        # The TOC lists every heading. If it won, Business would contain the
        # remaining TOC rows and nothing else.
        business = next(
            s for s in extract_sections(FILING, ten_k_html) if s.section_id is SectionId.BUSINESS
        )
        assert "We design and sell devices" in business.text
        assert "Item 1A. Risk Factors" not in business.text

    def test_unmapped_item_does_not_bleed_into_previous_section(self, ten_k_html: bytes) -> None:
        # Regression: SEC added Item 1C for fiscal years ending after
        # 2023-12-15. Before it was mapped, its whole body was absorbed into
        # Item 1B, which made the next year's diff report Item 1B as
        # massively reworded when nothing about it had changed.
        sections = {s.section_id: s for s in extract_sections(FILING, ten_k_html)}
        assert sections[SectionId.UNRESOLVED_STAFF_COMMENTS].text.strip() == "None."
        assert "information security" in sections[SectionId.CYBERSECURITY].text

    def test_decodes_html_entities_in_headings(self, ten_k_html: bytes) -> None:
        headings = [s.heading for s in extract_sections(FILING, ten_k_html)]
        assert "Item 1. Business" in headings
        assert not any("&#" in h for h in headings)

    def test_spans_resolve_against_extracted_text(self, ten_k_html: bytes) -> None:
        risk = next(
            s
            for s in extract_sections(FILING, ten_k_html)
            if s.section_id is SectionId.RISK_FACTORS
        )
        idx = risk.text.index("39%")
        from vantage.domain.filing import Span

        span = Span.from_section(risk, idx, idx + 3)
        assert span.quote == "39%"
        assert span.verify(risk)

    def test_empty_input_yields_nothing(self) -> None:
        assert html_to_lines(b"") == []
        assert extract_sections(FILING, b"") == []

    def test_malformed_html_falls_back_rather_than_raising(self) -> None:
        broken = b"<div><span>Item 1A. Risk Factors<div>Demand may decline."
        sections = extract_sections(FILING, broken)
        assert any(s.section_id is SectionId.RISK_FACTORS for s in sections)


class TestQuarterly:
    def test_ten_q_uses_its_own_numbering(self) -> None:
        # Item 1A means Risk Factors in a 10-K, but in a 10-Q it only means
        # that under Part II.
        parsed = _parse_item_line("Part II, Item 1A. Risk Factors", Form.TEN_Q)
        assert parsed is not None
        assert parsed[1] is SectionId.QUARTERLY_RISK_FACTORS

    def test_ten_q_mda_is_part_one_item_two(self) -> None:
        parsed = _parse_item_line(
            "Item 2. Management's Discussion and Analysis of Financial Condition",
            Form.TEN_Q,
        )
        assert parsed is not None
        assert parsed[1] is SectionId.QUARTERLY_MDA


def test_headings_are_ordered_by_position(ten_k_html: bytes) -> None:
    lines = html_to_lines(ten_k_html)
    headings = find_headings(lines, Form.TEN_K)
    assert [h.line_index for h in headings] == sorted(h.line_index for h in headings)
