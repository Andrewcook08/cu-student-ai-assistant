"""Integration test: security headers on chat-service responses (SEC-010 / CUAI-86)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

_ALWAYS_PRESENT = {
    "content-security-policy": "default-src 'self'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}


@pytest.fixture()
def _stub_lifespan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub heavy lifespan deps so TestClient starts without live infra."""
    mock_driver = AsyncMock()
    mock_graph_db = MagicMock()
    mock_graph_db.driver.return_value = mock_driver
    monkeypatch.setattr("chat_service.main.AsyncGraphDatabase", mock_graph_db)
    monkeypatch.setattr("chat_service.main.build_redis_client", MagicMock(return_value=AsyncMock()))
    mock_pg = MagicMock(return_value=AsyncMock())
    monkeypatch.setattr("chat_service.main.build_postgres_engine", mock_pg)
    monkeypatch.setattr("chat_service.main.make_tools", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr("chat_service.main.ToolExecutor", MagicMock())
    monkeypatch.setattr("chat_service.main.build_graph", MagicMock())


def test_security_headers_on_health(_stub_lifespan: None) -> None:
    """Every response includes the four always-on security headers."""
    from chat_service.main import app

    with TestClient(app) as client:
        resp = client.get("/api/chat/health")

    assert resp.status_code == 200
    for header, value in _ALWAYS_PRESENT.items():
        assert resp.headers.get(header) == value, f"Missing or wrong: {header}"


def test_no_hsts_in_development(_stub_lifespan: None) -> None:
    """HSTS must not appear when ENVIRONMENT is not production."""
    from chat_service.main import app

    with TestClient(app) as client:
        resp = client.get("/api/chat/health")

    assert "strict-transport-security" not in resp.headers
