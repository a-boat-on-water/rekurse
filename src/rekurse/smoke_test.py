"""End-to-end check: Atlas connection, embeddings, vector index, vector search, LLM.

Run:  uv run smoke-test
"""
import os
import sys
import uuid


def step(msg):
    print(f"\n==> {msg}", flush=True)


def run() -> None:
    from .db import ensure_vector_index, get_db, vector_search
    from .embeddings import dims, embed, provider

    step("Connecting to MongoDB Atlas")
    db = get_db()
    db.client.admin.command("ping")
    from .store import _uri_host
    host = _uri_host(os.environ.get("MONGODB_URI", ""))
    expected = os.environ.get("ATLAS_SANDBOX_HOST", "")
    print(f"  ok — database '{db.name}' on host {host}")
    if host != expected.lower():
        raise RuntimeError(f"connected to {host}, but ATLAS_SANDBOX_HOST is {expected} (must use the hackathon sandbox)")

    step(f"Embedding with {provider()} ({dims()} dims)")
    coll = db[f"smoke_{provider()}"]
    notes = [
        "The user prefers concise answers with code examples.",
        "Deploys happen on Fridays after the test suite passes.",
        "The staging database was migrated to Atlas last week.",
    ]
    run_id = uuid.uuid4().hex[:8]
    vecs = embed(notes)
    coll.insert_many([{"text": t, "embedding": v, "run": run_id} for t, v in zip(notes, vecs)])
    print(f"  inserted {len(notes)} memories")

    step("Ensuring vector search index (first run can take ~1 min)")
    ensure_vector_index(coll, dims(), filters=["run"])
    print("  index queryable")

    step("Vector search: 'how does the user like responses?'")
    q = embed(["how does the user like responses?"], input_type="query")[0]
    hits = vector_search(coll, q, k=2, filter={"run": run_id})
    for h in hits:
        print(f"  {h['score']:.3f}  {h['text']}")
    coll.delete_many({"run": run_id})

    if os.environ.get("ANTHROPIC_API_KEY"):
        step("LLM call (Anthropic)")
        import anthropic
        msg = anthropic.Anthropic().messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
            max_tokens=60,
            messages=[{"role": "user", "content": f"Memory: {hits[0]['text']}\nReply in one short sentence: how should you answer this user?"}],
        )
        print("  " + msg.content[0].text.strip())
    else:
        print("\n(skipping LLM check — no ANTHROPIC_API_KEY)")

    print("\nAll good ✅")


def cli() -> None:
    try:
        run()
    except Exception as e:  # friendly failure for teammates
        print(f"\n❌ {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli()
