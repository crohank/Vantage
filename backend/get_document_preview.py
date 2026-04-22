"""Return preview text for a Mongo document entry by ID."""

import json
import sys
from typing import Any, Dict, List

from services.document_store import DocumentStore
from services.document_registry import get_document


def build_preview(document: Dict[str, Any]) -> Dict[str, Any]:
    store = DocumentStore()
    ticker = str(document.get("ticker", "")).upper()
    analysis_id = str(document.get("analysis_id", ""))
    source_type = document.get("source_type", "")
    filename = document.get("filename", "")

    chunks: List[str] = []
    if source_type == "user_pdf" and analysis_id and ticker:
        for chunk in store.query_user_documents(
            analysis_id=analysis_id,
            ticker=ticker,
            query_text=f"Summarize key financial and risk insights for {ticker}",
            n_results=8,
        ):
            chunk_text = (chunk.text or "").strip()
            if chunk_text:
                chunks.append(chunk_text)
    elif source_type == "sec_filing" and ticker:
        combined = []
        combined.extend(store.query(ticker, f"Key risk factors for {ticker}", n_results=4, section_filter="risk_factors"))
        combined.extend(store.query(ticker, f"Management outlook for {ticker}", n_results=4, section_filter="mda"))
        for chunk in combined:
            chunk_text = (chunk.text or "").strip()
            if chunk_text:
                chunks.append(chunk_text)

    # De-duplicate while preserving order.
    deduped: List[str] = []
    seen = set()
    for chunk in chunks:
        if chunk in seen:
            continue
        seen.add(chunk)
        deduped.append(chunk)

    preview_chunks = deduped[:6]
    preview_text = "\n\n---\n\n".join(preview_chunks)

    return {
        "document_id": document.get("id"),
        "filename": filename,
        "preview_chunks": preview_chunks,
        "preview_text": preview_text,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing document_id"}))
        return 1

    document_id = sys.argv[1]
    document = get_document(document_id)
    if not document:
        print(json.dumps({"error": "Document not found"}))
        return 1

    result = build_preview(document)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
