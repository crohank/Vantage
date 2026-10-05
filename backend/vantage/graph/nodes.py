"""Graph nodes.

Each returns only the channels it wrote, so LangGraph can merge concurrent
branches through the reducers on the state. None of them mutate and return the
whole state, which is what made the previous graph impossible to parallelise.

Failures are recorded on the `errors` channel and surfaced in the response
rather than swallowed. The old code answered every exception with a printed
warning and a plausible-looking default, which is how a hardcoded sentiment
string shipped in every memo for the life of the project.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from vantage.config import get_settings
from vantage.domain.filing import FilingPair, Form, SectionId
from vantage.domain.finding import Finding, FindingKind, Materiality, Provenance
from vantage.engines.diff import diff_sections, score_materiality
from vantage.engines.novelty import find_novel_phrases
from vantage.engines.peer import peer_adoption
from vantage.graph.state import AnalysisState, NodeTiming, RequestKind
from vantage.ingest.edgar import EdgarClient, EdgarError
from vantage.ingest.parser import extract_sections

log = logging.getLogger(__name__)

# Sections worth diffing, most interesting first. Item 1B is one word in
# practice and Properties rarely moves.
PRIORITY_SECTIONS = (
    SectionId.RISK_FACTORS,
    SectionId.MDA,
    SectionId.LEGAL_PROCEEDINGS,
    SectionId.CYBERSECURITY,
    SectionId.BUSINESS,
    SectionId.CONTROLS,
)

# Novelty and peer checks each cost rate-limited EDGAR requests, so they run
# only against the findings most likely to matter.
NOVELTY_CANDIDATES = 3
PEER_CANDIDATES = 2

# How far back the peer window looks. One quarter catches an industry-wide
# addition without dragging in last year's language.
PEER_WINDOW_DAYS = 120


@asynccontextmanager
async def _edgar() -> AsyncIterator[EdgarClient]:
    async with EdgarClient() as client:
        yield client


def _timed(name: str, started: float) -> list[NodeTiming]:
    return [NodeTiming(node=name, seconds=round(time.monotonic() - started, 3))]


async def resolve_company(state: AnalysisState) -> dict[str, Any]:
    """Ticker to CIK, and the two most recent comparable annual filings."""
    started = time.monotonic()
    ticker = state["ticker"]

    try:
        async with _edgar() as edgar:
            company = await edgar.get_company(ticker)
            if company is None:
                return {
                    "errors": [f"no SEC filer matches ticker {ticker}"],
                    "timings": _timed("resolve_company", started),
                }
            # The submissions profile carries SIC, which the peer engine needs
            # and the ticker map does not include.
            profile = await edgar.get_company_profile(company.cik) or company
            filings = await edgar.list_filings(ticker, Form.TEN_K, limit=2)
    except EdgarError as exc:
        return {
            "errors": [f"EDGAR lookup failed for {ticker}: {exc}"],
            "timings": _timed("resolve_company", started),
        }

    if len(filings) < 2:
        return {
            "company": profile,
            "current_filing": filings[0] if filings else None,
            "errors": [
                f"{ticker} has {len(filings)} annual filing(s) on EDGAR, "
                "so there is nothing to diff against"
            ],
            "timings": _timed("resolve_company", started),
        }

    return {
        "company": profile,
        "current_filing": filings[0],
        "prior_filing": filings[1],
        "timings": _timed("resolve_company", started),
    }


async def ingest_filings(state: AnalysisState) -> dict[str, Any]:
    """Fetch and parse both filings, untruncated.

    Both documents are fetched concurrently. They are 1.5 MB each and the
    rate limiter paces them, so serialising costs a second for nothing.
    """
    started = time.monotonic()
    current, prior = state.get("current_filing"), state.get("prior_filing")
    if current is None or prior is None:
        return {"timings": _timed("ingest_filings", started)}

    try:
        async with _edgar() as edgar:
            raw_current, raw_prior = await asyncio.gather(
                edgar.fetch_document(current.primary_doc_url),
                edgar.fetch_document(prior.primary_doc_url),
            )
    except EdgarError as exc:
        return {
            "errors": [f"could not fetch filings: {exc}"],
            "timings": _timed("ingest_filings", started),
        }

    sections = {}
    for filing, raw in ((current, raw_current), (prior, raw_prior)):
        parsed = extract_sections(filing, raw)
        if not parsed:
            return {
                "errors": [f"no sections parsed from {filing.accession}"],
                "timings": _timed("ingest_filings", started),
            }
        for section in parsed:
            sections[section.key] = section

    return {"sections": sections, "timings": _timed("ingest_filings", started)}


async def run_diff(state: AnalysisState) -> dict[str, Any]:
    """Align every shared priority section and emit findings."""
    started = time.monotonic()
    current, prior = state.get("current_filing"), state.get("prior_filing")
    sections = state.get("sections") or {}
    company = state.get("company")
    if current is None or prior is None or company is None:
        return {"timings": _timed("run_diff", started)}

    # Refuse to diff across forms. A 10-K and a 10-Q number their items
    # differently, so the comparison would be noise.
    try:
        FilingPair(current=current, prior=prior)
    except ValueError as exc:
        return {"errors": [str(exc)], "timings": _timed("run_diff", started)}

    settings = get_settings()
    provenance = Provenance(git_sha=settings.git_sha)
    findings: list[Finding] = []
    limit = state.get("max_sections", 4)

    for section_id in PRIORITY_SECTIONS[:limit]:
        new = sections.get(f"{current.accession}:{section_id.value}")
        old = sections.get(f"{prior.accession}:{section_id.value}")
        if new is None or old is None:
            continue
        for change in diff_sections(
            old, new, include_cosmetic=state.get("include_cosmetic", False)
        ):
            anchor = change.current_span or change.prior_span
            if anchor is None:
                continue
            findings.append(
                Finding(
                    id=Finding.make_id(
                        FindingKind.DIFF,
                        anchor.accession,
                        section_id,
                        anchor.start,
                        anchor.end,
                        change.change_type.value,
                    ),
                    kind=FindingKind.DIFF,
                    cik=company.cik,
                    ticker=company.ticker,
                    section_id=section_id,
                    change_type=change.change_type,
                    current_span=change.current_span,
                    prior_span=change.prior_span,
                    current_accession=current.accession,
                    prior_accession=prior.accession,
                    materiality=score_materiality(change),
                    provenance=provenance,
                )
            )

    return {"findings": findings, "timings": _timed("run_diff", started)}


async def run_novelty(state: AnalysisState) -> dict[str, Any]:
    """Check whether the most material additions say something new.

    Only the top few findings are checked. Each phrase costs two rate-limited
    EDGAR requests and a single added paragraph yields dozens of candidates.
    """
    started = time.monotonic()
    company = state.get("company")
    current = state.get("current_filing")
    sections = state.get("sections") or {}
    if company is None or current is None:
        return {"timings": _timed("run_novelty", started)}

    from vantage.domain.finding import ChangeType

    candidates = sorted(
        (
            f
            for f in state.get("findings", [])
            if f.change_type is ChangeType.ADDED and f.current_span is not None
        ),
        key=lambda f: f.materiality.score,
        reverse=True,
    )[:NOVELTY_CANDIDATES]

    if not candidates:
        return {"timings": _timed("run_novelty", started)}

    provenance = Provenance(git_sha=get_settings().git_sha)
    findings: list[Finding] = []

    try:
        async with _edgar() as edgar:
            for finding in candidates:
                span = finding.current_span
                assert span is not None
                prior_section = sections.get(
                    f"{state['prior_filing'].accession}:{finding.section_id.value}"  # type: ignore[union-attr]
                )
                prior_text = prior_section.text if prior_section else ""
                results = await find_novel_phrases(
                    edgar,
                    span.quote,
                    prior_text,
                    cik=company.cik,
                    as_of=current.filing_date,
                    sic=company.sic,
                    max_checks=2,
                )
                for result in results:
                    if not result.is_notable:
                        continue
                    findings.append(
                        Finding(
                            id=Finding.make_id(
                                FindingKind.NOVELTY,
                                span.accession,
                                finding.section_id,
                                span.start,
                                span.end,
                                result.phrase,
                            ),
                            kind=FindingKind.NOVELTY,
                            cik=company.cik,
                            ticker=company.ticker,
                            section_id=finding.section_id,
                            current_span=span,
                            current_accession=current.accession,
                            novelty_phrase=result.phrase,
                            novelty_first_seen=(
                                result.filer_first_used.isoformat()
                                if result.filer_first_used
                                else None
                            ),
                            novelty_searched_since=2001,
                            summary=result.describe(),
                            materiality=Materiality(
                                score=min(1.0, finding.materiality.score + 0.1),
                                reasons=[*finding.materiality.reasons, "first use by this filer"],
                            ),
                            provenance=provenance,
                        )
                    )
    except EdgarError as exc:
        return {
            "errors": [f"novelty check failed: {exc}"],
            "timings": _timed("run_novelty", started),
        }

    return {"findings": findings, "timings": _timed("run_novelty", started)}


async def run_peer(state: AnalysisState) -> dict[str, Any]:
    """Check whether peers made the same change in the same window."""
    started = time.monotonic()
    company = state.get("company")
    current = state.get("current_filing")
    if company is None or current is None or not company.sic:
        return {"timings": _timed("run_peer", started)}

    novel = [f for f in state.get("findings", []) if f.kind is FindingKind.NOVELTY]
    candidates = sorted(novel, key=lambda f: f.materiality.score, reverse=True)[:PEER_CANDIDATES]
    if not candidates:
        return {"timings": _timed("run_peer", started)}

    provenance = Provenance(git_sha=get_settings().git_sha)
    window_start = current.filing_date - timedelta(days=PEER_WINDOW_DAYS)
    findings: list[Finding] = []

    try:
        async with _edgar() as edgar:
            for finding in candidates:
                phrase = finding.novelty_phrase
                span = finding.current_span
                if not phrase or span is None:
                    continue
                adoption = await peer_adoption(
                    edgar,
                    phrase,
                    start=window_start,
                    end=current.filing_date,
                    sic=company.sic,
                    form=Form.TEN_K.value,
                )
                if not adoption.is_sector_wide:
                    continue
                findings.append(
                    Finding(
                        id=Finding.make_id(
                            FindingKind.PEER,
                            span.accession,
                            finding.section_id,
                            span.start,
                            span.end,
                            phrase,
                        ),
                        kind=FindingKind.PEER,
                        cik=company.cik,
                        ticker=company.ticker,
                        section_id=finding.section_id,
                        current_span=span,
                        current_accession=current.accession,
                        novelty_phrase=phrase,
                        peer_ciks=[a.cik for a in adoption.adopters[:10]],
                        peer_total=adoption.sic_filings,
                        summary=adoption.describe(),
                        materiality=finding.materiality,
                        provenance=provenance,
                    )
                )
    except EdgarError as exc:
        return {"errors": [f"peer check failed: {exc}"], "timings": _timed("run_peer", started)}

    return {"findings": findings, "timings": _timed("run_peer", started)}


async def measure_attention(state: AnalysisState) -> dict[str, Any]:
    """How much public discussion the ticker is drawing right now.

    Resolved once per run rather than per finding: the sources are keyed by
    ticker, and the free tiers have daily caps measured in the dozens.
    """
    started = time.monotonic()
    company = state.get("company")
    if company is None:
        return {"timings": _timed("measure_attention", started)}

    from vantage.attention.score import score_attention

    try:
        score = await score_attention(company.ticker, company.name, window_days=14)
    except Exception as exc:
        # Attention is additive. A total failure must not sink an analysis
        # whose filing findings are already valid.
        log.warning("attention scoring failed for %s: %s", company.ticker, exc)
        return {
            "errors": [f"attention unavailable: {exc}"],
            "timings": _timed("measure_attention", started),
        }

    return {"attention": score, "timings": _timed("measure_attention", started)}


def route_after_ingest(state: AnalysisState) -> list[str]:
    """Fan out to whichever engines the request actually needs.

    The previous graph ran all six nodes on every request regardless of what
    was asked, which is where most of its runtime went.
    """
    if state.get("errors") and not state.get("sections"):
        return ["finalize"]

    kind = state.get("kind", RequestKind.FULL)
    if kind is RequestKind.DIFF:
        return ["run_diff"]
    return ["run_diff", "measure_attention"]


def needs_novelty(state: AnalysisState) -> str:
    kind = state.get("kind", RequestKind.FULL)
    if kind in (RequestKind.NOVELTY, RequestKind.PEER, RequestKind.FULL) and state.get("findings"):
        return "run_novelty"
    return "finalize"


def needs_peer(state: AnalysisState) -> str:
    kind = state.get("kind", RequestKind.FULL)
    if kind in (RequestKind.PEER, RequestKind.FULL):
        return "run_peer"
    return "finalize"


async def finalize(state: AnalysisState) -> dict[str, Any]:
    """Drop findings whose spans no longer resolve.

    A finding that cannot quote its source verbatim is a bug, and shipping one
    is worse than shipping nothing. This is the same invariant the CI gate
    enforces, applied at runtime.
    """
    started = time.monotonic()
    sections = state.get("sections") or {}
    findings = state.get("findings", [])

    kept: list[Finding] = []
    rejected: list[str] = []
    for finding in findings:
        problems = finding.verify_spans(sections)
        if problems:
            rejected.append(f"dropped finding {finding.id}: {problems[0]}")
        else:
            kept.append(finding)

    kept.sort(key=lambda f: f.materiality.score, reverse=True)

    return {
        "final_findings": kept,
        "errors": rejected,
        "timings": _timed("finalize", started),
    }
