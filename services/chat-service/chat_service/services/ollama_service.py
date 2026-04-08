"""Ollama async transport layer for the chat service.

Thin wrappers around the two Ollama HTTP endpoints that the chat pipeline
needs:

- ``get_embedding``   → ``POST /api/embed`` (nomic-embed-text, 768-dim)
- ``chat_completion`` → ``POST /api/chat`` (gpt-oss:20b w/ optional tool calls)

The ``httpx.AsyncClient`` is owned by ``main.py`` lifespan (with the 120s
read timeout configured there) and injected per call, mirroring the
``neo4j_service`` pattern. The chat service uses this transport directly.
A separate queue layer may sit in front of it later; this module stays a
thin wire-protocol wrapper either way.

Both helpers translate httpx exceptions into domain errors with
user-friendly messages, all sharing a common ``OllamaError`` base so
callers can handle any Ollama failure with a single ``except``:

- ``OllamaError``         — base class; catch this for any Ollama failure
- ``OllamaTimeoutError``  — any timeout on the transport
- ``OllamaServiceError``  — connect / network / HTTP-status / malformed response

The original exception is chained via ``raise ... from exc`` so logs keep
the underlying detail.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict, cast

import httpx
from shared.config import settings


class OllamaError(RuntimeError):
    """Base class for ollama_service failures — catch this to handle any Ollama error."""


class OllamaTimeoutError(OllamaError):
    """Raised when an Ollama call exceeds the configured timeout."""


class OllamaServiceError(OllamaError):
    """Raised when Ollama is unreachable, returns an HTTP error, or returns a malformed response."""


class ToolCall(TypedDict):
    function: dict[str, Any]  # {"name": str, "arguments": dict}


class ChatMessage(TypedDict):
    role: NotRequired[str]
    content: str
    tool_calls: NotRequired[list[ToolCall]]


_TIMEOUT_MESSAGE = "The AI is taking longer than expected. Please try again in a moment."
_SERVICE_MESSAGE = "The AI service is temporarily unavailable. Please try again."
_MALFORMED_MESSAGE = "The AI returned an unexpected response. Please try again."


async def get_embedding(client: httpx.AsyncClient, text: str) -> list[float]:
    """Return the embedding vector for *text* from Ollama.

    POSTs to ``/api/embed`` with the configured embed model and returns the
    first vector from the ``embeddings`` array (768-dim for nomic-embed-text).
    The wire format matches ``data/ingest/build_embeddings.py``.
    """
    try:
        response = await client.post(
            "/api/embed",
            json={"model": settings.ollama_embed_model, "input": text},
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        # TimeoutException must be caught before HTTPError because in httpx
        # it inherits from HTTPError via RequestError.
        raise OllamaTimeoutError(_TIMEOUT_MESSAGE) from exc
    except httpx.HTTPError as exc:
        raise OllamaServiceError(_SERVICE_MESSAGE) from exc

    try:
        embeddings: list[list[float]] = response.json()["embeddings"]
        return embeddings[0]
    except (KeyError, IndexError, ValueError) as exc:
        # KeyError: missing "embeddings" key (e.g. {"error": "..."}).
        # IndexError: empty "embeddings" list.
        # ValueError: response body was not valid JSON.
        raise OllamaServiceError(_MALFORMED_MESSAGE) from exc


async def chat_completion(
    client: httpx.AsyncClient,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    format: dict[str, Any] | str | None = None,
    options: dict[str, Any] | None = None,
) -> ChatMessage:
    """Return the assistant message dict from an Ollama chat completion.

    POSTs to ``/api/chat`` with ``stream=False``. The ``tools``, ``format``,
    and ``options`` keys are each only included in the request body when
    the corresponding argument is not ``None`` — Ollama treats the
    presence of these keys as feature flags, and we don't want to flip
    them on accidentally.

    *format* enables Ollama's structured-output mode. Pass ``"json"`` for
    free-form JSON, or a JSON Schema dict for constrained decoding (the
    model is forced via logit masking to emit only schema-conforming
    tokens). The intent classifier uses an enum schema to guarantee one
    of five labels.

    *options* is forwarded to Ollama's request ``options`` field. Used by
    callers that need to pin sampler params — e.g. ``{"temperature": 0}``
    for deterministic classification.

    Returns the inner ``message`` dict, which contains ``content`` and
    (when the model elected to call a tool) ``tool_calls``. When *format*
    is a JSON schema, ``content`` will be a JSON string the caller is
    responsible for parsing.
    """
    body: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
    }
    if tools is not None:
        body["tools"] = tools
    if format is not None:
        body["format"] = format
    if options is not None:
        body["options"] = options

    try:
        response = await client.post("/api/chat", json=body)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise OllamaTimeoutError(_TIMEOUT_MESSAGE) from exc
    except httpx.HTTPError as exc:
        raise OllamaServiceError(_SERVICE_MESSAGE) from exc

    try:
        message = response.json()["message"]
    except (KeyError, ValueError) as exc:
        # KeyError: missing "message" key (e.g. {"error": "..."}).
        # ValueError: response body was not valid JSON.
        raise OllamaServiceError(_MALFORMED_MESSAGE) from exc

    # Schema is validated by the LLM tool layer downstream; trust the wire
    # shape here.
    return cast(ChatMessage, message)
