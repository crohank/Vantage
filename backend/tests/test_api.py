"""HTTP surface.

Offline. The graph is replaced with a fake, so these cover the contract
rather than the analysis: status codes, validation, auth, and the guarantee
that a stream always terminates.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any

import httpx
import pytest

from vantage.api import jobs as jobs_module
from vantage.api.app import app
from vantage.api.jobs import JobStatus, get_runner, reset_runner
from vantage.config import get_settings
from vantage.domain.filing import Company, Filing, FilingSection, Form, SectionId, Span
from vantage.domain.finding import ChangeType, Finding, FindingKind, Materiality, Provenance

ACCESSION = "0000320193-25-000079"
SECTION_TEXT = "Two customers accounted for a majority of net sales."


def _section() -> FilingSection:
    return FilingSection(
        accession=ACCESSION,
        cik="0000320193",
        section_id=SectionId.RISK_FACTORS,
        heading="Item 1A. Risk Factors",
        order=0,
        text=SECTION_TEXT,
    )


def _finding(section: FilingSection) -> Finding:
    return Finding(
        id="f-1",
        kind=FindingKind.DIFF,
        cik="0000320193",
        ticker="AAPL",
        section_id=SectionId.RISK_FACTORS,
        change_type=ChangeType.ADDED,
        current_span=Span.from_section(section, 0, 13),
        current_accession=ACCESSION,
        materiality=Materiality(score=0.8, reasons=["customer concentration"]),
        provenance=Provenance(git_sha="test"),
    )


def _filing(accession: str, year: int) -> Filing:
    return Filing(
        accession=accession,
        cik="0000320193",
        ticker="AAPL",
        form=Form.TEN_K,
        filing_date=dt.date(year, 11, 1),
        period_of_report=dt.date(year, 9, 28),
        primary_doc_url=f"https://example.test/{accession}.htm",
    )


class FakeSnapshot:
    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values


class FakeGraph:
    """Emits the node events a real run would, without the network."""

    def __init__(self, *, fail: bool = False, slow: bool = False) -> None:
        self.fail = fail
        self.slow = slow
        self.checkpointer = object()
        section = _section()
        self._values = {
            "company": Company(cik="0000320193", ticker="AAPL", name="Apple Inc.", sic="3571"),
            "current_filing": _filing(ACCESSION, 2025),
            "prior_filing": _filing("0000320193-24-000123", 2024),
            "sections": {section.key: section},
            "final_findings": [_finding(section)],
            "errors": [],
            "timings": [{"node": "run_diff", "seconds": 1.5}],
            "attention": None,
        }

    async def astream_events(self, state: Any, config: Any, version: str = "v2") -> Any:
        if self.fail:
            raise RuntimeError("EDGAR is unreachable")
        for node in ("resolve_company", "run_diff", "finalize"):
            if self.slow:
                await asyncio.sleep(0.01)
            yield {"event": "on_chain_start", "name": node}
            yield {"event": "on_chain_end", "name": node}

    async def aget_state(self, config: Any) -> FakeSnapshot:
        return FakeSnapshot(self._values)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_runner()
    get_settings.cache_clear()
    monkeypatch.delenv("VANTAGE_API_KEY", raising=False)


@pytest.fixture
def fake_graph(monkeypatch: pytest.MonkeyPatch) -> FakeGraph:
    graph = FakeGraph()

    async def _get_graph() -> FakeGraph:
        return graph

    monkeypatch.setattr(jobs_module, "get_graph", _get_graph)
    monkeypatch.setattr("vantage.api.app.get_graph", _get_graph)
    return graph


async def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30
    )


async def _await_terminal(job_id: str, limit_seconds: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + limit_seconds
    while asyncio.get_running_loop().time() < deadline:
        job = get_runner().get(job_id)
        if job and job.is_terminal:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"job {job_id} never reached a terminal state")


class TestHealth:
    async def test_reports_checkpointer_and_sha(self, fake_graph: FakeGraph) -> None:
        async with await _client() as c:
            body = (await c.get("/health")).json()
        assert body["status"] == "ok"
        assert "checkpointer" in body


class TestSubmit:
    async def test_returns_202_and_a_job_reference(self, fake_graph: FakeGraph) -> None:
        # 202 rather than 200: the work is accepted, not finished.
        async with await _client() as c:
            r = await c.post("/analyses", json={"ticker": "aapl"})
        assert r.status_code == 202
        body = r.json()
        assert body["ticker"] == "AAPL"
        assert body["stream_url"].endswith("/stream")

    @pytest.mark.parametrize("ticker", ["", "TOOLONG", "not a ticker", "AA PL", "123"])
    async def test_rejects_anything_that_is_not_a_ticker(
        self, fake_graph: FakeGraph, ticker: str
    ) -> None:
        # Rejecting at the edge keeps junk out of the EDGAR rate limiter and
        # out of the attention sources' daily quotas.
        async with await _client() as c:
            r = await c.post("/analyses", json={"ticker": ticker})
        assert r.status_code == 422

    async def test_rejects_an_out_of_range_section_count(self, fake_graph: FakeGraph) -> None:
        async with await _client() as c:
            r = await c.post("/analyses", json={"ticker": "AAPL", "max_sections": 99})
        assert r.status_code == 422


class TestResult:
    async def test_completed_job_carries_findings_and_filings(self, fake_graph: FakeGraph) -> None:
        async with await _client() as c:
            job_id = (await c.post("/analyses", json={"ticker": "AAPL"})).json()["job_id"]
            await _await_terminal(job_id)
            body = (await c.get(f"/analyses/{job_id}")).json()

        assert body["status"] == "succeeded"
        assert body["company_name"] == "Apple Inc."
        # fiscal_label is derived, so it has to be a computed field to serialize.
        assert body["current_filing"]["fiscal_label"] == "FY2025"
        assert len(body["findings"]) == 1
        assert body["findings"][0]["materiality"]["band"] == "high"

    async def test_unknown_job_is_404(self, fake_graph: FakeGraph) -> None:
        async with await _client() as c:
            assert (await c.get("/analyses/nope")).status_code == 404

    async def test_a_failed_run_reports_the_error_rather_than_an_empty_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The previous system answered every failure with a plausible-looking
        # default, which is how a hardcoded sentiment string shipped for years.
        async def _get_graph() -> FakeGraph:
            return FakeGraph(fail=True)

        monkeypatch.setattr(jobs_module, "get_graph", _get_graph)
        monkeypatch.setattr("vantage.api.app.get_graph", _get_graph)

        async with await _client() as c:
            job_id = (await c.post("/analyses", json={"ticker": "AAPL"})).json()["job_id"]
            await _await_terminal(job_id)
            body = (await c.get(f"/analyses/{job_id}")).json()

        assert body["status"] == "failed"
        job = get_runner().get(job_id)
        assert job is not None and "unreachable" in (job.error or "")


class TestStream:
    async def test_emits_node_events_and_always_terminates(self, fake_graph: FakeGraph) -> None:
        # The previous SSE implementation could end without a terminal event,
        # leaving the UI spinning forever with nothing shown.
        async with await _client() as c:
            job = (await c.post("/analyses", json={"ticker": "AAPL"})).json()
            seen: list[str] = []
            async with c.stream("GET", job["stream_url"]) as s:
                async for line in s.aiter_lines():
                    if line.startswith("event: "):
                        seen.append(line.removeprefix("event: "))
                    if line.startswith("event: result"):
                        break

        assert "node_start" in seen
        assert "complete" in seen
        assert seen[-1] == "result"

    async def test_a_late_consumer_still_sees_the_whole_run(self, fake_graph: FakeGraph) -> None:
        async with await _client() as c:
            job = (await c.post("/analyses", json={"ticker": "AAPL"})).json()
            await _await_terminal(job["job_id"])

            seen: list[str] = []
            async with c.stream("GET", job["stream_url"]) as s:
                async for line in s.aiter_lines():
                    if line.startswith("event: "):
                        seen.append(line.removeprefix("event: "))

        assert "complete" in seen, "history should replay for a consumer that attaches late"

    async def test_stream_of_an_unknown_job_is_404(self, fake_graph: FakeGraph) -> None:
        async with await _client() as c:
            assert (await c.get("/analyses/nope/stream")).status_code == 404


class TestSections:
    async def test_returns_the_text_a_span_resolves_against(self, fake_graph: FakeGraph) -> None:
        # This endpoint is what makes a citation checkable in the UI.
        async with await _client() as c:
            job_id = (await c.post("/analyses", json={"ticker": "AAPL"})).json()["job_id"]
            await _await_terminal(job_id)
            result = (await c.get(f"/analyses/{job_id}")).json()
            span = result["findings"][0]["current_span"]
            section = (
                await c.get(f"/analyses/{job_id}/sections/{span['accession']}/{span['section_id']}")
            ).json()

        assert section["text"][span["start"] : span["end"]] == span["quote"]

    async def test_unknown_section_is_404(self, fake_graph: FakeGraph) -> None:
        async with await _client() as c:
            job_id = (await c.post("/analyses", json={"ticker": "AAPL"})).json()["job_id"]
            await _await_terminal(job_id)
            r = await c.get(f"/analyses/{job_id}/sections/nope/item_1a_risk_factors")
        assert r.status_code == 404


class TestAuth:
    async def test_open_when_no_key_is_configured(self, fake_graph: FakeGraph) -> None:
        async with await _client() as c:
            assert (await c.get("/analyses")).status_code == 200

    async def test_rejects_a_missing_key_when_one_is_configured(
        self, fake_graph: FakeGraph, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VANTAGE_API_KEY", "s3cret")
        get_settings.cache_clear()
        async with await _client() as c:
            assert (await c.get("/analyses")).status_code == 401
            ok = await c.get("/analyses", headers={"X-API-Key": "s3cret"})
            assert ok.status_code == 200
        get_settings.cache_clear()


class TestCancel:
    async def test_cancelling_a_finished_job_is_a_conflict(self, fake_graph: FakeGraph) -> None:
        async with await _client() as c:
            job_id = (await c.post("/analyses", json={"ticker": "AAPL"})).json()["job_id"]
            await _await_terminal(job_id)
            r = await c.delete(f"/analyses/{job_id}")
        assert r.status_code == 409


class TestJobRetention:
    async def test_running_jobs_are_never_evicted(self, fake_graph: FakeGraph) -> None:
        runner = get_runner()
        job = runner.submit("AAPL", jobs_module.RequestKind.DIFF, 2)
        job.status = JobStatus.RUNNING
        for _ in range(jobs_module.MAX_RETAINED_JOBS + 5):
            filler = runner.submit("MSFT", jobs_module.RequestKind.DIFF, 2)
            filler.status = JobStatus.SUCCEEDED
        runner._evict()
        assert runner.get(job.id) is not None
