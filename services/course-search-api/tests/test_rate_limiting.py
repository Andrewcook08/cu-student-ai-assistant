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
from course_search_api.dependencies import get_current_user
from course_search_api.limiter import limiter
from course_search_api.main import app
from fastapi.testclient import TestClient
from shared.database import get_db

# Minimal valid register payload — passes RegisterRequest validation so the
# request reaches the limiter (Pydantic rejects bodies before the limiter fires).
_VALID_REGISTER_BODY = {
    "email": "ratelimit@colorado.edu",
    "password": "SecurePass1234!",
    "name": "Rate Limit Test",
}

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
    # Override get_current_user so rate-limit tests for authenticated routes
    # (e.g. GET /api/courses/search) don't fail with 401 before the limiter fires.
    app.dependency_overrides[get_current_user] = lambda: MagicMock()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def auth_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with auth and DB dependencies overridden for authenticated endpoint tests.

    Overrides get_current_user and get_db so the completed-courses endpoint
    succeeds without a real database or valid JWT.  decode_access_token is
    patched to return a deterministic user_id from any token string, enabling
    per-user isolation tests.
    """
    monkeypatch.setattr("course_search_api.main.engine", MagicMock())
    monkeypatch.setattr("course_search_api.main.Base", MagicMock())
    mock_driver = AsyncMock()
    mock_graph_db = MagicMock()
    mock_graph_db.driver.return_value = mock_driver
    monkeypatch.setattr("course_search_api.main.AsyncGraphDatabase", mock_graph_db)

    from course_search_api.dependencies import get_current_user
    from shared.database import get_db

    mock_user = MagicMock()
    mock_user.id = 1

    mock_db = MagicMock()
    # Empty payload means the route skips course-code validation and returns [].
    mock_db.query.return_value.filter.return_value.all.return_value = []

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def register_rate_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient for register rate-limit tests.

    Mocks DB so valid register requests succeed (200) without a live PostgreSQL
    connection.  The limiter counter increments on each passing request, so the
    rate-limit boundary can be exercised without hitting a real database.

    Note: db.refresh(user) is a no-op on the mock, so user.id is None in the
    returned payload — acceptable here since we only care about the status code.
    """
    monkeypatch.setattr("course_search_api.main.engine", MagicMock())
    monkeypatch.setattr("course_search_api.main.Base", MagicMock())
    mock_driver = AsyncMock()
    mock_graph_db = MagicMock()
    mock_graph_db.driver.return_value = mock_driver
    monkeypatch.setattr("course_search_api.main.AsyncGraphDatabase", mock_graph_db)

    mock_db = MagicMock()
    # No duplicate email found → uniqueness check passes.
    mock_db.query.return_value.filter.return_value.first.return_value = None

    app.dependency_overrides[get_db] = lambda: mock_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_EMBEDDING = [0.1] * 768
_FAKE_RESULTS = [{"code": "CSCI 4830", "title": "Machine Learning", "score": 0.95}]


def _bearer(user_id: str) -> dict[str, str]:
    """Return an Authorization header whose token encodes *user_id*.

    decode_access_token is patched in auth_client tests to parse the token
    value as a plain user_id string, so the actual JWT format doesn't matter.
    """
    return {"Authorization": f"Bearer {user_id}"}


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
    retry = int(sixth.headers["retry-after"])
    assert 1 <= retry <= 60  # 1-minute window


def test_login_5th_request_still_allowed(client: TestClient) -> None:
    """The 5th POST /api/auth/login must NOT be rate-limited (boundary check)."""
    for _ in range(4):
        client.post("/api/auth/login", json={})

    fifth = client.post("/api/auth/login", json={})
    assert fifth.status_code == 501  # stub, not 429


# ---------------------------------------------------------------------------
# POST /api/auth/register — 3/hour per IP
# ---------------------------------------------------------------------------


def test_4th_register_returns_429(register_rate_client: TestClient) -> None:
    """The 4th POST /api/auth/register within an hour must return 429."""
    for i in range(3):
        resp = register_rate_client.post("/api/auth/register", json=_VALID_REGISTER_BODY)
        assert resp.status_code == 200, f"Expected 200 on request {i + 1}, got {resp.status_code}"

    fourth = register_rate_client.post("/api/auth/register", json=_VALID_REGISTER_BODY)
    assert fourth.status_code == 429
    assert fourth.json() == {"detail": "Too many requests"}
    assert "retry-after" in fourth.headers
    retry = int(fourth.headers["retry-after"])
    assert 1 <= retry <= 3600  # 1-hour window


