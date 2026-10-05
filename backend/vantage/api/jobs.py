"""In-process job runner.

Analysis is filing-triggered rather than user-triggered, so a request starts
work and returns an id instead of holding a connection open for the duration.
The previous design spawned a Python process per request and kept an HTTP
connection alive for up to sixty minutes, with no concurrency limit and no way
to kill the child when the client went away.

Jobs live in memory. That is deliberate at this scale: the graph checkpointer
already persists the work itself, so a restart loses the job index rather than
the analysis, and a resumed thread_id picks up where it stopped. Durable job
rows would duplicate state the checkpointer already owns.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from vantage.config import get_settings
from vantage.graph.build import RECURSION_LIMIT, get_graph
from vantage.graph.state import RequestKind, initial_state

log = logging.getLogger(__name__)

# Completed jobs are kept so a client that reconnects after the stream closed
# can still collect its result. Oldest terminal job is evicted first.
MAX_RETAINED_JOBS = 200

# How long a stream consumer waits for the next event before emitting a
# keep-alive. Proxies commonly idle out an SSE connection at 60s.
HEARTBEAT_SECONDS = 15.0

NODE_NAMES = frozenset(
    {
        "resolve_company",
        "ingest_filings",
        "run_diff",
        "run_novelty",
        "run_peer",
        "measure_attention",
        "finalize",
    }
)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job:
    """One analysis run, and the event stream it produces."""

    def __init__(self, ticker: str, kind: RequestKind, max_sections: int) -> None:
        self.id = str(uuid.uuid4())
        self.ticker = ticker.upper()
        self.kind = kind
        self.max_sections = max_sections
        self.status = JobStatus.QUEUED
        self.created_at = datetime.now(UTC)
        self.finished_at: datetime | None = None
        self.error: str | None = None
        self.result: dict[str, Any] | None = None

        # Unbounded because a dropped consumer must not stall the producer.
        # Events are small and a run emits tens, not thousands.
        self.events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.task: asyncio.Task[None] | None = None
        # Replayed to a consumer that attaches late, so a client which starts
        # streaming after the run began does not miss the early nodes.
        self.history: list[dict[str, Any]] = []

    @property
    def thread_id(self) -> str:
        return f"job-{self.id}"

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)

    def emit(self, event: dict[str, Any]) -> None:
        self.history.append(event)
        self.events.put_nowait(event)

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        """Replay what has happened, then follow.

        Always ends after a terminal event. The previous SSE implementation
        could end without one, leaving the UI spinning with no error shown.
        """
        for event in list(self.history):
            yield event
        if self.is_terminal:
            return

        while True:
            try:
                # asyncio.timeout rather than wait_for: wait_for's overloads
                # drop the None from the queue's item type, after which mypy
                # calls the sentinel branch unreachable.
                async with asyncio.timeout(HEARTBEAT_SECONDS):
                    item = await self.events.get()
            except TimeoutError:
                yield {"type": "heartbeat", "at": datetime.now(UTC).isoformat()}
                continue
            if item is None:
                return
            yield item

    def cancel(self) -> bool:
        if self.task is None or self.task.done():
            return False
        self.task.cancel()
        return True


class JobRunner:
    """Owns running jobs and bounds how many execute at once."""

    def __init__(self) -> None:
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._semaphore = asyncio.Semaphore(get_settings().max_concurrent_jobs)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self, limit: int = 50) -> list[Job]:
        return list(reversed(self._jobs.values()))[:limit]

    def submit(self, ticker: str, kind: RequestKind, max_sections: int) -> Job:
        job = Job(ticker, kind, max_sections)
        self._jobs[job.id] = job
        self._evict()
        job.task = asyncio.create_task(self._run(job))
        return job

    def _evict(self) -> None:
        """Drop the oldest finished job. Running jobs are never evicted."""
        while len(self._jobs) > MAX_RETAINED_JOBS:
            for job_id, job in self._jobs.items():
                if job.is_terminal:
                    del self._jobs[job_id]
                    break
            else:
                return

    async def _run(self, job: Job) -> None:
        try:
            async with self._semaphore:
                job.status = JobStatus.RUNNING
                job.emit({"type": "status", "status": job.status.value, "ticker": job.ticker})
                await self._execute(job)
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
            job.emit({"type": "status", "status": job.status.value})
            raise
        except Exception as exc:
            log.exception("job %s failed", job.id)
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.emit({"type": "error", "message": str(exc)})
        finally:
            job.finished_at = datetime.now(UTC)
            # Unblock every consumer, including on the cancellation path.
            job.events.put_nowait(None)

    async def _execute(self, job: Job) -> None:
        graph = await get_graph()
        config: dict[str, Any] = {
            "configurable": {"thread_id": job.thread_id},
            "recursion_limit": RECURSION_LIMIT,
        }
        state = initial_state(job.ticker, job.kind, max_sections=job.max_sections)

        # Progress comes from the graph's own event stream, so node names are
        # real. The previous implementation regex-scraped bracketed prefixes
        # out of a subprocess's print statements.
        async for event in graph.astream_events(state, config, version="v2"):
            name = event.get("name", "")
            if name not in NODE_NAMES:
                continue
            if event.get("event") == "on_chain_start":
                job.emit({"type": "node_start", "node": name})
            elif event.get("event") == "on_chain_end":
                job.emit({"type": "node_end", "node": name})

        snapshot = await graph.aget_state(config)
        job.result = dict(snapshot.values)
        job.status = JobStatus.SUCCEEDED
        job.emit(
            {
                "type": "complete",
                "findings": len(job.result.get("final_findings", [])),
                "errors": job.result.get("errors", []),
            }
        )


_runner: JobRunner | None = None


def get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner()
    return _runner


def reset_runner() -> None:
    """Drop the runner. Tests use this for isolation."""
    global _runner
    _runner = None
