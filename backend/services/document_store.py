"""MongoDB Atlas Vector Search backed document store.

Embeddings: local fastembed with sentence-transformers/all-MiniLM-L6-v2 (384 dims).
No API calls, no rate limits, no cost. Model (~50MB) downloads once on first use.
"""

import hashlib
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from services.mongo_client import get_db

_EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Lazy-loaded singleton — avoids loading the model on every DocumentStore() construction
_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        print(f"[DocumentStore] Loading embedding model '{_EMBED_MODEL_NAME}' (first run downloads ~50MB)...")
        _embedder = TextEmbedding(model_name=_EMBED_MODEL_NAME)
    return _embedder


class DocumentChunk:
    """A chunk of text retrieved from the document store."""

    def __init__(self, text: str, metadata: Dict[str, Any], score: float = 0.0):
        self.text = text
        self.metadata = metadata
        self.score = score

    def __repr__(self):
        return f"DocumentChunk(ticker={self.metadata.get('ticker')}, section={self.metadata.get('section')}, len={len(self.text)})"


class DocumentStore:
    def __init__(self):
        self._db = get_db()

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """
        Split text into chunks by approximate token count.
        Uses ~4 chars per token estimate.

        Args:
            text: Text to chunk
            chunk_size: Target tokens per chunk
            overlap: Token overlap between chunks

        Returns:
            List of text chunks
        """
        char_size = chunk_size * 4
        char_overlap = overlap * 4

        if len(text) <= char_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + char_size

            # Try to break at a sentence boundary
            if end < len(text):
                # Look for sentence end near the boundary
                for boundary in [". ", ".\n", "\n\n", "\n"]:
                    idx = text.rfind(boundary, start + char_size // 2, end + 200)
                    if idx != -1:
                        end = idx + len(boundary)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - char_overlap

        return chunks

    @staticmethod
    def _make_id(ticker: str, section: str, chunk_idx: int, filing_date: str) -> str:
        """Generate a deterministic ID for a chunk."""
        raw = f"{ticker}_{section}_{filing_date}_{chunk_idx}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _embed(self, text: str) -> List[float]:
        """Embed text locally via fastembed (384 dims, no API calls)."""
        embedder = _get_embedder()
        # fastembed.embed() returns a generator yielding numpy arrays
        vec = next(embedder.embed([text[:4096]]))
        return vec.tolist()

    def add_sec_filing_chunks(
        self,
        ticker: str,
        sections: Dict[str, str],
        filing_date: str,
    ) -> int:
        total_chunks = 0
        docs: List[Dict[str, Any]] = []

        for section_name, text in sections.items():
            if not text:
                continue

            chunks = self._chunk_text(text)
            for i, chunk in enumerate(chunks):
                docs.append({
                    "_id": self._make_id(ticker, section_name, i, filing_date),
                    "text": chunk,
                    "embedding": self._embed(chunk),
                    "collection": "sec_filings",
                    "ticker": ticker.upper(),
                    "section": section_name,
                    "filing_date": filing_date,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                })
                total_chunks += 1

        for doc in docs:
            self._db["document_chunks"].replace_one({"_id": doc["_id"]}, doc, upsert=True)

        return total_chunks

    def query(
        self,
        ticker: str,
        query_text: str,
        n_results: int = 5,
        section_filter: Optional[str] = None,
    ) -> List[DocumentChunk]:
        where_filter: Dict[str, Any] = {"ticker": ticker.upper(), "collection": "sec_filings"}
        if section_filter:
            where_filter["section"] = section_filter

        try:
            query_embedding = self._embed(query_text)
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "embedding",
                        "queryVector": query_embedding,
                        "numCandidates": 100,
                        "limit": n_results,
                        "filter": where_filter,
                    }
                },
                {"$project": {"text": 1, "score": {"$meta": "vectorSearchScore"}, "ticker": 1, "section": 1, "filing_date": 1}},
            ]
            results = list(self._db["document_chunks"].aggregate(pipeline))
        except Exception as e:
            print(f"[DocumentStore] Query error: {e}")
            return []

        return [
            DocumentChunk(
                text=doc.get("text", ""),
                metadata={
                    "ticker": doc.get("ticker", ""),
                    "section": doc.get("section", ""),
                    "filing_date": doc.get("filing_date", ""),
                },
                score=float(doc.get("score", 0.0)),
            )
            for doc in results
        ]

    def add_user_document_chunks(
        self,
        analysis_id: str,
        ticker: str,
        doc_id: str,
        filename: str,
        content: str,
        uploaded_at: Optional[str] = None,
    ) -> int:
        """Chunk and store user-uploaded PDF content."""
        chunks = self._chunk_text(content)
        if not chunks:
            return 0

        timestamp = uploaded_at or datetime.utcnow().isoformat()
        docs: List[Dict[str, Any]] = []

        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{analysis_id}_{filename}_{i}".encode("utf-8")).hexdigest()
            docs.append({
                "_id": chunk_id,
                "text": chunk,
                "embedding": self._embed(chunk),
                "collection": "user_documents",
                "analysisId": analysis_id,
                "docId": doc_id,
                "ticker": ticker.upper(),
                "filename": filename,
                "source_type": "user_pdf",
                "uploaded_at": timestamp,
                "chunk_index": i,
                "total_chunks": len(chunks),
            })

        for doc in docs:
            self._db["document_chunks"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
        return len(docs)

    def query_user_documents(
        self,
        analysis_id: str,
        ticker: str,
        query_text: str,
        n_results: int = 5,
    ) -> List[DocumentChunk]:
        where_filter: Dict[str, Any] = {"analysisId": analysis_id, "ticker": ticker.upper(), "collection": "user_documents"}

        try:
            query_embedding = self._embed(query_text)
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "embedding",
                        "queryVector": query_embedding,
                        "numCandidates": 100,
                        "limit": n_results,
                        "filter": where_filter,
                    }
                },
                {"$project": {"text": 1, "score": {"$meta": "vectorSearchScore"}, "filename": 1, "ticker": 1}},
            ]
            results = list(self._db["document_chunks"].aggregate(pipeline))
        except Exception as e:
            print(f"[DocumentStore] User document query error: {e}")
            return []

        return [DocumentChunk(text=doc.get("text", ""), metadata={"filename": doc.get("filename"), "ticker": doc.get("ticker")}, score=float(doc.get("score", 0.0))) for doc in results]

    def has_recent_filing(self, ticker: str, max_age_days: int = 90) -> bool:
        """
        Check if we already have recent filing data cached.

        Args:
            ticker: Stock ticker
            max_age_days: Maximum age in days

        Returns:
            True if recent data exists
        """
        try:
            doc = self._db["document_chunks"].find_one(
                {"ticker": ticker.upper(), "collection": "sec_filings"},
                sort=[("filing_date", -1)],
            )
            if not doc:
                return False
            filing_date_str = doc.get("filing_date", "")
            if not filing_date_str:
                return False

            try:
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d")
                cutoff = datetime.now() - timedelta(days=max_age_days)
                return filing_date >= cutoff
            except ValueError:
                return False

        except Exception:
            return False

    def count_documents(self, ticker: Optional[str] = None) -> int:
        """Count stored documents, optionally filtered by ticker."""
        query: Dict[str, Any] = {"collection": "sec_filings"}
        if ticker:
            query["ticker"] = ticker.upper()
        return self._db["document_chunks"].count_documents(query)
