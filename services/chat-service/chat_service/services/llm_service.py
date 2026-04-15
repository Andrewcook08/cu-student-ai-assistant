"""LLM and embedding transport layer for the chat service.

Dual-backend module:

- ``get_embedding``   → Ollama ``POST /api/embed`` (nomic-embed-text, 768-dim)
- ``chat_completion`` → Anthropic Messages API via the ``anthropic`` SDK

The Ollama ``httpx.AsyncClient`` and Anthropic ``AsyncAnthropic`` client are
both owned by ``main.py`` lifespan and injected per call.

Domain errors share a common ``LLMError`` base so callers can handle any
LLM failure with a single ``except``:

- ``LLMError``         — base class; catch this for any LLM failure
- ``LLMTimeoutError``  — timeout on the transport
- ``LLMServiceError``  — connect / network / HTTP-status / malformed response
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

import anthropic
import httpx
from shared.config import settings


class LLMError(RuntimeError):
    """Base class for llm_service failures — catch this to handle any LLM error."""


class LLMTimeoutError(LLMError):
    """Raised when an LLM call exceeds the configured timeout."""


class LLMServiceError(LLMError):
    """Raised when the LLM is unreachable, returns an error, or gives a malformed response."""


class ChatMessage(TypedDict):
    role: NotRequired[str]
    content: str


_TIMEOUT_MESSAGE = "The AI is taking longer than expected. Please try again in a moment."
_SERVICE_MESSAGE = "The AI service is temporarily unavailable. Please try again."
_MALFORMED_MESSAGE = "The AI returned an unexpected response. Please try again."


async def get_embedding(client: httpx.AsyncClient, text: str) -> list[float]:
    """Return the embedding vector for *text* from Ollama.

    POSTs to ``/api/embed`` with the configured embed model and returns the
    first vector from the ``embeddings`` array (768-dim for nomic-embed-text).
    """
    try:
        response = await client.post(
            "/api/embed",
            json={"model": settings.ollama_embed_model, "input": text},
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(_TIMEOUT_MESSAGE) from exc
    except httpx.HTTPError as exc:
        raise LLMServiceError(_SERVICE_MESSAGE) from exc

    try:
        embeddings: list[list[float]] = response.json()["embeddings"]
        return embeddings[0]
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMServiceError(_MALFORMED_MESSAGE) from exc


async def chat_completion(
    client: anthropic.AsyncAnthropic,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 1.0,
    max_tokens: int = 4096,
) -> ChatMessage:
    """Return the assistant message from an Anthropic chat completion.

    Accepts a flat message list where ``role="system"`` messages are
    extracted and passed via the Anthropic ``system`` parameter.
    Remaining messages (``user``/``assistant``) are forwarded directly.
    """
    system_parts: list[str] = []
    api_messages: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role", "user")
        if role == "system":
            system_parts.append(msg["content"])
        else:
            api_messages.append({"role": role, "content": msg["content"]})

    kwargs: dict[str, Any] = {
        "model": settings.anthropic_model,
        "messages": api_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system_parts:
        kwargs["system"] = "\n\n".join(system_parts)

    try:
        response = await client.messages.create(**kwargs)
    except anthropic.APITimeoutError as exc:
        raise LLMTimeoutError(_TIMEOUT_MESSAGE) from exc
    except anthropic.APIError as exc:
        raise LLMServiceError(_SERVICE_MESSAGE) from exc

    try:
        text = response.content[0].text
    except (IndexError, AttributeError) as exc:
        raise LLMServiceError(_MALFORMED_MESSAGE) from exc

    return ChatMessage(content=text)
