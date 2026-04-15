"""Unit tests for chat_service.services.llm_service (CUAI-35 / CUAI-87).

Dual-backend test suite:

- **Embedding tests** — httpx.AsyncClient is mocked; these tests assert the
  request shape (endpoint, model, body) and exception translation without
  hitting a real Ollama instance.
- **Chat completion tests** — anthropic.AsyncAnthropic is mocked; these tests
  assert that ``client.messages.create`` is called with the correct model,
  messages, system extraction, temperature, and max_tokens, and that Anthropic
  API errors are translated into ``LLMTimeoutError`` / ``LLMServiceError``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import anthropic
import httpx
import pytest
from chat_service.services.llm_service import (
    ChatMessage,
    LLMServiceError,
    LLMTimeoutError,
    chat_completion,
    get_embedding,
)
from shared.config import settings

# ─── Shared helpers ────────────────────────────────────────────────────


def _make_httpx_client(
    json_payload: Any = None,
    *,
    raises: Exception | None = None,
    raise_status: Exception | None = None,
) -> MagicMock:
    """Build a mock httpx.AsyncClient whose ``.post`` returns (or raises) as configured.

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


def _make_anthropic_client(*, response_text: str = "Hello") -> MagicMock:
    """Create a mock anthropic.AsyncAnthropic client."""
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.text = response_text
    mock_response.content = [mock_block]

    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=mock_response)
    return client


# ─── get_embedding ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_embedding_returns_768_dim_vector() -> None:
    vector = [0.1] * 768
    client = _make_httpx_client({"embeddings": [vector]})

    result = await get_embedding(client, "data science")

    assert len(result) == 768
    assert result == vector


@pytest.mark.asyncio
async def test_get_embedding_posts_to_embed_endpoint_with_configured_model() -> None:
    client = _make_httpx_client({"embeddings": [[0.0] * 768]})

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
    client = _make_httpx_client(raises=original)

    with pytest.raises(LLMTimeoutError) as excinfo:
        await get_embedding(client, "ml")

    assert "taking longer than expected" in str(excinfo.value)
    assert excinfo.value.__cause__ is original


@pytest.mark.asyncio
async def test_get_embedding_connection_error_raises_service_error() -> None:
    original = httpx.ConnectError("nope")
    client = _make_httpx_client(raises=original)

    with pytest.raises(LLMServiceError) as excinfo:
        await get_embedding(client, "ml")

    assert "temporarily unavailable" in str(excinfo.value)
    assert excinfo.value.__cause__ is original


# ─── get_embedding — HTTP status error translation ─────────────────────


@pytest.mark.asyncio
async def test_get_embedding_http_status_error_raises_service_error() -> None:
    original = _http_status_error()
    client = _make_httpx_client({"embeddings": [[0.0] * 768]}, raise_status=original)

    with pytest.raises(LLMServiceError) as excinfo:
        await get_embedding(client, "ml")

    assert "temporarily unavailable" in str(excinfo.value)
    assert excinfo.value.__cause__ is original


# ─── get_embedding — malformed response translation ────────────────────


@pytest.mark.asyncio
async def test_get_embedding_empty_embeddings_raises_service_error() -> None:
    client = _make_httpx_client({"embeddings": []})

    with pytest.raises(LLMServiceError) as excinfo:
        await get_embedding(client, "ml")

    assert "unexpected response" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert isinstance(excinfo.value.__cause__, IndexError)


@pytest.mark.asyncio
async def test_get_embedding_missing_embeddings_key_raises_service_error() -> None:
    client = _make_httpx_client({"error": "model not loaded"})

    with pytest.raises(LLMServiceError) as excinfo:
        await get_embedding(client, "ml")

    assert "unexpected response" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert isinstance(excinfo.value.__cause__, KeyError)


# ─── chat_completion ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_completion_returns_content() -> None:
    client = _make_anthropic_client(response_text="Here are some courses.")
    messages = [{"role": "user", "content": "find ML courses"}]

    result = await chat_completion(client, messages)

    assert result == ChatMessage(content="Here are some courses.")


@pytest.mark.asyncio
async def test_chat_completion_calls_anthropic_with_model_and_messages() -> None:
    client = _make_anthropic_client(response_text="hi")
    messages = [{"role": "user", "content": "hello"}]

    await chat_completion(client, messages)

    client.messages.create.assert_awaited_once()
    call_kwargs = client.messages.create.await_args.kwargs
    assert call_kwargs["model"] == settings.anthropic_model
    assert call_kwargs["messages"] == [{"role": "user", "content": "hello"}]
    assert call_kwargs["max_tokens"] == 4096
    assert call_kwargs["temperature"] == 1.0


@pytest.mark.asyncio
async def test_chat_completion_extracts_system_messages() -> None:
    """System-role messages are extracted into the Anthropic ``system`` parameter."""
    client = _make_anthropic_client(response_text="ok")
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "hello"},
    ]

    await chat_completion(client, messages)

    call_kwargs = client.messages.create.await_args.kwargs
    assert call_kwargs["system"] == "You are a helpful assistant."
    # System messages must NOT appear in the messages list.
    assert all(m["role"] != "system" for m in call_kwargs["messages"])


@pytest.mark.asyncio
async def test_chat_completion_forwards_temperature() -> None:
    client = _make_anthropic_client(response_text="hi")

    await chat_completion(
        client,
        [{"role": "user", "content": "hi"}],
        temperature=0.0,
    )

    call_kwargs = client.messages.create.await_args.kwargs
    assert call_kwargs["temperature"] == 0.0


@pytest.mark.asyncio
async def test_chat_completion_timeout_raises_llm_timeout_error() -> None:
    client = AsyncMock()
    client.messages.create = AsyncMock(side_effect=anthropic.APITimeoutError(request=MagicMock()))

    with pytest.raises(LLMTimeoutError) as excinfo:
        await chat_completion(client, [{"role": "user", "content": "hi"}])

    assert "taking longer than expected" in str(excinfo.value)


@pytest.mark.asyncio
async def test_chat_completion_api_error_raises_llm_service_error() -> None:
    client = AsyncMock()
    client.messages.create = AsyncMock(
        side_effect=anthropic.APIConnectionError(request=MagicMock())
    )

    with pytest.raises(LLMServiceError) as excinfo:
        await chat_completion(client, [{"role": "user", "content": "hi"}])

    assert "temporarily unavailable" in str(excinfo.value)


@pytest.mark.asyncio
async def test_chat_completion_malformed_response_raises_llm_service_error() -> None:
    """Empty ``.content`` list triggers LLMServiceError."""
    mock_response = MagicMock()
    mock_response.content = []  # empty — no text blocks

    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=mock_response)

    with pytest.raises(LLMServiceError) as excinfo:
        await chat_completion(client, [{"role": "user", "content": "hi"}])

    assert "unexpected response" in str(excinfo.value)
