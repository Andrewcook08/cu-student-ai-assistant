"""Ollama HTTP client for embedding generation.

Used by the semantic search endpoint (API-003) to convert a text query
into a 768-dimensional vector via the nomic-embed-text model.
"""

import httpx
from shared.config import settings


async def get_embedding(text: str) -> list[float]:
    """Return a 768-dim embedding vector for *text* from Ollama.

    Raises:
        httpx.HTTPStatusError: if Ollama returns a non-2xx response.
        httpx.TimeoutException: if Ollama takes longer than 120 s.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/embeddings",
            json={"model": settings.ollama_embed_model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]  # type: ignore[no-any-return]
