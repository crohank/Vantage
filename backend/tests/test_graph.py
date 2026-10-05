"""Graph state, routing and the finalize gate.

Offline. Network behaviour lives in the live suite; what matters here is that
the reducers merge concurrent branches correctly and that unverifiable
findings never escape.
"""

import operator

import pytest

from vantage.domain.filing import FilingSection, SectionId, Span
from vantage.domain.finding import ChangeType, Finding, FindingKind, Materiality, Provenance
from vantage.graph.nodes import finalize, needs_novelty, needs_peer, route_after_ingest
from vantage.graph.state import AnalysisState, RequestKind, initial_state

CURRENT = "0000320193-25-000079"
PRIOR = "0000320193-24-000123"


def section(accession: str, text: str = "Two customers accounted for most sales.") -> FilingSection:
    return FilingSection(
        accession=accession,
        cik="0000320193",
        section_id=SectionId.RISK_FACTORS,
        heading="Item 1A. Risk Factors",
        order=0,
        text=text,
    )


def any_span() -> Span:
    return Span.from_section(section(CURRENT), 0, 13)


def finding(span: Span | None, *, kind: FindingKind = FindingKind.DIFF) -> Finding:
    return Finding(
        id=f"test-{id(span)}",
        kind=kind,
        cik="0000320193",
        ticker="AAPL",
        section_id=SectionId.RISK_FACTORS,
        change_type=ChangeType.ADDED if kind is FindingKind.DIFF else None,
        current_span=span,
        materiality=Materiality(score=0.5),
        provenance=Provenance(git_sha="test"),
    )


class TestInitialState:
    def test_accumulating_channels_start_empty(self) -> None:
        state = initial_state("aapl")
        assert state["ticker"] == "AAPL"
        assert state["findings"] == []
        assert state["errors"] == []
        assert state["sections"] == {}

    def test_kind_defaults_to_full(self) -> None:
        assert initial_state("AAPL")["kind"] is RequestKind.FULL


class TestReducerSemantics:
    def test_findings_accumulate_rather_than_overwrite(self) -> None:
        # This is what lets run_diff and measure_attention run concurrently.
        # Under last-write-wins, whichever finished second erased the other,
        # which is exactly how the previous graph lost its parallel results.
        a = [finding(any_span(), kind=FindingKind.NOVELTY)]
        b = [finding(any_span(), kind=FindingKind.PEER)]
        assert len(operator.add(a, b)) == 2

    def test_sections_merge_by_key(self) -> None:
        left = {"a": section(CURRENT)}
        right = {"b": section(PRIOR)}
        assert set(operator.or_(left, right)) == {"a", "b"}


class TestRouting:
    def _state(self, **kw: object) -> AnalysisState:
        base = initial_state("AAPL")
        base.update(kw)  # type: ignore[typeddict-item]
        return base

    def test_diff_only_request_skips_attention(self) -> None:
        # The old graph ran all six nodes on every request regardless of what
        # was asked, which is where most of its runtime went.
        routes = route_after_ingest(
            self._state(kind=RequestKind.DIFF, sections={"a": section(CURRENT)})
        )
        assert routes == ["run_diff"]

    def test_full_request_fans_out(self) -> None:
        routes = route_after_ingest(
            self._state(kind=RequestKind.FULL, sections={"a": section(CURRENT)})
        )
        assert set(routes) == {"run_diff", "measure_attention"}

    def test_ingest_failure_short_circuits_to_finalize(self) -> None:
        routes = route_after_ingest(self._state(errors=["could not fetch filings"], sections={}))
        assert routes == ["finalize"]

    def test_novelty_is_skipped_when_nothing_was_found(self) -> None:
        assert needs_novelty(self._state(kind=RequestKind.FULL, findings=[])) == "finalize"

    def test_novelty_runs_when_there_are_findings(self) -> None:
        state = self._state(kind=RequestKind.FULL, findings=[finding(any_span())])
        assert needs_novelty(state) == "run_novelty"

    def test_diff_only_request_never_reaches_peer(self) -> None:
        assert needs_peer(self._state(kind=RequestKind.DIFF)) == "finalize"

    def test_peer_runs_for_a_full_request(self) -> None:
        assert needs_peer(self._state(kind=RequestKind.PEER)) == "run_peer"


class TestFinalize:
    async def test_keeps_findings_whose_spans_resolve(self) -> None:
        sec = section(CURRENT)
        state = initial_state("AAPL")
        state["sections"] = {sec.key: sec}
        state["findings"] = [finding(Span.from_section(sec, 0, 13))]

        result = await finalize(state)
        assert len(result["final_findings"]) == 1
        assert result["errors"] == []

    async def test_drops_a_finding_whose_span_does_not_resolve(self) -> None:
        # The runtime half of the citation-validity invariant the CI gate
        # enforces. Shipping a finding that cannot quote its source is worse
        # than shipping nothing.
        sec = section(CURRENT)
        tampered = Span(
            accession=CURRENT,
            section_id=SectionId.RISK_FACTORS,
            start=0,
            end=13,
            quote="Ten customers",
        )
        state = initial_state("AAPL")
        state["sections"] = {sec.key: sec}
        state["findings"] = [finding(tampered)]

        result = await finalize(state)
        assert result["final_findings"] == []
        assert "dropped finding" in result["errors"][0]

    async def test_drops_a_finding_referencing_an_unstored_section(self) -> None:
        state = initial_state("AAPL")
        state["sections"] = {}
        state["findings"] = [finding(Span.from_section(section(CURRENT), 0, 13))]

        result = await finalize(state)
        assert result["final_findings"] == []

    async def test_orders_by_materiality(self) -> None:
        sec = section(CURRENT, "A" * 100)
        low = finding(Span.from_section(sec, 0, 10))
        high = finding(Span.from_section(sec, 20, 30))
        object.__setattr__(high, "materiality", Materiality(score=0.9))

        state = initial_state("AAPL")
        state["sections"] = {sec.key: sec}
        state["findings"] = [low, high]

        result = await finalize(state)
        scores = [f.materiality.score for f in result["final_findings"]]
        assert scores == sorted(scores, reverse=True)


class TestGraphAssembly:
    def test_compiles_with_the_expected_nodes(self) -> None:
        from vantage.graph.build import build_graph

        nodes = set(build_graph().nodes)
        assert {
            "resolve_company",
            "ingest_filings",
            "run_diff",
            "run_novelty",
            "run_peer",
            "measure_attention",
            "finalize",
        } <= nodes

    def test_retry_policies_are_attached_to_network_nodes(self) -> None:
        from vantage.graph.build import build_graph

        graph = build_graph()
        for name in ("resolve_company", "ingest_filings", "run_novelty", "run_peer"):
            assert graph.nodes[name].retry_policy, f"{name} should retry"


@pytest.mark.live
class TestLiveRun:
    async def test_end_to_end_diff_against_edgar(self) -> None:
        from vantage.graph.build import RECURSION_LIMIT, get_graph

        graph = await get_graph()
        config = {
            "configurable": {"thread_id": "test-live-aapl"},
            "recursion_limit": RECURSION_LIMIT,
        }
        final = await graph.ainvoke(initial_state("AAPL", RequestKind.DIFF, max_sections=2), config)

        assert final["company"].cik == "0000320193"
        assert final["current_filing"].filing_date > final["prior_filing"].filing_date
        assert final["final_findings"], "a year of Apple filings should differ somewhere"
        # Nothing may be dropped: every emitted span must resolve.
        assert not [e for e in final["errors"] if "dropped finding" in e]
