"""Redis async transport layer for the chat service.

Backs two slices of the chat pipeline:

- **Session storage** — per-(user, session) JSON blobs with a 2-hour TTL
  (``store_session`` / ``get_session``).
- **Conversation message cache** — append-only message lists per session,
  TTL refreshed on every append (``append_message`` / ``get_messages``).

The ``redis.asyncio.Redis`` connection is owned by ``main.py`` lifespan
(constructed once via ``build_redis_client``) and injected per call,
mirroring the dependency-injection pattern used by ``llm_service`` and
``neo4j_service``. There is intentionally **no** module-level pool — the
same client/pool is reused across requests so we don't churn TCP
connections.

All raised errors share a common ``RedisError`` base so callers can
handle any Redis failure with a single ``except``:

- ``RedisError``         — base class; catch this for any Redis failure
- ``RedisTimeoutError``  — operation timeout
- ``RedisServiceError``  — connection errors, malformed payloads, and
  other unexpected protocol failures

The original exception is chained via ``raise ... from exc`` so logs keep
the underlying detail.

Session and conversation keys are scoped by ``user_id`` first so that
guessing another user's ``session_id`` cannot leak data — see
``_session_key`` / ``messages_key``.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import Any, cast

import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError as RedisLibraryError
from redis.exceptions import TimeoutError as RedisLibraryTimeoutError


class RedisError(RuntimeError):
    """Base class for redis_service failures — catch this to handle any Redis error."""


class RedisTimeoutError(RedisError):
    """Raised when a Redis operation (or the inference wait) exceeds its timeout budget."""


class RedisServiceError(RedisError):
    """Raised when Redis is unreachable, returns an error, or returns a malformed payload."""


# ─── TTL constants ──────────────────────────────────────────────────────

# 2-hour session TTL — sessions are cheap to recreate from Postgres if a
# user comes back after this window, but in-flight conversations should
# survive normal idle periods (lunch break, browser tab in background).
SESSION_TTL_SECONDS = 7200

_TIMEOUT_MESSAGE = "The AI is taking longer than expected. Please try again in a moment."
_SERVICE_MESSAGE = "Redis is temporarily unavailable. Please try again."
_MALFORMED_MESSAGE = "The AI returned an unexpected response. Please try again."


# ─── Key helpers ────────────────────────────────────────────────────────


def _session_key(user_id: int, session_id: str) -> str:
    """Build the per-user session key.

    User ID is the first segment so that two users with the same
    (guessable) session_id can never collide.
    """
    return f"session:{user_id}:{session_id}"


def messages_key(user_id: int, session_id: str) -> str:
    """Build the per-user conversation message list key (same scoping as sessions)."""
    return f"messages:{user_id}:{session_id}"


# ─── Client factory ─────────────────────────────────────────────────────


def build_redis_client(url: str, password: str | None = None) -> redis.Redis:
    """Construct the long-lived async Redis client used by the chat service.

    Called once from ``main.py`` lifespan and stored on ``app.state.redis``.
    ``decode_responses=False`` is intentional: pub/sub messages and list
    entries come back as ``bytes`` so we can decode them at the JSON
    boundary in one place rather than mixing str/bytes assumptions.

    *password* is wired through only when set so that local dev (which
    runs an unauthenticated Redis) doesn't need to pass an empty
    placeholder. Prod overrides supply ``REDIS_PASSWORD`` via env (see
    SEC-008 / CUAI-82).
    """
    if password:
        return redis.Redis.from_url(url, password=password, decode_responses=False)
    return redis.Redis.from_url(url, decode_responses=False)


# ─── Session storage ────────────────────────────────────────────────────


async def store_session(
    client: redis.Redis,
    *,
    user_id: int,
    session_id: str,
    data: dict[str, Any],
) -> None:
    """Store *data* under the per-user session key with a 2-hour TTL.

    Uses ``SETEX`` so the write and the expiry are atomic — a separate
    SET + EXPIRE could leave a key with no TTL if the second command
    failed.
    """
    try:
        await client.setex(
            _session_key(user_id, session_id),
            SESSION_TTL_SECONDS,
            json.dumps(data),
        )
    except RedisLibraryTimeoutError as exc:
        # Library TimeoutError must be caught before RedisError because
        # it inherits from RedisError in redis-py.
        raise RedisTimeoutError(_TIMEOUT_MESSAGE) from exc
    except (RedisConnectionError, RedisLibraryError) as exc:
        raise RedisServiceError(_SERVICE_MESSAGE) from exc


async def get_session(
    client: redis.Redis,
    *,
    user_id: int,
    session_id: str,
) -> dict[str, Any] | None:
    """Return the stored session dict, or ``None`` if it has expired or never existed."""
    try:
        raw = await client.get(_session_key(user_id, session_id))
    except RedisLibraryTimeoutError as exc:
        raise RedisTimeoutError(_TIMEOUT_MESSAGE) from exc
    except (RedisConnectionError, RedisLibraryError) as exc:
        raise RedisServiceError(_SERVICE_MESSAGE) from exc

    if raw is None:
        return None

    try:
        decoded = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        parsed: dict[str, Any] = json.loads(decoded)
        return parsed
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RedisServiceError(_MALFORMED_MESSAGE) from exc


# ─── Conversation message cache ─────────────────────────────────────────


async def append_message(
    client: redis.Redis,
    *,
    user_id: int,
    session_id: str,
    message: dict[str, Any],
) -> None:
    """Append *message* to the conversation list and refresh its 2-hour TTL.

    RPUSH + EXPIRE rather than a Lua script: the two-step race (a TTL
    that briefly lapses between commands) is harmless here because the
    immediately-following EXPIRE re-arms it, and the cost of a Lua
    eval round-trip isn't worth the marginal correctness gain.
    """
    key = messages_key(user_id, session_id)
    try:
        # redis-py types these as ``Awaitable[T] | T`` because the same
        # method object is reused by the sync client. At runtime the
        # async client always returns a coroutine, so the cast is safe.
        await cast(Awaitable[int], client.rpush(key, json.dumps(message)))
        await cast(Awaitable[bool], client.expire(key, SESSION_TTL_SECONDS))
    except RedisLibraryTimeoutError as exc:
        raise RedisTimeoutError(_TIMEOUT_MESSAGE) from exc
    except (RedisConnectionError, RedisLibraryError) as exc:
        raise RedisServiceError(_SERVICE_MESSAGE) from exc


async def append_messages(
    client: redis.Redis,
    *,
    user_id: int,
    session_id: str,
    messages: list[dict[str, Any]],
) -> None:
    """Atomically append multiple *messages* via a Redis pipeline.

    All RPUSHes and the final EXPIRE run in a single pipeline round-trip,
    so either all messages are persisted or none are — no partial history.
    """
    if not messages:
        return
    key = messages_key(user_id, session_id)
    try:
        async with client.pipeline(transaction=True) as pipe:
            for msg in messages:
                pipe.rpush(key, json.dumps(msg))
            pipe.expire(key, SESSION_TTL_SECONDS)
            await pipe.execute()
    except RedisLibraryTimeoutError as exc:
        raise RedisTimeoutError(_TIMEOUT_MESSAGE) from exc
    except (RedisConnectionError, RedisLibraryError) as exc:
        raise RedisServiceError(_SERVICE_MESSAGE) from exc


async def get_messages(
    client: redis.Redis,
    *,
    user_id: int,
    session_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return up to *limit* most recent messages, oldest-first.

    LRANGE with a negative start grabs the tail of the list (the most
    recent N entries) while preserving insertion order, so callers get a
    chronologically ordered window without an extra reverse step.
    """
    if limit <= 0:
        return []

    try:
        raw_entries = await cast(
            Awaitable[list[bytes]],
            client.lrange(messages_key(user_id, session_id), -limit, -1),
        )
    except RedisLibraryTimeoutError as exc:
        raise RedisTimeoutError(_TIMEOUT_MESSAGE) from exc
    except (RedisConnectionError, RedisLibraryError) as exc:
        raise RedisServiceError(_SERVICE_MESSAGE) from exc

    messages: list[dict[str, Any]] = []
    try:
        for entry in raw_entries:
            decoded = entry.decode("utf-8") if isinstance(entry, bytes) else entry
            messages.append(json.loads(decoded))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RedisServiceError(_MALFORMED_MESSAGE) from exc

    return messages
