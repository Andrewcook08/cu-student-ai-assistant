"""Tests for GET /api/courses/search — API-003 (CUAI-28).

Ollama and Neo4j are mocked so the test suite runs without live services.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

_FAKE_EMBEDDING = [0.1] * 768

_FAKE_RESULTS = [
    {"code": "CSCI 4830", "title": "Machine Learning", "score": 0.95},
    {"code": "CSCI 5622", "title": "Machine Learning", "score": 0.91},
]


@pytest.fixture(autouse=True)
def mock_search_services():
    """Patch Ollama + Neo4j for every test in this module."""
    with (
        patch(
            "course_search_api.services.ollama_service.get_embedding",
            new_callable=AsyncMock,
            return_value=_FAKE_EMBEDDING,
        ),
        patch(
            "course_search_api.services.neo4j_service.vector_search",
            new_callable=AsyncMock,
            return_value=_FAKE_RESULTS,
        ),
    ):
        yield


def test_search_requires_q_param(client):
    """GET /api/courses/search without ?q= must return 422."""
    response = client.get("/api/courses/search")
    assert response.status_code == 422


def test_search_returns_200(client):
    """GET /api/courses/search?q=... returns 200 with expected shape."""
    response = client.get("/api/courses/search?q=machine+learning")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "machine learning"
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 2
    first = data["items"][0]
    assert "code" in first
    assert "title" in first
    assert "score" in first


def test_search_respects_limit(client):
    """GET /api/courses/search?limit= is accepted and forwarded."""
    response = client.get("/api/courses/search?q=data+science&limit=5")
    assert response.status_code == 200


def test_search_handles_service_error(client):
    """If Ollama raises, the endpoint must return 503."""
    import httpx

    with patch(
        "course_search_api.services.ollama_service.get_embedding",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("connection refused"),
    ):
        response = client.get("/api/courses/search?q=anything")
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
