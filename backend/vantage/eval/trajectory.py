"""Trajectory evaluation.

Scoring only the final output hides most of what goes wrong in an agent.
A run can return a plausible list of findings while having skipped the
verification step, re-run a node, or quietly taken the expensive path for a
request that did not need it. None of that shows up in the findings.

So this scores the path: which nodes ran, in what order, how many times, and
whether the ones that must run did. It needs no model and no network, which
is what lets it gate every pull request.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from vantage.graph.state import RequestKind

# Nodes that must run on every path. finalize is the citation gate, so a run
# that skips it has not verified anything it is about to return.
ALWAYS_REQUIRED = frozenset({"resolve_company", "ingest_filings", "finalize"})


@dataclass(frozen=True)
class Trajectory:
    """The path one run actually took."""

    nodes: tuple[str, ...]
    seconds: float

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> Trajectory:
        timings = state.get("timings", [])
        return cls(
            nodes=tuple(t["node"] for t in timings),
            seconds=round(sum(t["seconds"] for t in timings), 3),
        )

    @property
    def counts(self) -> Counter[str]:
        return Counter(self.nodes)

    @property
    def repeated(self) -> dict[str, int]:
        """Nodes that ran more than once.

        Every node in this graph is single-shot, so a repeat means a retry
        fired or an edge is wrong. Either is worth failing on.
        """
        return {node: n for node, n in self.counts.items() if n > 1}


@dataclass(frozen=True)
class TrajectorySpec:
    """What a given request kind is supposed to do."""

    kind: RequestKind
    required: frozenset[str]
    forbidden: frozenset[str] = frozenset()
    max_nodes: int = 12

    def check(self, trajectory: Trajectory) -> list[str]:
        """Violations, empty when the path is correct."""
        ran = set(trajectory.nodes)
        problems: list[str] = []

        for node in sorted((self.required | ALWAYS_REQUIRED) - ran):
            problems.append(f"required node did not run: {node}")

        for node in sorted(self.forbidden & ran):
            problems.append(f"node ran for a {self.kind.value} request but should not: {node}")

        for node, n in sorted(trajectory.repeated.items()):
            problems.append(f"node ran {n} times, expected once: {node}")

        if len(trajectory.nodes) > self.max_nodes:
            problems.append(
                f"path was {len(trajectory.nodes)} nodes, over the {self.max_nodes} budget"
            )

        # finalize is the citation gate, so anything generative must come
        # after it. Explaining an unverified span is exactly the ordering
        # this project exists to prevent.
        if (
            "explain_findings" in ran
            and "finalize" in ran
            and trajectory.nodes.index("explain_findings") < trajectory.nodes.index("finalize")
        ):
            problems.append("explain_findings ran before finalize, on unverified spans")

        return problems


# A diff request must not pay for the expensive optional work. The previous
# graph ran all six nodes on every request regardless of what was asked.
SPECS: dict[RequestKind, TrajectorySpec] = {
    RequestKind.DIFF: TrajectorySpec(
        kind=RequestKind.DIFF,
        required=frozenset({"run_diff"}),
        forbidden=frozenset({"run_novelty", "run_peer", "measure_attention"}),
        max_nodes=6,
    ),
    RequestKind.NOVELTY: TrajectorySpec(
        kind=RequestKind.NOVELTY,
        required=frozenset({"run_diff"}),
        forbidden=frozenset({"run_peer"}),
        max_nodes=8,
    ),
    RequestKind.PEER: TrajectorySpec(
        kind=RequestKind.PEER,
        required=frozenset({"run_diff"}),
        max_nodes=9,
    ),
    RequestKind.FULL: TrajectorySpec(
        kind=RequestKind.FULL,
        required=frozenset({"run_diff", "measure_attention"}),
        max_nodes=12,
    ),
}


@dataclass
class TrajectoryReport:
    """Results across several runs."""

    rows: list[tuple[RequestKind, Trajectory, list[str]]] = field(default_factory=list)

    def add(self, kind: RequestKind, trajectory: Trajectory) -> list[str]:
        problems = SPECS[kind].check(trajectory)
        self.rows.append((kind, trajectory, problems))
        return problems

    @property
    def passed(self) -> bool:
        return all(not problems for _, _, problems in self.rows)

    def render(self) -> str:
        lines = ["", "trajectories:"]
        for kind, trajectory, problems in self.rows:
            mark = "ok  " if not problems else "FAIL"
            lines.append(
                f"  {mark} {kind.value:8} {trajectory.seconds:6.2f}s  "
                + " -> ".join(trajectory.nodes)
            )
            lines.extend(f"         {p}" for p in problems)
        lines.append("")
        lines.append("PASSED" if self.passed else "FAILED")
        return "\n".join(lines)


def check_state(kind: RequestKind, state: dict[str, Any]) -> list[str]:
    """Convenience for checking one completed run."""
    return SPECS[kind].check(Trajectory.from_state(state))
