"""MongoDB Atlas connection + vector search helpers."""
import os
import time

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

load_dotenv()

_client: MongoClient | None = None


def get_db():
    """Return the project database (MONGODB_URI / MONGODB_DB from .env)."""
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI is not set — copy .env.example to .env and fill it in")
        expected = os.environ.get("ATLAS_SANDBOX_HOST", "").strip().lower()
        # Validate before constructing MongoClient so even a later ping cannot touch the wrong cluster.
        if not expected:
            raise RuntimeError("ATLAS_SANDBOX_HOST is required; set the exact hackathon Atlas host in .env")
        actual = uri.split("://", 1)[-1].rsplit("@", 1)[-1].split("/", 1)[0].split("?", 1)[0].split(":", 1)[0].lower()
        if actual != expected:
            raise RuntimeError(f"MONGODB_URI host {actual!r} does not match ATLAS_SANDBOX_HOST {expected!r}")
        _client = MongoClient(uri, appname="agent-memory-hackathon")
    return _client[os.environ.get("MONGODB_DB", "rekurse")]


def ensure_vector_index(coll, dims: int, path: str = "embedding",
                        name: str = "vector_index", filters: list[str] | None = None,
                        timeout_s: int = 120):
    """Create an Atlas Vector Search index if missing and wait until it's queryable."""
    if not any(ix["name"] == name for ix in coll.list_search_indexes()):
        fields = [{"type": "vector", "path": path, "numDimensions": dims, "similarity": "cosine"}]
        fields += [{"type": "filter", "path": f} for f in (filters or [])]
        coll.create_search_index(SearchIndexModel(
            definition={"fields": fields}, name=name, type="vectorSearch"))
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        ix = next(iter(coll.list_search_indexes(name)), None)
        if ix and ix.get("queryable"):
            return
        time.sleep(3)
    raise TimeoutError(f"Vector index {name!r} not queryable after {timeout_s}s")


def vector_search(coll, query_vector: list[float], k: int = 5,
                  path: str = "embedding", index: str = "vector_index", filter: dict | None = None):
    """Return the top-k most similar documents, each with a `score`."""
    stage = {"index": index, "path": path, "queryVector": query_vector,
             "numCandidates": max(k * 20, 100), "limit": k}
    if filter:
        stage["filter"] = filter
    return list(coll.aggregate([
        {"$vectorSearch": stage},
        {"$project": {"embedding": 0, "score": {"$meta": "vectorSearchScore"}}},
    ]))
