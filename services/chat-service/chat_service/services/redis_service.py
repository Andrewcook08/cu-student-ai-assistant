"""Redis async transport layer for the chat service.

Backs three slices of the chat pipeline:

- **Session storage** — per-(user, session) JSON blobs with a 2-hour TTL
  (``store_session`` / ``get_session``).
- **Conversation message cache** — append-only message lists per session,
  TTL refreshed on every append (``append_message`` / ``get_messages``).
- **Ollama inference queue** — LPUSH a request onto a shared queue and
  await its result on a per-request pub/sub channel
  (``enqueue_inference``), with a 30 s "still working" progress callback
  and a hard 120 s timeout. The request is **never** silently retried —
  the caller decides what to do on failure.

The ``redis.asyncio.Redis`` connection is owned by ``main.py`` lifespan
(constructed once via ``build_redis_client``) and injected per call,
mirroring the dependency-injection pattern used by ``ollama_service`` and
``neo4j_service``. There is intentionally **no** module-level pool — the
same client/pool is reused across requests so we don't churn TCP
connections.

All raised errors share a common ``RedisError`` base so callers can
handle any Redis failure with a single ``except``:

- ``RedisError``         — base class; catch this for any Redis failure
- ``RedisTimeoutError``  — operation timeout, including the 120 s
  inference budget
- ``RedisServiceError``  — connection errors, malformed payloads, and
  other unexpected protocol failures

The original exception is chained via ``raise ... from exc`` so logs keep
the underlying detail.

Session and conversation keys are scoped by ``user_id`` first so that
guessing another user's ``session_id`` cannot leak data — see
``_session_key`` / ``_messages_key``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import Awaitable, Callable
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


# ─── TTLs and channel/queue constants ───────────────────────────────────

# 2-hour session TTL — sessions are cheap to recreate from Postgres if a
# user comes back after this window, but in-flight conversations should
# survive normal idle periods (lunch break, browser tab in background).
SESSION_TTL_SECONDS = 7200

# Hard wall-clock budget for one Ollama inference request. Matches the
# httpx read timeout in main.py so a queued inference and a direct call
# fail in the same window.
INFERENCE_TIMEOUT_SECONDS = 120.0

# How often to fire the optional progress callback while we're still
# waiting on the worker. The frontend uses this to push a "still
# thinking…" event so the user knows the connection is alive.
INFERENCE_PROGRESS_INTERVAL_SECONDS = 30.0

# Global queue the Ollama worker LPOPs from. Per-request results come
# back on ``ollama:result:{request_id}`` so concurrent requests don't
# cross-contaminate.
INFERENCE_QUEUE_KEY = "ollama:inference_queue"
_RESULT_CHANNEL_PREFIX = "ollama:result:"

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


def _messages_key(user_id: int, session_id: str) -> str:
    """Build the per-user conversation message list key (same scoping as sessions)."""
    return f"messages:{user_id}:{session_id}"


def _result_channel(request_id: str) -> str:
    return f"{_RESULT_CHANNEL_PREFIX}{request_id}"


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
    key = _messages_key(user_id, session_id)
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
    key = _messages_key(user_id, session_id)
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
            client.lrange(_messages_key(user_id, session_id), -limit, -1),
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


# ─── Inference queue ────────────────────────────────────────────────────


async def enqueue_inference(
    client: redis.Redis,
    request: dict[str, Any],
    *,
    timeout: float = INFERENCE_TIMEOUT_SECONDS,
    progress_interval: float = INFERENCE_PROGRESS_INTERVAL_SECONDS,
    on_progress: Callable[[], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Push *request* onto the Ollama inference queue and await its result.

    Generates a ``request_id``, injects it into the payload so the worker
    knows which channel to publish the result on, then LPUSHes the JSON
    onto ``INFERENCE_QUEUE_KEY``. The result comes back via pub/sub on
    ``ollama:result:{request_id}``.

    While we wait, ``on_progress`` (if supplied) is invoked roughly every
    ``progress_interval`` seconds so the WebSocket layer can send a
    "still thinking…" frame. After ``timeout`` seconds with no result,
    raises ``RedisTimeoutError`` with a user-facing message — the
    request is **not** silently retried.

    The pub/sub subscription is always torn down in a ``finally`` block,
    even on timeout or unexpected exception, so a stuck request can't
    leak a subscriber.
    """
    request_id = str(uuid.uuid4())
    payload = {**request, "request_id": request_id}
    channel = _result_channel(request_id)

    # Subscribe BEFORE LPUSH. If the worker were extremely fast and
    # published its result before we subscribed, we'd block forever
    # waiting for a message that already happened. Pub/sub has no
    # backlog.
    pubsub = client.pubsub()
    try:
        try:
            await pubsub.subscribe(channel)
        except RedisLibraryTimeoutError as exc:
            raise RedisTimeoutError(_TIMEOUT_MESSAGE) from exc
        except (RedisConnectionError, RedisLibraryError) as exc:
            raise RedisServiceError(_SERVICE_MESSAGE) from exc

        try:
            await cast(
                Awaitable[int],
                client.lpush(INFERENCE_QUEUE_KEY, json.dumps(payload)),
            )
        except RedisLibraryTimeoutError as exc:
            raise RedisTimeoutError(_TIMEOUT_MESSAGE) from exc
        except (RedisConnectionError, RedisLibraryError) as exc:
            raise RedisServiceError(_SERVICE_MESSAGE) from exc

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        # Two interleaved budgets: a hard wall-clock deadline (the
        # 120 s SLA) and a soft per-tick budget (the 30 s progress
        # interval). We poll get_message with the smaller of the two
        # remaining budgets so the progress callback fires on time
        # AND we never overshoot the hard deadline.
        while True:
            now = loop.time()
            remaining_total = deadline - now
            if remaining_total <= 0:
                raise RedisTimeoutError(_TIMEOUT_MESSAGE)

            tick = min(progress_interval, remaining_total)
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=None),
                    timeout=tick,
                )
            except TimeoutError:
                # No result yet within this tick — fire the progress
                # callback (if any) and loop. Whether the next loop
                # iteration times out for real is decided by the
                # remaining_total check above.
                if on_progress is not None:
                    await on_progress()
                continue
            except RedisLibraryTimeoutError as exc:
                raise RedisTimeoutError(_TIMEOUT_MESSAGE) from exc
            except (RedisConnectionError, RedisLibraryError) as exc:
                raise RedisServiceError(_SERVICE_MESSAGE) from exc

            if message is None:
                # get_message can return None when the underlying read
                # times out internally — treat the same as a tick
                # expiry so the progress callback still fires.
                if on_progress is not None:
                    await on_progress()
                continue

            data = message.get("data")
            if data is None:
                continue

            try:
                decoded = data.decode("utf-8") if isinstance(data, bytes) else data
                parsed: dict[str, Any] = json.loads(decoded)
                return parsed
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RedisServiceError(_MALFORMED_MESSAGE) from exc
    finally:
        # Best-effort cleanup. We swallow errors here because the
        # caller already has whatever exception they're going to see —
        # masking it with a teardown failure would be worse than
        # leaking one subscription on shutdown.
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
        with contextlib.suppress(Exception):
            # redis-py 5.0.1 deprecated ``close`` in favor of ``aclose``,
            # but ``aclose`` is currently declared as an untyped method
            # (no return-type annotation), so strict mypy rejects the
            # call without an explicit ignore. Use ``aclose`` and pin
            # the ignore to that one diagnostic so a future redis-py
            # release that adds the annotation surfaces immediately.
            await pubsub.aclose()  # type: ignore[no-untyped-call]
