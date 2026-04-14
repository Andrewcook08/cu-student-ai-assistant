"""Unit tests for SecurityHeadersMiddleware (SEC-010 / CUAI-86)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.middleware import SecurityHeadersMiddleware

_ALWAYS_HEADERS = {
    "content-security-policy": "default-src 'self'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}


def _make_app(environment: str = "development") -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, environment=environment)

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_always_on_headers() -> None:
    client = TestClient(_make_app())
    resp = client.get("/ping")
    for header, value in _ALWAYS_HEADERS.items():
        assert resp.headers[header] == value


def test_no_hsts_in_development() -> None:
    client = TestClient(_make_app("development"))
    resp = client.get("/ping")
    assert "strict-transport-security" not in resp.headers


def test_hsts_in_production() -> None:
    client = TestClient(_make_app("production"))
    resp = client.get("/ping")
    assert resp.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
