"""Tests for GET /api/courses/search — API-003 (CUAI-28).

Ollama and Neo4j are mocked so the test suite runs without live services.
"""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, patch

import pytest

_FAKE_EMBEDDING = [0.1] * 768

_FAKE_RESULTS = [
    {"code": "CSCI 4830", "title": "Machine Learning", "score": 0.95},
    {"code": "CSCI 5622", "title": "Machine Learning", "score": 0.91},
]


@pytest.fixture(autouse=True)
def mock_search_services():
    """Patch Ollama + Neo4j at the routes level for every test in this module.

    Yields (mock_get_embedding, mock_vector_search) so individual tests can
    assert on call arguments.
    """
    with (
        patch(
            "course_search_api.routes.courses.get_embedding",
            new_callable=AsyncMock,
            return_value=_FAKE_EMBEDDING,
        ) as mock_embed,
        patch(
            "course_search_api.routes.courses.vector_search",
            new_callable=AsyncMock,
            return_value=_FAKE_RESULTS,
        ) as mock_search,
    ):
        yield mock_embed, mock_search


# ---------------------------------------------------------------------------
# Auth lock-in
# ---------------------------------------------------------------------------


def test_search_requires_auth(client):
    """GET /api/courses/search without a Bearer token must return 401 or 403."""
    response = client.get("/api/courses/search?q=machine+learning")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Route behaviour
# ---------------------------------------------------------------------------


def test_search_route_not_swallowed_by_catch_all(client, auth_headers):
    """Regression: /search must be declared before /{code:path} or it returns 404."""
    response = client.get("/api/courses/search?q=x", headers=auth_headers)
    assert response.status_code != 404


def test_search_requires_q_param(client, auth_headers):
    """GET /api/courses/search without ?q= must return 422."""
    response = client.get("/api/courses/search", headers=auth_headers)
    assert response.status_code == 422


def test_search_returns_200(client, auth_headers, mock_search_services):
    """GET /api/courses/search?q=... returns 200 with expected shape and calls services."""
    mock_embed, mock_search = mock_search_services

    response = client.get("/api/courses/search?q=machine+learning", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "machine learning"
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 2
    first = data["items"][0]
    assert "code" in first
    assert "title" in first
    assert "score" in first

    # Verify both services were called with the correct arguments
    mock_embed.assert_called_once_with(ANY, "machine learning")
    mock_search.assert_called_once_with(ANY, _FAKE_EMBEDDING, limit=10)


def test_search_respects_limit(client, auth_headers, mock_search_services):
    """GET /api/courses/search?limit= is accepted and forwarded to vector_search."""
    _, mock_search = mock_search_services

    response = client.get("/api/courses/search?q=data+science&limit=5", headers=auth_headers)

    assert response.status_code == 200
    mock_search.assert_called_once_with(ANY, _FAKE_EMBEDDING, limit=5)


def test_search_handles_service_error(client, auth_headers):
    """If Ollama raises, the endpoint must return 503 with a generic message."""
    import httpx

    with patch(
        "course_search_api.routes.courses.get_embedding",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("connection refused"),
    ):
        response = client.get("/api/courses/search?q=anything", headers=auth_headers)

    assert response.status_code == 503
    assert response.json()["detail"] == "Search service temporarily unavailable"
