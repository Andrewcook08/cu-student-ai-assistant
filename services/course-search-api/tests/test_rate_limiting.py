"""Tests for SEC-007: slowapi rate limiting (CUAI-81).

Strategy
--------
Each test resets the limiter's in-memory storage before running so that
request counts from other tests don't spill over.  Tests call the limited
endpoint exactly (limit + 1) times and assert the final response is 429
with a Retry-After header.

The app lifespan connects to PostgreSQL and Neo4j, which are not needed for
rate-limit validation.  The ``client`` fixture patches out those connections
so the test suite runs without live infrastructure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from course_search_api.limiter import limiter
from course_search_api.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_limiter() -> None:
    """Wipe all in-memory rate-limit counters before each test."""
    limiter.reset()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with lifespan dependencies stubbed out.

    Rate-limit tests only need FastAPI routing and the slowapi middleware —
    not PostgreSQL, Neo4j, or httpx singletons.
    """
    monkeypatch.setattr("course_search_api.main.engine", MagicMock())
    monkeypatch.setattr("course_search_api.main.Base", MagicMock())
    # AsyncGraphDatabase.driver() must return an object whose .close() is
    # awaitable (the lifespan calls ``await driver.close()``).
    mock_driver = AsyncMock()
    mock_graph_db = MagicMock()
    mock_graph_db.driver.return_value = mock_driver
    monkeypatch.setattr("course_search_api.main.AsyncGraphDatabase", mock_graph_db)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_EMBEDDING = [0.1] * 768
_FAKE_RESULTS = [{"code": "CSCI 4830", "title": "Machine Learning", "score": 0.95}]


# ---------------------------------------------------------------------------
# POST /api/auth/login — 5/minute per IP
# ---------------------------------------------------------------------------


def test_6th_login_returns_429(client: TestClient) -> None:
    """The 6th POST /api/auth/login within a minute must return 429."""
    for i in range(5):
        resp = client.post("/api/auth/login", json={})
        # Stub returns 501; limiter hasn't fired yet
        assert resp.status_code == 501, f"Expected 501 on request {i + 1}, got {resp.status_code}"

    sixth = client.post("/api/auth/login", json={})
    assert sixth.status_code == 429
    assert sixth.json() == {"detail": "Too many requests"}
    assert "retry-after" in sixth.headers


def test_login_5th_request_still_allowed(client: TestClient) -> None:
    """The 5th POST /api/auth/login must NOT be rate-limited (boundary check)."""
    for _ in range(4):
        client.post("/api/auth/login", json={})

    fifth = client.post("/api/auth/login", json={})
    assert fifth.status_code == 501  # stub, not 429


# ---------------------------------------------------------------------------
# GET /api/courses/search — 30/minute per IP
# ---------------------------------------------------------------------------


def test_31st_search_returns_429(client: TestClient) -> None:
    """The 31st GET /api/courses/search within a minute must return 429."""
    with (
        patch(
            "course_search_api.routes.courses.get_embedding",
            new_callable=AsyncMock,
            return_value=_FAKE_EMBEDDING,
        ),
        patch(
            "course_search_api.routes.courses.vector_search",
            new_callable=AsyncMock,
            return_value=_FAKE_RESULTS,
        ),
    ):
        for i in range(30):
            resp = client.get("/api/courses/search?q=test")
            assert resp.status_code == 200, f"Expected 200 on request {i + 1}, got {resp.status_code}"

        thirty_first = client.get("/api/courses/search?q=test")

    assert thirty_first.status_code == 429
    assert thirty_first.json() == {"detail": "Too many requests"}
    assert "retry-after" in thirty_first.headers


def test_search_30th_request_still_allowed(client: TestClient) -> None:
    """The 30th GET /api/courses/search must NOT be rate-limited (boundary check)."""
    with (
        patch(
            "course_search_api.routes.courses.get_embedding",
            new_callable=AsyncMock,
            return_value=_FAKE_EMBEDDING,
        ),
        patch(
            "course_search_api.routes.courses.vector_search",
            new_callable=AsyncMock,
            return_value=_FAKE_RESULTS,
        ),
    ):
        for _ in range(29):
            client.get("/api/courses/search?q=test")

        thirtieth = client.get("/api/courses/search?q=test")
        assert thirtieth.status_code == 200
