"""FastAPI application.

One service. The previous architecture was an Express server that spawned
`python main.py` per request and parsed its stdout between sentinel markers,
with a greedy brace-match and a regex scraper of human-readable CLI prose as
fallbacks. Changing a print statement changed the API contract.

Auth, a rate limit, and a concurrency cap are present from the start. The
previous server had none of the three on any route, including an
unauthenticated upload that spawned a process and an unauthenticated delete.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from vantage.api.jobs import Job, JobStatus, get_runner
from vantage.api.schemas import (
    AnalysisResult,
    AnalyzeRequest,
    FindingOut,
    HealthOut,
    JobRef,
    JobSummary,
    NewFilingOut,
    NodeTimingOut,
    PollerStatusOut,
    SectionOut,
    SpanOut,
    WatchedOut,
    WatchRequest,
)
from vantage.config import get_settings
from vantage.domain.finding import Finding
from vantage.graph.build import get_graph
from vantage.watchlist.poller import NewFiling, get_poller
from vantage.watchlist.store import WatchedCompany, get_store

log = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Compile the graph at startup rather than per request, and surface a
    # misconfigured checkpointer in the logs before the first caller arrives.
    await get_graph()
    yield


app = FastAPI(
    title="Vantage",
    version="0.2.0",
    summary="Finds what changed in SEC filings, and whether anyone noticed.",
    lifespan=lifespan,
)
app.state.limiter = limiter

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    # An explicit list, never "*". The previous server set the allowlist
    # correctly and then overrode it with a hand-written wildcard header on
    # the streaming routes, which is invalid alongside credentials anyway.
    allow_origins=[o.strip() for o in _settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def _rate_limited(request: Request, exc: RateLimitExceeded) -> Any:
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": f"rate limit exceeded: {exc.detail}"},
    )


async def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Shared-secret auth.

    When no key is configured the API is open, which is correct for local
    development and is logged as a warning at startup by config. In a
    deployment VANTAGE_API_KEY is set and every route requires it.
    """
    configured = get_settings().api_key
    if configured is None:
        return
    if x_api_key != configured.get_secret_value():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing X-API-Key")


Authed = Depends(require_api_key)


def _finding_out(finding: Finding) -> FindingOut:
    return FindingOut(
        id=finding.id,
        kind=finding.kind,
        ticker=finding.ticker,
        cik=finding.cik,
        section_id=finding.section_id,
        change_type=finding.change_type,
        current_span=SpanOut.of(finding.current_span) if finding.current_span else None,
        prior_span=SpanOut.of(finding.prior_span) if finding.prior_span else None,
        current_accession=finding.current_accession,
        prior_accession=finding.prior_accession,
        summary=finding.summary,
        rationale=finding.rationale,
        materiality=finding.materiality,
        novelty_phrase=finding.novelty_phrase,
        novelty_first_seen=finding.novelty_first_seen,
        peer_ciks=finding.peer_ciks,
        peer_total=finding.peer_total,
    )


def _result(job: Job) -> AnalysisResult:
    values = job.result or {}
    company = values.get("company")
    return AnalysisResult(
        job_id=job.id,
        ticker=job.ticker,
        status=job.status.value,
        company_name=company.name if company else None,
        cik=company.cik if company else None,
        sic=company.sic if company else None,
        current_filing=values.get("current_filing"),
        prior_filing=values.get("prior_filing"),
        findings=[_finding_out(f) for f in values.get("final_findings", [])],
        attention=values.get("attention"),
        errors=values.get("errors", []),
        timings=[NodeTimingOut(**t) for t in values.get("timings", [])],
    )


def _summary(job: Job) -> JobSummary:
    return JobSummary(
        job_id=job.id,
        ticker=job.ticker,
        kind=job.kind,
        status=job.status.value,
        created_at=job.created_at,
        finished_at=job.finished_at,
        error=job.error,
        finding_count=len((job.result or {}).get("final_findings", [])),
    )


def _require_job(job_id: str) -> Job:
    job = get_runner().get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no job {job_id}")
    return job


@app.get("/health", response_model=HealthOut, tags=["meta"])
async def health() -> HealthOut:
    from vantage.attention.score import default_sources

    graph = await get_graph()
    checkpointer = type(graph.checkpointer).__name__ if graph.checkpointer else "none"
    return HealthOut(
        status="ok",
        git_sha=get_settings().git_sha,
        checkpointer=checkpointer,
        attention_sources=[s.name.value for s in default_sources() if s.is_configured()],
    )


@app.post("/analyses", response_model=JobRef, status_code=202, tags=["analyses"])
@limiter.limit(_settings.rate_limit)
async def submit_analysis(request: Request, body: AnalyzeRequest, _: None = Authed) -> JobRef:
    """Start a run and return immediately.

    202 rather than 200: the work is accepted, not finished. Progress is on
    the stream endpoint and the result on the job endpoint.
    """
    job = get_runner().submit(body.ticker, body.kind, body.max_sections)
    return JobRef(
        job_id=job.id,
        ticker=job.ticker,
        kind=job.kind,
        status=job.status.value,
        created_at=job.created_at,
        stream_url=f"/analyses/{job.id}/stream",
    )


