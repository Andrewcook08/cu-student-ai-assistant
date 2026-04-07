"""Ollama HTTP client for embedding generation.

Used by the semantic search endpoint (API-003) to convert a text query
into a 768-dimensional vector via the nomic-embed-text model.

The httpx.AsyncClient is injected rather than constructed per call so the
connection pool is reused across requests (see lifespan in main.py).
"""

import httpx
from shared.config import settings


async def get_embedding(client: httpx.AsyncClient, text: str) -> list[float]:
    """Return a 768-dim embedding vector for *text* from Ollama.

    Args:
        client: The shared AsyncClient from app.state (lifespan-managed).
        text:   The query string to embed.

    Raises:
        httpx.HTTPError: if Ollama returns a non-2xx response.
        httpx.TimeoutException: if Ollama takes longer than the client timeout.
    """
    resp = await client.post(
        f"{settings.ollama_url}/api/embeddings",
        json={"model": settings.ollama_embed_model, "prompt": text},
    )
    resp.raise_for_status()
    return resp.json()["embedding"]  # type: ignore[no-any-return]
