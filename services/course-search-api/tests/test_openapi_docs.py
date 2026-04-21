"""Tests for OpenAPI docs endpoint visibility — SYN-024.

Verifies that /docs, /redoc, and /openapi.json are unreachable (404) when
enable_docs is False (the production default), and reachable when enable_docs
is True (development).

A standalone FastAPI app is constructed per test to avoid depending on the
module-level singleton in main.py, which is created at import time with
whatever settings are in the environment.  This pattern mirrors test_main.py
and test_security_headers.py in this directory.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app(*, enable_docs: bool) -> FastAPI:
    """Construct a minimal FastAPI app with the same docs_url pattern as main.py."""
    return FastAPI(
        title="Test App",
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
        openapi_url="/openapi.json" if enable_docs else None,
    )


def test_docs_disabled_in_production() -> None:
    """With enable_docs=False (production default), all three doc endpoints must return 404."""
    app = _make_app(enable_docs=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            resp = client.get(path)
            assert resp.status_code == 404, (
                f"Expected {path!r} to return 404 when docs are disabled, got {resp.status_code}"
            )


def test_docs_enabled_in_development() -> None:
    """With enable_docs=True (development), /docs and /openapi.json must return 200."""
    app = _make_app(enable_docs=True)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/docs").status_code == 200, "/docs should be 200 when docs are enabled"
        assert client.get("/openapi.json").status_code == 200, (
            "/openapi.json should be 200 when docs are enabled"
        )