@app.get("/analyses", response_model=list[JobSummary], tags=["analyses"])
async def list_analyses(
    limit: Annotated[int, Query(ge=1, le=200)] = 50, _: None = Authed
) -> list[JobSummary]:
    return [_summary(j) for j in get_runner().list(limit)]


@app.get("/analyses/{job_id}", response_model=AnalysisResult, tags=["analyses"])
async def get_analysis(job_id: str, _: None = Authed) -> AnalysisResult:
    return _result(_require_job(job_id))


@app.delete("/analyses/{job_id}", status_code=204, tags=["analyses"])
async def cancel_analysis(job_id: str, _: None = Authed) -> None:
    job = _require_job(job_id)
    if not job.cancel():
        raise HTTPException(status.HTTP_409_CONFLICT, f"job {job_id} is already {job.status}")


@app.get("/analyses/{job_id}/stream", tags=["analyses"])
async def stream_analysis(job_id: str, _: None = Authed) -> StreamingResponse:
    """Server-sent events for one run.

    The stream always terminates with a `complete` or `error` event, so a
    client never has to guess whether a silent connection means work in
    progress or a dead backend.
    """
    job = _require_job(job_id)

    async def events() -> AsyncIterator[str]:
        async for event in job.stream():
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        if job.status is JobStatus.SUCCEEDED:
            payload = _result(job).model_dump(mode="json")
            yield f"event: result\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # nginx buffers SSE into uselessness without this.
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/analyses/{job_id}/sections/{accession}/{section_id}", tags=["filings"])
async def get_section(job_id: str, accession: str, section_id: str, _: None = Authed) -> SectionOut:
    """The stored text a finding's span points into.

    This is what makes a citation checkable in the UI: the client resolves
    start and end against exactly the text the engine diffed.
    """
    job = _require_job(job_id)
    sections = (job.result or {}).get("sections", {})
    section = sections.get(f"{accession}:{section_id}")
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no section {accession}:{section_id}")
    return SectionOut(
        accession=section.accession,
        section_id=section.section_id,
        heading=section.heading,
        text=section.text,
        char_length=len(section.text),
    )


def _watched_out(entry: WatchedCompany) -> WatchedOut:
    return WatchedOut(
        ticker=entry.ticker,
        cik=entry.cik,
        forms=entry.forms,
        added_at=entry.added_at,
        last_seen=entry.last_seen,
        last_checked_at=entry.last_checked_at,
    )


def _new_filing_out(item: NewFiling) -> NewFilingOut:
    return NewFilingOut(
        ticker=item.ticker,
        cik=item.cik,
        accession=item.entry.accession,
        form=item.entry.form,
        filed=item.entry.filed,
        title=item.entry.title,
        link=item.entry.link,
    )


@app.get("/watchlist", response_model=list[WatchedOut], tags=["watchlist"])
async def list_watchlist(_: None = Authed) -> list[WatchedOut]:
    store = await get_store()
    return [_watched_out(e) for e in await store.list()]


@app.post("/watchlist", response_model=WatchedOut, status_code=201, tags=["watchlist"])
async def add_to_watchlist(body: WatchRequest, _: None = Authed) -> WatchedOut:
    """Watch a ticker.

    The first sweep records the newest filing as a baseline without alerting,
    so adding a ticker does not immediately report its whole history.
    """
    store = await get_store()
    existing = await store.get(body.ticker)
    entry = existing or WatchedCompany(ticker=body.ticker, forms=body.forms)
    if existing:
        entry = entry.model_copy(update={"forms": body.forms})
    await store.put(entry)
    return _watched_out(entry)


@app.delete("/watchlist/{ticker}", status_code=204, tags=["watchlist"])
async def remove_from_watchlist(ticker: str, _: None = Authed) -> None:
    store = await get_store()
    if not await store.remove(ticker):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{ticker.upper()} is not watched")


@app.get("/watchlist/poller", response_model=PollerStatusOut, tags=["watchlist"])
async def poller_status(_: None = Authed) -> PollerStatusOut:
    poller = get_poller()
    return PollerStatusOut(
        running=poller.running,
        interval_seconds=poller.interval,
        last_sweep_at=poller.last_sweep_at,
        last_error=poller.last_error,
        pending=[_new_filing_out(f) for f in poller.pending],
    )


@app.post("/watchlist/poller/sweep", response_model=list[NewFilingOut], tags=["watchlist"])
@limiter.limit("6/minute")
async def sweep_now(request: Request, _: None = Authed) -> list[NewFilingOut]:
    """Run one sweep immediately, rather than waiting for the interval."""
    found = await get_poller().run_once()
    return [_new_filing_out(f) for f in found]
