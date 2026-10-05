"""Graph state.

Uses reducers rather than last-write-wins. The previous graph passed a plain
TypedDict between nodes that each mutated and returned the whole object, which
forced parallelism to happen inside a single node via ThreadPoolExecutor over
deep copies. That discarded every field the copies wrote apart from two, and
was the direct cause of the sentiment agent never running for the life of the
project.

With `operator.add` on the accumulating channels, nodes can genuinely fan out:
each returns only its own contribution and LangGraph merges them.
"""

from __future__ import annotations

import operator
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Any, TypedDict

from vantage.domain.attention import AttentionScore
from vantage.domain.filing import Company, Filing, FilingSection
from vantage.domain.finding import Finding


class RequestKind(StrEnum):
    """What the caller asked for.

    Drives conditional routing. Running every engine on every request is what
    the old graph did, and most of it was wasted: a document lookup does not
    need peer analysis.
    """

    DIFF = "diff"
    NOVELTY = "novelty"
    PEER = "peer"
    FULL = "full"


class NodeTiming(TypedDict):
    node: str
    seconds: float


class AnalysisState(TypedDict, total=False):
    """Channels flowing through the graph.

    Accumulating channels are annotated with a reducer. Everything else is
    last-write-wins, which is correct for inputs and for single-writer fields.
    """

    # Inputs, written once by the caller.
    ticker: str
    kind: RequestKind
    max_sections: int
    include_cosmetic: bool
    requested_at: datetime

    # Resolution.
    company: Company | None
    current_filing: Filing | None
    prior_filing: Filing | None

    # Ingest. Keyed by FilingSection.key so both sides of a diff are
    # addressable and spans can be verified against the exact stored text.
    sections: Annotated[dict[str, FilingSection], operator.or_]

    # Engine output. Every engine appends; none overwrite.
    findings: Annotated[list[Finding], operator.add]

    # The authoritative, verified, ranked list. Deliberately a separate
    # channel with no reducer: `findings` accumulates and cannot be replaced,
    # so the node that filters unverifiable spans needs somewhere to write a
    # result rather than another contribution to append.
    final_findings: list[Finding]

    # Attention, resolved once per run rather than per finding.
    attention: AttentionScore | None

    # Human-in-the-loop. Set when a reviewer accepts or rejects, which also
    # produces labelled data for the eval suite.
    review_decisions: Annotated[dict[str, str], operator.or_]

    # Diagnostics. Errors accumulate rather than replacing, so a partial
    # failure is visible in the response instead of being swallowed by a
    # broad except that returns a plausible-looking empty result.
    errors: Annotated[list[str], operator.add]
    timings: Annotated[list[NodeTiming], operator.add]
    llm_calls: Annotated[list[dict[str, Any]], operator.add]


def initial_state(
    ticker: str,
    kind: RequestKind = RequestKind.FULL,
    *,
    max_sections: int = 4,
    include_cosmetic: bool = False,
) -> AnalysisState:
    return AnalysisState(
        ticker=ticker.upper(),
        kind=kind,
        max_sections=max_sections,
        include_cosmetic=include_cosmetic,
        requested_at=datetime.now(UTC),
        company=None,
        current_filing=None,
        prior_filing=None,
        sections={},
        findings=[],
        final_findings=[],
        attention=None,
        review_decisions={},
        errors=[],
        timings=[],
        llm_calls=[],
    )


def filing_label(filing: Filing | None) -> str:
    return filing.fiscal_label if filing else "unknown"


def as_of(state: AnalysisState) -> date:
    filing = state.get("current_filing")
    return filing.filing_date if filing else datetime.now(UTC).date()
