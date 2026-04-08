"""Unit tests for chat_service.services.ollama_service (CUAI-35).

The httpx.AsyncClient is mocked — these tests assert the request shape
(endpoint, model, body) and exception translation without hitting a real
Ollama instance. Mirrors the AsyncMock/MagicMock pattern used by
``test_neo4j_service.py``; no new dependencies (no respx).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from chat_service.services.ollama_service import (
    OllamaServiceError,
    OllamaTimeoutError,
    chat_completion,
    get_embedding,
)
from shared.config import settings


def _make_client(
    json_payload: Any = None,
    *,
    raises: Exception | None = None,
    raise_status: Exception | None = None,
) -> MagicMock:
    """Build a mock AsyncClient whose ``.post`` returns (or raises) as configured.

    Parameters
    ----------
    json_payload:
        Value returned by ``response.json()``.
    raises:
        If set, ``client.post`` itself raises this exception (simulates
        connect / timeout errors mid-request).
    raise_status:
        If set, ``response.raise_for_status()`` raises this exception
        (simulates a non-2xx HTTP response reaching the caller).
    """
    response = MagicMock()
    response.json = MagicMock(return_value=json_payload)
    if raise_status is not None:
        response.raise_for_status = MagicMock(side_effect=raise_status)
    else:
        response.raise_for_status = MagicMock(return_value=None)
    post = AsyncMock(side_effect=raises) if raises is not None else AsyncMock(return_value=response)
    client = MagicMock()
    client.post = post
    return client


def _http_status_error() -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError with mock request/response for tests."""
    return httpx.HTTPStatusError(
        "server error",
        request=MagicMock(),
        response=MagicMock(),
    )


# ─── get_embedding ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_embedding_returns_768_dim_vector() -> None:
    vector = [0.1] * 768
    client = _make_client({"embeddings": [vector]})

    result = await get_embedding(client, "data science")

    assert len(result) == 768
    assert result == vector


@pytest.mark.asyncio
async def test_get_embedding_posts_to_embed_endpoint_with_configured_model() -> None:
    client = _make_client({"embeddings": [[0.0] * 768]})

    await get_embedding(client, "data science")

    client.post.assert_awaited_once()
    args, kwargs = client.post.await_args.args, client.post.await_args.kwargs
    assert args == ("/api/embed",)
    assert kwargs["json"] == {
        "model": settings.ollama_embed_model,
        "input": "data science",
    }


@pytest.mark.asyncio
async def test_get_embedding_timeout_raises_friendly_error() -> None:
    original = httpx.ReadTimeout("read timed out")
    client = _make_client(raises=original)

    with pytest.raises(OllamaTimeoutError) as excinfo:
        await get_embedding(client, "ml")

    assert "taking longer than expected" in str(excinfo.value)
    assert excinfo.value.__cause__ is original


@pytest.mark.asyncio
async def test_get_embedding_connection_error_raises_service_error() -> None:
    original = httpx.ConnectError("nope")
    client = _make_client(raises=original)

    with pytest.raises(OllamaServiceError) as excinfo:
        await get_embedding(client, "ml")

    assert "temporarily unavailable" in str(excinfo.value)
    assert excinfo.value.__cause__ is original


# ─── chat_completion ────────────────────────────────────────────────────


_TOOL_MESSAGE = {
    "content": "",
    "tool_calls": [{"function": {"name": "search_courses", "arguments": {"query": "ml"}}}],
}


@pytest.mark.asyncio
async def test_chat_completion_returns_message_with_tool_calls() -> None:
    client = _make_client({"message": _TOOL_MESSAGE})
    messages = [{"role": "user", "content": "find ML courses"}]

    result = await chat_completion(client, messages, tools=[{"type": "function"}])

    assert result == _TOOL_MESSAGE
    assert result["tool_calls"][0]["function"]["name"] == "search_courses"


@pytest.mark.asyncio
async def test_chat_completion_posts_to_chat_endpoint_with_model_and_tools() -> None:
    client = _make_client({"message": {"content": "hi"}})
    messages = [{"role": "user", "content": "hello"}]
    tools = [{"type": "function", "function": {"name": "search_courses"}}]

    await chat_completion(client, messages, tools=tools)

    client.post.assert_awaited_once()
    args, kwargs = client.post.await_args.args, client.post.await_args.kwargs
    assert args == ("/api/chat",)
    body = kwargs["json"]
    assert body["model"] == settings.ollama_model
    assert body["messages"] == messages
    assert body["stream"] is False
    assert body["tools"] == tools


