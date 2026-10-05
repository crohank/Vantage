"""Trajectory scoring.

Offline. These encode what each request kind is allowed to do, so a routing
regression that still returns plausible findings fails here instead of
shipping.
"""

from __future__ import annotations

import pytest

from vantage.eval.trajectory import (
    SPECS,
    Trajectory,
    TrajectoryReport,
    check_state,
)
from vantage.graph.state import RequestKind

DIFF_PATH = ("resolve_company", "ingest_filings", "run_diff", "finalize", "explain_findings")
FULL_PATH = (
    "resolve_company",
    "ingest_filings",
    "measure_attention",
    "run_diff",
    "run_novelty",
    "run_peer",
    "finalize",
    "explain_findings",
)


def traj(*nodes: str, seconds: float = 1.0) -> Trajectory:
    return Trajectory(nodes=nodes, seconds=seconds)


def state(*nodes: str) -> dict[str, object]:
    return {"timings": [{"node": n, "seconds": 0.5} for n in nodes]}


class TestTrajectory:
    def test_reads_a_path_out_of_a_completed_run(self) -> None:
        t = Trajectory.from_state(state(*DIFF_PATH))
        assert t.nodes == DIFF_PATH
        assert t.seconds == pytest.approx(2.5)

    def test_detects_a_repeated_node(self) -> None:
        # Every node here is single-shot, so a repeat means a retry fired or
        # an edge is wrong.
        t = traj("resolve_company", "run_diff", "run_diff", "finalize")
        assert t.repeated == {"run_diff": 2}

    def test_a_clean_path_repeats_nothing(self) -> None:
        assert traj(*DIFF_PATH).repeated == {}


class TestSpecs:
    def test_a_correct_diff_path_passes(self) -> None:
        assert SPECS[RequestKind.DIFF].check(traj(*DIFF_PATH)) == []

    def test_a_correct_full_path_passes(self) -> None:
        assert SPECS[RequestKind.FULL].check(traj(*FULL_PATH)) == []

    def test_a_diff_request_may_not_run_the_expensive_nodes(self) -> None:
        # The previous graph ran all six nodes on every request regardless
        # of what was asked, which is where most of its runtime went.
        problems = SPECS[RequestKind.DIFF].check(
            traj("resolve_company", "ingest_filings", "run_diff", "run_peer", "finalize")
        )
        assert any("run_peer" in p for p in problems)

    def test_skipping_the_citation_gate_fails(self) -> None:
        # A run that skips finalize has verified nothing it is about to
        # return, however plausible the findings look.
        problems = SPECS[RequestKind.DIFF].check(
            traj("resolve_company", "ingest_filings", "run_diff")
        )
        assert any("finalize" in p for p in problems)

    def test_explaining_before_verifying_fails(self) -> None:
        # Generative work on spans that have not been checked is exactly the
        # ordering this project exists to prevent.
        problems = SPECS[RequestKind.DIFF].check(
            traj("resolve_company", "ingest_filings", "run_diff", "explain_findings", "finalize")
        )
        assert any("before finalize" in p for p in problems)

    def test_a_missing_required_node_fails(self) -> None:
        problems = SPECS[RequestKind.FULL].check(
            traj("resolve_company", "ingest_filings", "run_diff", "finalize")
        )
        assert any("measure_attention" in p for p in problems)

    def test_an_overlong_path_fails_the_budget(self) -> None:
        problems = SPECS[RequestKind.DIFF].check(traj(*DIFF_PATH, *DIFF_PATH))
        assert any("budget" in p for p in problems)

    def test_a_loop_is_caught(self) -> None:
        problems = SPECS[RequestKind.DIFF].check(
            traj("resolve_company", "ingest_filings", "run_diff", "run_diff", "finalize")
        )
        assert any("expected once" in p for p in problems)

    @pytest.mark.parametrize("kind", list(RequestKind))
    def test_every_request_kind_has_a_spec(self, kind: RequestKind) -> None:
        assert kind in SPECS


class TestReport:
    def test_passes_when_every_row_is_clean(self) -> None:
        report = TrajectoryReport()
        report.add(RequestKind.DIFF, traj(*DIFF_PATH))
        report.add(RequestKind.FULL, traj(*FULL_PATH))
        assert report.passed
        assert "PASSED" in report.render()

    def test_fails_and_names_the_violation(self) -> None:
        report = TrajectoryReport()
        report.add(RequestKind.DIFF, traj("resolve_company", "run_diff"))
        assert not report.passed
        rendered = report.render()
        assert "FAILED" in rendered
        assert "finalize" in rendered


class TestCheckState:
    def test_accepts_a_completed_run(self) -> None:
        assert check_state(RequestKind.DIFF, state(*DIFF_PATH)) == []

    def test_rejects_one_that_skipped_verification(self) -> None:
        assert check_state(RequestKind.DIFF, state("resolve_company", "ingest_filings", "run_diff"))
