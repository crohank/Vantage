"""Mongo-backed document registry."""

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from services.mongo_client import get_db


def _document_id(source_type: str, ticker: str, source_ref: str) -> str:
    raw = f"{source_type}:{ticker.upper()}:{source_ref}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def register_document(entry: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    source_type = entry.get("source_type", "unknown")
    ticker = str(entry.get("ticker", "")).upper()
    source_ref = entry.get("source_url") or entry.get("filename") or entry.get("title") or "unknown"
    document_id = entry.get("id") or _document_id(source_type, ticker, source_ref)
    normalized = {
        "_id": document_id,
        "id": document_id,
        "source_type": source_type,
        "ticker": ticker,
        "analysis_id": entry.get("analysis_id", ""),
        "title": entry.get("title", ""),
        "source_url": entry.get("source_url", ""),
        "filename": entry.get("filename", ""),
        "gridfs_file_id": entry.get("gridfs_file_id", ""),
        "file_path": entry.get("file_path", ""),
        "filing_date": entry.get("filing_date", ""),
        "chunks": int(entry.get("chunks", 0)),
        "status": entry.get("status", "ready"),
        "created_at": entry.get("created_at", now),
        "updated_at": now,
    }

    get_db()["documents"].update_one({"_id": document_id}, {"$set": normalized}, upsert=True)
    return normalized


def list_documents(
    ticker: Optional[str] = None,
    source_type: Optional[str] = None,
    analysis_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {}
    if ticker:
        query["ticker"] = ticker.upper()
    if source_type:
        query["source_type"] = source_type
    if analysis_id:
        query["analysis_id"] = analysis_id
    cursor = get_db()["documents"].find(query).sort("updated_at", -1).limit(max(1, limit))
    docs: List[Dict[str, Any]] = []
    for doc in cursor:
        doc["id"] = doc.get("_id")
        docs.append(doc)
    return docs


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    query: Dict[str, Any] = {"_id": doc_id}
    if ObjectId.is_valid(doc_id):
        query = {"$or": [{"_id": doc_id}, {"_id": ObjectId(doc_id)}]}
    doc = get_db()["documents"].find_one(query)
    if not doc:
        return None
    doc["id"] = str(doc.get("_id"))
    return doc