@pytest.mark.asyncio
async def test_chat_completion_omits_tools_key_when_none() -> None:
    client = _make_client({"message": {"content": "hi"}})

    await chat_completion(client, [{"role": "user", "content": "hi"}])

    body = client.post.await_args.kwargs["json"]
    assert "tools" not in body
    assert "format" not in body
    assert "options" not in body
    assert body["stream"] is False
    assert body["model"] == settings.ollama_model


@pytest.mark.asyncio
async def test_chat_completion_forwards_format_schema() -> None:
    """A JSON schema passed via *format* must reach Ollama's request body verbatim."""
    schema = {
        "type": "object",
        "properties": {"intent": {"type": "string", "enum": ["a", "b"]}},
        "required": ["intent"],
    }
    client = _make_client({"message": {"content": '{"intent": "a"}'}})

    await chat_completion(
        client,
        [{"role": "user", "content": "hi"}],
        format=schema,
    )

    body = client.post.await_args.kwargs["json"]
    assert body["format"] == schema


@pytest.mark.asyncio
async def test_chat_completion_forwards_options() -> None:
    """*options* is forwarded so callers can pin temperature etc."""
    client = _make_client({"message": {"content": "hi"}})

    await chat_completion(
        client,
        [{"role": "user", "content": "hi"}],
        options={"temperature": 0},
    )

    body = client.post.await_args.kwargs["json"]
    assert body["options"] == {"temperature": 0}


@pytest.mark.asyncio
async def test_chat_completion_timeout_raises_friendly_error() -> None:
    original = httpx.ReadTimeout("read timed out")
    client = _make_client(raises=original)

    with pytest.raises(OllamaTimeoutError) as excinfo:
        await chat_completion(client, [{"role": "user", "content": "hi"}])

    assert "taking longer than expected" in str(excinfo.value)
    assert excinfo.value.__cause__ is original


@pytest.mark.asyncio
async def test_chat_completion_connection_error_raises_service_error() -> None:
    original = httpx.ConnectError("nope")
    client = _make_client(raises=original)

    with pytest.raises(OllamaServiceError) as excinfo:
        await chat_completion(client, [{"role": "user", "content": "hi"}])

    assert "temporarily unavailable" in str(excinfo.value)
    assert excinfo.value.__cause__ is original


# ─── HTTP status error translation ──────────────────────────────────────


@pytest.mark.asyncio
async def test_get_embedding_http_status_error_raises_service_error() -> None:
    original = _http_status_error()
    client = _make_client({"embeddings": [[0.0] * 768]}, raise_status=original)

    with pytest.raises(OllamaServiceError) as excinfo:
        await get_embedding(client, "ml")

    assert "temporarily unavailable" in str(excinfo.value)
    assert excinfo.value.__cause__ is original


@pytest.mark.asyncio
async def test_chat_completion_http_status_error_raises_service_error() -> None:
    original = _http_status_error()
    client = _make_client({"message": {"content": "hi"}}, raise_status=original)

    with pytest.raises(OllamaServiceError) as excinfo:
        await chat_completion(client, [{"role": "user", "content": "hi"}])

    assert "temporarily unavailable" in str(excinfo.value)
    assert excinfo.value.__cause__ is original


# ─── Malformed response translation ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_embedding_empty_embeddings_raises_service_error() -> None:
    client = _make_client({"embeddings": []})

    with pytest.raises(OllamaServiceError) as excinfo:
        await get_embedding(client, "ml")

    assert "unexpected response" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert isinstance(excinfo.value.__cause__, IndexError)


@pytest.mark.asyncio
async def test_get_embedding_missing_embeddings_key_raises_service_error() -> None:
    client = _make_client({"error": "model not loaded"})

    with pytest.raises(OllamaServiceError) as excinfo:
        await get_embedding(client, "ml")

    assert "unexpected response" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert isinstance(excinfo.value.__cause__, KeyError)


@pytest.mark.asyncio
async def test_chat_completion_missing_message_key_raises_service_error() -> None:
    client = _make_client({"error": "model not loaded"})

    with pytest.raises(OllamaServiceError) as excinfo:
        await chat_completion(client, [{"role": "user", "content": "hi"}])

    assert "unexpected response" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert isinstance(excinfo.value.__cause__, KeyError)
