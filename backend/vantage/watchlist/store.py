"""Watchlist persistence.

Mongo when it is configured, an in-process dict otherwise, behind one
interface. The fallback keeps the feature usable on a fresh clone with no
Atlas cluster, and says so rather than pretending to persist.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vantage.config import get_settings

log = logging.getLogger(__name__)

MONGO_TIMEOUT_MS = 3000


class WatchedCompany(BaseModel):
    """One ticker a user wants to hear about."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    ticker: str
    cik: str | None = None
    forms: list[str] = Field(default_factory=lambda: ["10-K", "10-Q", "8-K"])
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Newest accession already reported, per form. One cursor across all
    # forms does not work: EDGAR serves a feed per form, so the newest 10-K
    # never appears in the 8-K feed and every 8-K would look new forever.
    last_seen: dict[str, str] = Field(default_factory=dict)
    last_checked_at: datetime | None = None

    @field_validator("ticker")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class WatchlistStore(Protocol):
    async def list(self) -> list[WatchedCompany]: ...
    async def get(self, ticker: str) -> WatchedCompany | None: ...
    async def put(self, entry: WatchedCompany) -> None: ...
    async def remove(self, ticker: str) -> bool: ...


class MemoryWatchlistStore:
    """Non-durable fallback. Logged at startup so it is never a surprise."""

    def __init__(self) -> None:
        self._rows: dict[str, WatchedCompany] = {}

    async def list(self) -> list[WatchedCompany]:
        return sorted(self._rows.values(), key=lambda e: e.ticker)

    async def get(self, ticker: str) -> WatchedCompany | None:
        return self._rows.get(ticker.upper())

    async def put(self, entry: WatchedCompany) -> None:
        self._rows[entry.ticker] = entry

    async def remove(self, ticker: str) -> bool:
        return self._rows.pop(ticker.upper(), None) is not None


class MongoWatchlistStore:
    """Durable store. Ticker is the document id, so put is an upsert."""

    def __init__(self, collection: Any) -> None:
        self._col = collection

    async def list(self) -> list[WatchedCompany]:
        rows = await self._col.find({}).sort("_id", 1).to_list(length=500)
        return [WatchedCompany(**{k: v for k, v in r.items() if k != "_id"}) for r in rows]

    async def get(self, ticker: str) -> WatchedCompany | None:
        row = await self._col.find_one({"_id": ticker.upper()})
        if row is None:
            return None
        return WatchedCompany(**{k: v for k, v in row.items() if k != "_id"})

    async def put(self, entry: WatchedCompany) -> None:
        doc = entry.model_dump(mode="python")
        await self._col.replace_one(
            {"_id": entry.ticker}, {"_id": entry.ticker, **doc}, upsert=True
        )

    async def remove(self, ticker: str) -> bool:
        result = await self._col.delete_one({"_id": ticker.upper()})
        return bool(result.deleted_count)


_store: WatchlistStore | None = None


async def get_store() -> WatchlistStore:
    global _store
    if _store is not None:
        return _store

    uri = get_settings().mongodb_uri.get_secret_value()
    if not uri or "placeholder" in uri:
        log.warning("MONGODB_URI is not set, the watchlist will not survive a restart")
        _store = MemoryWatchlistStore()
        return _store

    try:
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
        _store = MongoWatchlistStore(client[get_settings().mongodb_database]["watchlist"])
    except Exception as exc:
        log.warning("Mongo unavailable (%s), the watchlist will not persist", exc)
        _store = MemoryWatchlistStore()
    return _store


def reset_store() -> None:
    """Drop the cached store. Tests use this for isolation."""
    global _store
    _store = None
