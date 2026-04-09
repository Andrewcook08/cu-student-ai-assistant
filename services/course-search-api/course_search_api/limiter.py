"""Shared slowapi Limiter instance for course-search-api.

Imported by main.py (to wire into app.state and register the 429 handler)
and by route modules (to apply @limiter.limit() decorators).

Storage strategy
----------------
Default: in-process MemoryStorage — zero external dependencies, suitable for
local dev and tests.

Production: switch to Redis-backed storage by passing storage_uri to the
Limiter constructor:

    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=settings.redis_url,
    )

This requires REDIS_URL to be set in the environment (already available via
shared.config.settings.redis_url from CHAT-004 / CUAI-36).
"""

from fastapi import Request
from jose import JWTError
from shared.auth import decode_access_token
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def user_key_func(request: Request) -> str:
    """Rate-limit key for authenticated routes: JWT user_id, or IP fallback.

    Parses the Bearer token directly so the key function runs independently of
    FastAPI's dependency injection (slowapi checks limits before dependencies
    are resolved). Falls back to remote IP if the token is missing or invalid —
    in that case get_current_user will still reject the request with 401.
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            user_id = decode_access_token(auth[7:])
            return f"user:{user_id}"
        except JWTError:
            pass
    return get_remote_address(request)
