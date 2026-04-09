"""Shared rate-limit handler factory for slowapi (SEC-007)."""

from __future__ import annotations

import time

from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded


def make_rate_limit_handler(limiter: Limiter) -> Callable[..., object]:
    """Return a 429 exception handler wired to *limiter*.

    Usage::

        from shared.rate_limit import make_rate_limit_handler
        app.add_exception_handler(RateLimitExceeded, make_rate_limit_handler(limiter))

    The handler always returns a clean 429 with a Retry-After header.  The
    header value is computed from the window stats exposed by slowapi; if the
    internal structure changes the handler falls back to a safe 60-second
    value rather than crashing.
    """

    async def handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        response = JSONResponse(content={"detail": "Too many requests"}, status_code=429)
        try:
            current_limit = request.state.view_rate_limit
            window_stats = limiter.limiter.get_window_stats(current_limit[0], *current_limit[1])
            retry_after = max(1, int(window_stats[0] - time.time()))
            response.headers["Retry-After"] = str(retry_after)
        except Exception:
            response.headers["Retry-After"] = "60"  # safe fallback if slowapi internals change
        return response

    return handler
