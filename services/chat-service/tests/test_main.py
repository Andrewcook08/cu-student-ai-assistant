"""Tests for chat_service.main lifespan wiring.

These tests pin the httpx timeout configuration set up in the FastAPI
lifespan — the 120s read timeout is the inference budget, and the tight
connect timeout makes an unreachable Ollama surface quickly instead of
hanging for the full inference window. The ``TestClient`` context
manager enters the lifespan; the Neo4j driver constructor is sync and
does not actually connect, so no live Neo4j is required.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_lifespan_configures_ollama_client_with_120s_read_timeout() -> None:
    from chat_service.main import app

    with TestClient(app):
        client = app.state.ollama_client
        assert client.timeout.read == 120.0
        # Tight connect timeout — see Fix 2 in ollama_service hardening.
        assert client.timeout.connect == 10.0
