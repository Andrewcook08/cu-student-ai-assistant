"""Two-tier conversation memory for the chat service (MEM-001 / CUAI-57).

Tier 1 — Redis message buffer (this module):
  Up to ``MAX_RECENT_MESSAGES`` messages stored per session.  Loaded at the
  start of every turn so the LLM has full conversational context for recent
  exchanges.  Persisted atomically after each turn via a single pipeline.

Tier 2 — Running summary (MEM-002, planned):
  When the buffer exceeds ``MAX_RECENT_MESSAGES``, the caller should generate
  an LLM summary and call :func:`save_summary` to compress history.
  :func:`save_messages` returns ``True`` as the trigger signal.

Key layout (mirrors ``redis_service`` scoping — ``user_id`` first so that
guessing a ``session_id`` cannot leak another user's data):

  ``messages:{user_id}:{session_id}``  — RPUSH list of JSON message dicts
  ``summary:{user_id}:{session_id}``   — string: LLM-generated running summary

Both keys share ``SESSION_TTL_SECONDS`` (2 hours), refreshed on every write.

Error handling mirrors ``redis_service``:
- :func:`get_conversation_state` loads messages via ``redis_service``
  (raises ``RedisError`` on failure) and fetches the summary with a
  best-effort GET that logs a warning and returns ``None`` on any error.
- :func:`save_messages` propagates ``RedisError`` from ``append_messages``
  so the caller can apply graceful-degradation logic; the length check
  is non-fatal (returns ``False`` on unexpected failure).
- :func:`save_summary` propagates ``RedisError`` on pipeline failure.
"""

from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError as RedisLibraryError
from redis.exceptions import TimeoutError as RedisLibraryTimeoutError

from chat_service.services import redis_service
from chat_service.services.redis_service import SESSION_TTL_SECONDS, RedisError, RedisServiceError

logger = logging.getLogger(__name__)

#: Maximum number of messages kept in Redis before :func:`save_messages`
#: returns ``True`` to signal that summary compression is needed (MEM-002).
MAX_RECENT_MESSAGES: int = 20

#: Number of messages to retain after summary compression.
_POST_SUMMARY_KEEP: int = 10


# ─── Key helpers ─────────────────────────────────────────────────────────
# Duplicating the pattern from redis_service rather than exporting a private
# helper.  Both modules must agree on the key format; a mismatch would be
# caught immediately by the integration tests.


def _messages_key(user_id: int, session_id: str) -> str:
    return f"messages:{user_id}:{session_id}"


def _summary_key(user_id: int, session_id: str) -> str:
    return f"summary:{user_id}:{session_id}"


# ─── Public API ──────────────────────────────────────────────────────────


async def get_conversation_state(
    client: redis.Redis,
    *,
    user_id: int,
    session_id: str,
) -> dict[str, Any]:
    """Load the full conversation state for *session_id*.

    Returns a dict with two keys:

    * ``"messages"`` — list of message dicts (oldest-first, up to
      ``MAX_RECENT_MESSAGES``), fetched via ``redis_service.get_messages``.
      Raises ``RedisError`` on failure; callers should apply graceful
      degradation (empty history) and log a warning.
    * ``"summary"`` — the running LLM-generated summary string, or
      ``None`` if no summary has been saved yet or if the fetch fails.
      Summary fetch failures are logged at WARNING and silently swallowed
      so a missing summary never blocks the message loop.
    """
    messages = await redis_service.get_messages(
        client, user_id=user_id, session_id=session_id, limit=MAX_RECENT_MESSAGES
    )

    summary: str | None = None
    try:
        raw = await client.get(_summary_key(user_id, session_id))
        if raw is not None:
            summary = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    except (RedisLibraryTimeoutError, RedisConnectionError, RedisLibraryError) as exc:
        logger.warning(
            "memory: failed to load summary for user_id=%s session=%s: %s",
            user_id,
            session_id,
            exc,
        )

    return {"messages": messages, "summary": summary}


async def save_messages(
    client: redis.Redis,
    *,
    user_id: int,
    session_id: str,
    messages: list[dict[str, Any]],
) -> bool:
    """Append *messages* to the session history and signal if compression is needed.

    Delegates to ``redis_service.append_messages`` for the atomic
    RPUSH + EXPIRE pipeline, then checks the list length.

    Returns:
        ``True`` if the buffer now exceeds ``MAX_RECENT_MESSAGES`` and
        the caller should trigger summary compression (MEM-002).
        ``False`` otherwise, or if the length check itself fails (non-fatal).

    Raises:
        ``RedisError`` — if the append pipeline fails.  The caller should
        log a warning and continue; history loss on a single turn is
        acceptable (graceful degradation).
    """
    await redis_service.append_messages(
        client, user_id=user_id, session_id=session_id, messages=messages
    )

    try:
        count = await client.llen(_messages_key(user_id, session_id))
        return int(count) > MAX_RECENT_MESSAGES
    except Exception as exc:
        # Length check failure is non-fatal — we already persisted
        # successfully; the only downside is a missed compression trigger.
        logger.warning(
            "memory: llen check failed for user_id=%s session=%s: %s",
            user_id,
            session_id,
            exc,
        )
        return False


async def save_summary(
    client: redis.Redis,
    *,
    user_id: int,
    session_id: str,
    summary: str,
) -> None:
    """Persist *summary* and trim the message buffer to ``_POST_SUMMARY_KEEP``.

    Both operations run in a single pipeline so the summary and the trimmed
    message list are always consistent — either both are updated or neither is.

    The summary key shares ``SESSION_TTL_SECONDS`` with the message list key
    so both expire together when a session becomes inactive.

    Raises:
        ``RedisError`` — if the pipeline fails.
    """
    try:
        async with client.pipeline(transaction=True) as pipe:
            pipe.set(_summary_key(user_id, session_id), summary, ex=SESSION_TTL_SECONDS)
            pipe.ltrim(_messages_key(user_id, session_id), -_POST_SUMMARY_KEEP, -1)
            await pipe.execute()
    except RedisLibraryTimeoutError as exc:
        from chat_service.services.redis_service import RedisTimeoutError

        raise RedisTimeoutError("Redis summary save timed out.") from exc
    except (RedisConnectionError, RedisLibraryError) as exc:
        raise RedisServiceError("Redis summary save failed.") from exc
