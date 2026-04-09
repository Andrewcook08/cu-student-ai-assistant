"""Tests for course_search_api.main lifespan wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


def test_lifespan_invokes_validate_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin that lifespan calls settings.validate_production() on startup.

    If a future refactor drops or reorders the call, this test fails
    instead of silently turning SEC-006 into a no-op in production.
    """
    from course_search_api.main import app
    from shared.config import settings

    spy = MagicMock()
    # Pydantic BaseSettings rejects setattr on instances for non-fields;
    # patch the method on the class so the instance call is intercepted.
    monkeypatch.setattr(type(settings), "validate_production", spy)

    with TestClient(app):
        pass

    spy.assert_called_once()


def test_health_endpoint_remains_public(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/health must NOT require auth — used by load balancer probes.

    Lock-in: a future blanket auth middleware or accidental Depends(get_current_user)
    on the health route would break load balancer probes with no test failure to catch it.
    """
    from course_search_api.main import app

    monkeypatch.setattr("course_search_api.main.engine", MagicMock())
    monkeypatch.setattr("course_search_api.main.Base", MagicMock())
    mock_driver = AsyncMock()
    mock_graph_db = MagicMock()
    mock_graph_db.driver.return_value = mock_driver
    monkeypatch.setattr("course_search_api.main.AsyncGraphDatabase", mock_graph_db)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
