"""
Smoke test — verifies MongoDB Atlas connectivity, Vector Search index, and Google embeddings.

Run from the backend/ directory:
    python -m scripts.smoke_test

Requirements in .env:
    MONGODB_URI=mongodb+srv://...
    GEMINI_API_KEY=AIza...
"""

import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Allow running from backend/ or backend/scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
# .env lives at project root (analyst/), three levels up from backend/scripts/smoke_test.py
_project_root = Path(__file__).parent.parent.parent
load_dotenv(_project_root / ".env")


def check_env() -> bool:
    if not os.getenv("MONGODB_URI"):
        print("[FAIL] Missing env var: MONGODB_URI")
        print("       Add it to analyst/.env and retry.")
        return False
    print("[OK]   MONGODB_URI found in environment")
    return True


def check_mongo_connection() -> bool:
    try:
        from services.mongo_client import get_db
        db = get_db()
        db.command("ping")
        print("[OK]   MongoDB Atlas connection successful")
        return True
    except Exception as e:
        print(f"[FAIL] MongoDB connection failed: {e}")
        print("       Check MONGODB_URI and that 0.0.0.0/0 is in Atlas Network Access.")
        return False


def check_local_embedding() -> list | None:
    """Returns a 384-dim embedding via local fastembed (no API, no internet on warm runs)."""
    try:
        from fastembed import TextEmbedding
    except ImportError:
        print("[FAIL] fastembed not installed. Run: pip install fastembed")
        return None
    try:
        print("       (first run downloads ~50MB — may take 30s)")
        model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        vec = next(model.embed(["The quick brown fox"])).tolist()
        assert len(vec) == 384, f"Expected 384 dims, got {len(vec)}"
        print(f"[OK]   Local fastembed returned {len(vec)}-dim vector")
        return vec
    except Exception as e:
        print(f"[FAIL] fastembed failed: {e}")
        return None


def check_vector_search(embedding: list) -> bool:
    """Inserts a real embedding and runs $vectorSearch to verify the index exists."""
    from services.mongo_client import get_db
    db = get_db()
    analysis_id = f"smoke-{uuid.uuid4()}"
    chunk_id = f"smoke-chunk-{uuid.uuid4()}"

    try:
        # Insert
        db["analyses"].insert_one({
            "_id": analysis_id,
            "ticker": "SMOKE",
            "horizon": "short",
            "riskProfile": "moderate",
            "recommendation": "Hold",
            "confidenceScore": 0.5,
            "scenarios": {},
            "memoMarkdown": "smoke test — safe to delete",
            "createdAt": datetime.now(timezone.utc),
        })
        db["document_chunks"].insert_one({
            "_id": chunk_id,
            "collection": "user_documents",
            "analysisId": analysis_id,
            "ticker": "SMOKE",
            "text": "smoke test chunk",
            "embedding": embedding,
        })

        # Confirm the doc is actually in the collection (separate from being in the vector index)
        stored = db["document_chunks"].find_one({"_id": chunk_id})
        if not stored:
            print("[FAIL] Chunk was not persisted to MongoDB — unexpected.")
            return False
        print(f"       Chunk persisted to MongoDB. Waiting for Atlas Vector Search to index it...")

        # Poll $vectorSearch — Atlas indexes new docs asynchronously (can take 10-60s on M0)
        pipeline = [{
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": embedding,
                "numCandidates": 10,
                "limit": 1,
                "filter": {"analysisId": analysis_id},
            }
        }]

        max_wait = 90  # seconds
        interval = 3
        waited = 0
        while waited < max_wait:
            results = list(db["document_chunks"].aggregate(pipeline))
            if results:
                print(f"[OK]   Atlas Vector Search index 'vector_index' is working (indexed in ~{waited}s)")
                return True
            print(f"       ...still waiting ({waited}s elapsed)")
            time.sleep(interval)
            waited += interval

        print(f"[FAIL] Vector search returned no results after {max_wait}s.")
        print("       Possible causes:")
        print("       - Index numDimensions mismatch (should be 384, not 768)")
        print("       - Index field name mismatch (should be 'embedding')")
        print("       - Index not on 'document_chunks' collection")
        print("       Check Atlas → Search & Vector Search → vector_index → JSON config")
        return False

    except Exception as e:
        err = str(e)
        if "index not found" in err.lower() or "IndexNotFound" in err:
            print("[FAIL] Vector Search index 'vector_index' does not exist yet.")
            print("       Create it in Atlas UI → Search & Vector Search → Create Search Index")
            print("       Use Atlas Vector Search (not regular Search), numDimensions: 768")
        else:
            print(f"[FAIL] Vector search error: {e}")
        return False
    finally:
        # Always clean up test docs
        db["document_chunks"].delete_one({"_id": chunk_id})
        db["analyses"].delete_one({"_id": analysis_id})


def main() -> int:
    print("\n=== Vantage MongoDB + Embeddings Smoke Test ===\n")

    if not check_env():
        return 1

    if not check_mongo_connection():
        return 1

    embedding = check_local_embedding()
    if embedding is None:
        return 1

    if not check_vector_search(embedding):
        return 1

    print("\n✓ All checks passed — MongoDB and embeddings are ready!\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
