"""Graph assembly.

Topology, in contrast to the six-node straight line this replaces:

    resolve_company
        |
    ingest_filings
        |
        +--> run_diff ---> [novelty?] --> run_novelty --> [peer?] --> run_peer
        |                                                                 |
        +--> measure_attention -------------------------------------------+
                                                                          |
                                                                      finalize

run_diff and measure_attention genuinely run concurrently, merged through the
state reducers, rather than by a ThreadPoolExecutor inside one node copying
the state and throwing most of the result away.

The graph is compiled once at import and reused. The old code rebuilt it on
every request.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from vantage.config import get_settings
from vantage.graph.nodes import (
    finalize,
    ingest_filings,
    measure_attention,
    needs_novelty,
    needs_peer,
    resolve_company,
    route_after_ingest,
    run_diff,
    run_novelty,
    run_peer,
)
from vantage.graph.state import AnalysisState

log = logging.getLogger(__name__)

MONGO_TIMEOUT_MS = 3000

# EDGAR is rate limited and occasionally answers 503. The client already
# retries individual requests; this covers a node failing as a whole.
_NETWORK_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0)

# Every path through the graph is finite, so a high limit only ever catches a
# genuine bug rather than shaping normal behaviour.
RECURSION_LIMIT = 40


def build_graph() -> StateGraph[AnalysisState, None, AnalysisState, AnalysisState]:
    workflow = StateGraph(AnalysisState)

    workflow.add_node("resolve_company", resolve_company, retry_policy=_NETWORK_RETRY)
    workflow.add_node("ingest_filings", ingest_filings, retry_policy=_NETWORK_RETRY)
    workflow.add_node("run_diff", run_diff)
    workflow.add_node("run_novelty", run_novelty, retry_policy=_NETWORK_RETRY)
    workflow.add_node("run_peer", run_peer, retry_policy=_NETWORK_RETRY)
    workflow.add_node("measure_attention", measure_attention)
    workflow.add_node("finalize", finalize)

    workflow.add_edge(START, "resolve_company")
    workflow.add_edge("resolve_company", "ingest_filings")

    # Fan out. The list return spawns one branch per name, which is how
    # LangGraph expresses genuine parallelism.
    workflow.add_conditional_edges(
        "ingest_filings",
        route_after_ingest,
        ["run_diff", "measure_attention", "finalize"],
    )

    workflow.add_conditional_edges("run_diff", needs_novelty, ["run_novelty", "finalize"])
    workflow.add_conditional_edges("run_novelty", needs_peer, ["run_peer", "finalize"])
    workflow.add_edge("run_peer", "finalize")
    workflow.add_edge("measure_attention", "finalize")
    workflow.add_edge("finalize", END)

    return workflow


async def make_checkpointer() -> Any:
    """Mongo when it is reachable, in-memory otherwise.

    A 10-K ingest plus diff is a long job over rate-limited external APIs, so
    resuming from the last completed node rather than restarting is a real
    requirement. InMemorySaver is a development convenience and loses
    everything on restart, so falling back to it is logged loudly.
    """
    settings = get_settings()
    uri = settings.mongodb_uri.get_secret_value()
    if not uri or "placeholder" in uri:
        log.warning(
            "MONGODB_URI is not configured, using an in-memory checkpointer. "
            "Runs will not survive a restart."
        )
        return InMemorySaver()

    try:
        from langgraph.checkpoint.mongodb import MongoDBSaver
        from pymongo import AsyncMongoClient

        # Fail fast. The default server selection timeout is 30s, and
        # both callers fall back cleanly, so a slow answer here just
        # stalls startup or the first request for no benefit.
        client: Any = AsyncMongoClient(
            uri,
            serverSelectionTimeoutMS=MONGO_TIMEOUT_MS,
            connectTimeoutMS=MONGO_TIMEOUT_MS,
        )
        await client.admin.command("ping")
        return MongoDBSaver(client, db_name=settings.mongodb_database)
    except Exception as exc:
        log.warning("Mongo checkpointer unavailable (%s), falling back to in-memory", exc)
        return InMemorySaver()


_compiled: Any | None = None


async def get_graph() -> Any:
    """The compiled graph, built once per process."""
    global _compiled
    if _compiled is None:
        _compiled = build_graph().compile(checkpointer=await make_checkpointer())
    return _compiled


def reset_graph() -> None:
    """Drop the cached graph. Tests use this to swap the checkpointer."""
    global _compiled
    _compiled = None
