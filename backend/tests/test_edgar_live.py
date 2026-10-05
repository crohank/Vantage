"""Tests that hit the real SEC API.

Excluded from the default run (see `addopts` in pyproject) because they need
network access and count against SEC's rate limit. Run explicitly:

    pytest -m live
"""

import pytest

from vantage.domain.filing import Form, SectionId
from vantage.ingest.edgar import EdgarClient
from vantage.ingest.parser import extract_sections

pytestmark = [pytest.mark.live, pytest.mark.asyncio]

# Sections every large-filer 10-K carries, used to catch parser regressions
# against documents we do not control.
_EXPECTED = {
    SectionId.BUSINESS,
    SectionId.RISK_FACTORS,
    SectionId.MDA,
    SectionId.FINANCIAL_STATEMENTS,
}


async def test_resolves_ticker_to_cik() -> None:
    async with EdgarClient() as ec:
        company = await ec.get_company("AAPL")
    assert company is not None
    assert company.cik == "0000320193"


async def test_full_text_search_returns_usable_hits() -> None:
    # Regression for the dead EFTS path: the old client read `_source.file_num`
    # as the accession and `_source.file_url` for the location. Neither field
    # means what it was assumed to mean, so every search fell through.
    async with EdgarClient() as ec:
        result = await ec.full_text_search("customer concentration", forms="10-K", limit=3)
    assert result.total > 0
    assert result.hits
    for hit in result.hits:
        assert len(hit.accession) == 20, "accession should be dashed 18-digit form"
        assert hit.document_url.startswith("https://www.sec.gov/Archives/")


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT"])
async def test_real_ten_k_parses_into_canonical_sections(ticker: str) -> None:
    async with EdgarClient() as ec:
        filings = await ec.list_filings(ticker, Form.TEN_K, limit=1)
        assert filings, f"no 10-K found for {ticker}"
        raw = await ec.fetch_document(filings[0].primary_doc_url)

    sections = {s.section_id: s for s in extract_sections(filings[0], raw)}
    assert sections.keys() >= _EXPECTED, f"missing {_EXPECTED - sections.keys()}"

    # The previous pipeline truncated every section to 5,000 characters, which
    # is roughly a fifteenth of a real Item 1A and made diffing pointless.
    assert len(sections[SectionId.RISK_FACTORS].text) > 20_000

    # Item 1B is a one-word section in practice. Anything large means a later
    # unmapped item bled into it.
    if SectionId.UNRESOLVED_STAFF_COMMENTS in sections:
        assert len(sections[SectionId.UNRESOLVED_STAFF_COMMENTS].text) < 500
