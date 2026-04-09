"""Shared slowapi Limiter instance for chat-service.

Imported by main.py to wire into app.state and register the 429 handler.
Route modules import this when applying @limiter.limit() decorators.

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

from slowapi import Limiter
from slowapi.util import get_remote_address

# TODO(SEC-007): get_remote_address reads request.client.host (the immediate TCP peer).
# Behind nginx/CloudFront/any load balancer all requests appear as the proxy's IP, so all
# users share one rate-limit bucket.  Switch key_func to read X-Forwarded-For / X-Real-IP
# before this service is deployed behind a reverse proxy.
limiter = Limiter(key_func=get_remote_address)
