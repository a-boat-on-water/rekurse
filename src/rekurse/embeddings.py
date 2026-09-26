"""Text embeddings: Voyage AI if VOYAGE_API_KEY is set, otherwise OpenAI."""
import os

from dotenv import load_dotenv

load_dotenv()

VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-3.5")      # 1024 dims
OPENAI_MODEL = os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small")  # 1536 dims


def provider() -> str:
    if os.environ.get("VOYAGE_API_KEY"):
        return "voyage"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    raise RuntimeError("Set VOYAGE_API_KEY or OPENAI_API_KEY in .env")


def dims() -> int:
    return 1024 if provider() == "voyage" else 1536


def embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Embed a batch of texts. Use input_type='query' for search queries."""
    if provider() == "voyage":
        import voyageai
        return voyageai.Client().embed(texts, model=VOYAGE_MODEL, input_type=input_type).embeddings
    from openai import OpenAI
    resp = OpenAI().embeddings.create(model=OPENAI_MODEL, input=texts)
    return [d.embedding for d in resp.data]
