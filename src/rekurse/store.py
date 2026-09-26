"""MemoryStore (offline tests) and MongoStore (Atlas). Same method names, duck-typed."""
from __future__ import annotations

import math
from collections import defaultdict

from .models import MONGODB_DB


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


class MemoryStore:
    kind = "memory"

    def __init__(self):
        self.c: dict[str, dict[str, dict]] = defaultdict(dict)

    def _put(self, coll, doc):
        self.c[coll][doc["_id"]] = dict(doc)

    # sessions / checkpoints
    def save_session(self, doc): self._put("sessions", doc)
    def get_session(self, sid): return self.c["sessions"].get(sid)
    def save_checkpoints(self, docs):
        for d in docs: self._put("checkpoints", d)
    def get_checkpoints(self, sid):
        return sorted((d for d in self.c["checkpoints"].values() if d["session_id"] == sid), key=lambda d: d["k"])

    # runs
    def save_run(self, doc): self._put("runs", doc)
    def get_run(self, run_id): return self.c["runs"].get(run_id)
    def runs(self, run_group, purpose=None):
        return [d for d in self.c["runs"].values()
                if d["run_group"] == run_group and (purpose is None or d["purpose"] == purpose)]

    # lessons
    def save_lesson(self, doc): self._put("lessons", doc)
    def update_lesson(self, lid, fields): self.c["lessons"][lid].update(fields)
    def get_lesson(self, lid): return self.c["lessons"].get(lid)
    def lessons(self, run_group=None):
        return [d for d in self.c["lessons"].values() if run_group is None or d["run_group"] == run_group]
    def similar_lessons(self, embedding, k=3):
        scored = [(cosine(embedding, d["embedding"]), d) for d in self.c["lessons"].values() if d.get("embedding")]
        scored.sort(key=lambda t: -t[0])
        return [dict(d, score=s) for s, d in scored[:k]]

    # reports
    def save_report(self, doc): self._put("reports", doc)
    def get_report(self, run_group):
        return next((d for d in self.c["reports"].values() if d["run_group"] == run_group), None)
    def latest_report(self):
        docs = list(self.c["reports"].values())
        return max(docs, key=lambda d: d.get("created_at", ""), default=None)


class MongoStore:
    kind = "mongo"

    def __init__(self, db=None):
        from .db import get_db
        import os
        os.environ.setdefault("MONGODB_DB", MONGODB_DB)
        self.db = db or get_db()
        self.db["runs"].create_index([("run_group", 1), ("purpose", 1), ("checkpoint_k", 1)])
        self.db["checkpoints"].create_index([("session_id", 1), ("k", 1)])

    def ensure_indexes(self, dims: int):
        from .db import ensure_vector_index
        coll = self.db["lessons"]
        if "lessons" not in self.db.list_collection_names():
            self.db.create_collection("lessons")   # search indexes need an existing collection
        for ix in coll.list_search_indexes():
            if ix["name"] != "vector_index":
                continue
            fields = (ix.get("latestDefinition") or ix.get("definition") or {}).get("fields", [])
            have = next((f.get("numDimensions") for f in fields if f.get("type") == "vector"), None)
            if have != dims:   # embedding provider changed: rebuild the index and drop incompatible vectors
                coll.drop_search_index("vector_index")
                coll.delete_many({"$expr": {"$ne": [{"$size": {"$ifNull": ["$embedding", []]}}, dims]}})
                import time
                while any(i["name"] == "vector_index" for i in coll.list_search_indexes()):
                    time.sleep(2)
        ensure_vector_index(coll, dims, filters=["run_group"])

    def get_run(self, run_id): return self.db["runs"].find_one({"_id": run_id})

    def _up(self, coll, doc):
        self.db[coll].replace_one({"_id": doc["_id"]}, doc, upsert=True)

    def save_session(self, doc): self._up("sessions", doc)
    def get_session(self, sid): return self.db["sessions"].find_one({"_id": sid})
    def save_checkpoints(self, docs):
        for d in docs: self._up("checkpoints", d)
    def get_checkpoints(self, sid):
        return list(self.db["checkpoints"].find({"session_id": sid}).sort("k", 1))

    def save_run(self, doc): self._up("runs", doc)
    def runs(self, run_group, purpose=None):
        q = {"run_group": run_group}
        if purpose: q["purpose"] = purpose
        return list(self.db["runs"].find(q))

    def save_lesson(self, doc): self._up("lessons", doc)
    def update_lesson(self, lid, fields): self.db["lessons"].update_one({"_id": lid}, {"$set": fields})
    def get_lesson(self, lid): return self.db["lessons"].find_one({"_id": lid})
    def lessons(self, run_group=None):
        return list(self.db["lessons"].find({"run_group": run_group} if run_group else {}))
    def similar_lessons(self, embedding, k=3):
        from .db import vector_search
        return vector_search(self.db["lessons"], embedding, k=k)

    def save_report(self, doc): self._up("reports", doc)
    def get_report(self, run_group): return self.db["reports"].find_one({"run_group": run_group})
    def latest_report(self): return self.db["reports"].find_one(sort=[("created_at", -1)])
