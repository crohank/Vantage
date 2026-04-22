import os
from typing import Optional

from gridfs import GridFSBucket
from pymongo import MongoClient
from pymongo.database import Database

_client: Optional[MongoClient] = None
_db: Optional[Database] = None


def get_db() -> Database:
    global _client, _db
    if _db is not None:
        return _db

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is required")

    _client = MongoClient(uri)
    _db = _client["vantage"]
    return _db


def get_gridfs() -> GridFSBucket:
    return GridFSBucket(get_db(), bucket_name="pdfs")
