"""Tests for CORS preflight behaviour — SYN-023.

Verifies that the allowed method set is exactly what the application declares
and does not accidentally include dangerous verbs such as DELETE or PATCH.
No database is required: OPTIONS preflight requests are handled entirely by
the CORSMiddleware and never reach a route handler.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def _stub_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub heavy lifespan dependencies so TestClient starts without live infra."""
    monkeypatch.setattr("course_search_api.main.engine", MagicMock())
    monkeypatch.setattr("course_search_api.main.Base", MagicMock())
    mock_driver = AsyncMock()
    mock_graph_db = MagicMock()
    mock_graph_db.driver.return_value = mock_driver
    monkeypatch.setattr("course_search_api.main.AsyncGraphDatabase", mock_graph_db)


def test_cors_preflight_allows_only_expected_methods(_stub_lifespan: None) -> None:
    """OPTIONS preflight must reflect exactly GET, POST, PUT, OPTIONS — nothing more.

    DELETE, PATCH, and HEAD are security-sensitive and must not appear in
    Access-Control-Allow-Methods.  The allowed set is compared as a sorted
    list so order differences do not cause false failures.
    """
    from course_search_api.main import app
    from shared.config import settings

    # Use the first configured origin so the middleware echoes it back.
    origin = settings.cors_origins_list[0]

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

    allowed_header = response.headers.get("access-control-allow-methods", "")
    allowed_methods = sorted(m.strip().upper() for m in allowed_header.split(",") if m.strip())

    expected_methods = sorted(["GET", "OPTIONS", "POST", "PUT"])
    assert allowed_methods == expected_methods, (
        f"access-control-allow-methods mismatch: got {allowed_methods!r}, "
        f"expected {expected_methods!r}"
    )

    forbidden = {"DELETE", "PATCH", "HEAD"}
    present_forbidden = forbidden & set(allowed_methods)
    assert not present_forbidden, (
        f"Dangerous HTTP methods present in CORS allow list: {present_forbidden!r}"
    )