def test_register_3rd_request_still_allowed(register_rate_client: TestClient) -> None:
    """The 3rd POST /api/auth/register must NOT be rate-limited (boundary check)."""
    for _ in range(2):
        register_rate_client.post("/api/auth/register", json=_VALID_REGISTER_BODY)

    third = register_rate_client.post("/api/auth/register", json=_VALID_REGISTER_BODY)
    assert third.status_code == 200  # not 429


# ---------------------------------------------------------------------------
# GET /api/courses/search — 30/minute per user (user_key_func, IP fallback)
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
            assert resp.status_code == 200, (
                f"Expected 200 on request {i + 1}, got {resp.status_code}"
            )

        thirty_first = client.get("/api/courses/search?q=test")

    assert thirty_first.status_code == 429
    assert thirty_first.json() == {"detail": "Too many requests"}
    assert "retry-after" in thirty_first.headers
    retry = int(thirty_first.headers["retry-after"])
    assert 1 <= retry <= 60  # 1-minute window


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


# ---------------------------------------------------------------------------
# PUT /api/students/me/completed-courses — 10/minute per user (user_key_func)
# ---------------------------------------------------------------------------


def test_11th_completed_courses_returns_429(auth_client: TestClient) -> None:
    """The 11th PUT /api/students/me/completed-courses within a minute must return 429."""
    with patch(
        "course_search_api.limiter.decode_access_token",
        return_value="1",
    ):
        for i in range(10):
            resp = auth_client.put(
                "/api/students/me/completed-courses",
                json=[],
                headers=_bearer("user1"),
            )
            assert resp.status_code == 200, (
                f"Expected 200 on request {i + 1}, got {resp.status_code}"
            )

        eleventh = auth_client.put(
            "/api/students/me/completed-courses",
            json=[],
            headers=_bearer("user1"),
        )

    assert eleventh.status_code == 429
    assert eleventh.json() == {"detail": "Too many requests"}
    assert "retry-after" in eleventh.headers
    retry = int(eleventh.headers["retry-after"])
    assert 1 <= retry <= 60  # 1-minute window


def test_completed_courses_10th_request_still_allowed(auth_client: TestClient) -> None:
    """The 10th PUT /api/students/me/completed-courses must NOT be rate-limited."""
    with patch(
        "course_search_api.limiter.decode_access_token",
        return_value="1",
    ):
        for _ in range(9):
            auth_client.put(
                "/api/students/me/completed-courses",
                json=[],
                headers=_bearer("user1"),
            )

        tenth = auth_client.put(
            "/api/students/me/completed-courses",
            json=[],
            headers=_bearer("user1"),
        )

    assert tenth.status_code == 200


def test_completed_courses_per_user_isolation(auth_client: TestClient) -> None:
    """Exhausting user A's quota must not affect user B's quota."""

    def _decode(token: str) -> str:
        # token value is used directly as the user_id
        return token

    with patch("course_search_api.limiter.decode_access_token", side_effect=_decode):
        # Exhaust user A's 10-request quota
        for _ in range(10):
            auth_client.put(
                "/api/students/me/completed-courses",
                json=[],
                headers=_bearer("userA"),
            )
        over_limit = auth_client.put(
            "/api/students/me/completed-courses",
            json=[],
            headers=_bearer("userA"),
        )
        assert over_limit.status_code == 429

        # User B should still be within their own quota
        user_b_resp = auth_client.put(
            "/api/students/me/completed-courses",
            json=[],
            headers=_bearer("userB"),
        )
        assert user_b_resp.status_code == 200


# ---------------------------------------------------------------------------
# Cross-endpoint isolation
# ---------------------------------------------------------------------------


def test_login_limit_does_not_bleed_into_search(client: TestClient) -> None:
    """Exhausting the login limit must not consume the search quota."""
    # Exhaust login (5/minute)
    for _ in range(5):
        client.post("/api/auth/login", json={})
    assert client.post("/api/auth/login", json={}).status_code == 429

    # Search quota is completely independent
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
        search_resp = client.get("/api/courses/search?q=test")

    assert search_resp.status_code == 200
