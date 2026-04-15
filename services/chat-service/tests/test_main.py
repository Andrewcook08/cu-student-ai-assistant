"""Tests for chat_service.main lifespan wiring.

These tests pin the httpx timeout configuration (for the Ollama
embeddings client) and the Anthropic SDK client set up in the FastAPI
lifespan. The ``TestClient`` context manager enters the lifespan; the
Neo4j driver constructor is sync and does not actually connect, so no
live Neo4j is required.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def test_lifespan_configures_ollama_client_with_120s_read_timeout() -> None:
    from chat_service.main import app

    with TestClient(app):
        client = app.state.ollama_client
        assert client.timeout.read == 120.0
        # Tight connect timeout — unreachable Ollama should surface quickly.
        assert client.timeout.connect == 10.0


def test_lifespan_creates_anthropic_client() -> None:
    """Pin that the lifespan wires an AsyncAnthropic client onto app.state.

    This client is used for LLM inference (chat completions, intent
    classification fallback, summary generation) after the Ollama-to-
    Anthropic migration.
    """
    import anthropic
    from chat_service.main import app

    with TestClient(app):
        client = app.state.anthropic_client
        assert isinstance(client, anthropic.AsyncAnthropic)


def test_lifespan_invokes_validate_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin that lifespan calls settings.validate_production() on startup.

    If a future refactor drops or reorders the call, this test fails
    instead of silently turning SEC-006 into a no-op in production.
    """
    from chat_service.main import app
    from shared.config import settings

    spy = MagicMock()
    # Pydantic BaseSettings rejects setattr on instances for non-fields;
    # patch the method on the class so the instance call is intercepted.
    monkeypatch.setattr(type(settings), "validate_production", spy)

    with TestClient(app):
        pass

    spy.assert_called_once()


def test_lifespan_builds_postgres_engine() -> None:
    """Pin that the lifespan wires an async Postgres engine onto app.state.

    ``create_async_engine`` is lazy, so this assertion does not require
    a running Postgres — it just proves the wiring is present so a
    future refactor that forgets to construct the engine fails here
    instead of at first tool call.
    """
    from chat_service.main import app
    from sqlalchemy.ext.asyncio import AsyncEngine

    with TestClient(app):
        engine = app.state.postgres_engine
        assert isinstance(engine, AsyncEngine)
