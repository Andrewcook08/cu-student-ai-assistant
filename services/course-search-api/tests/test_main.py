"""Tests for course_search_api.main lifespan wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

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
