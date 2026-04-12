"""Unit tests for chat_service.core.memory (MEM-001 / CUAI-57).

Redis client is mocked — tests assert:
- correct key names (user_id-scoped: messages:{uid}:{sid}, summary:{uid}:{sid})
- get_conversation_state returns messages + summary (or None on missing/error)
- save_messages delegates to redis_service and returns correct threshold signal
- save_summary writes summary + trims message buffer atomically
- error propagation / graceful degradation matches the documented contract
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from chat_service.core.memory import (
    MAX_RECENT_MESSAGES,
    _POST_SUMMARY_KEEP,
    _messages_key,
    _summary_key,
    get_conversation_state,
    save_messages,
    save_summary,
)
from chat_service.services.redis_service import RedisServiceError, RedisTimeoutError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisLibraryTimeoutError

# ─── Fixtures ────────────────────────────────────────────────────────────

USER_ID = 42
SESSION_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _make_client() -> MagicMock:
    """Mock Redis client with pipeline support."""
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.llen = AsyncMock(return_value=0)

    # Pipeline context manager
    pipe = MagicMock()
    pipe.set = MagicMock()
    pipe.ltrim = MagicMock()
    pipe.execute = AsyncMock(return_value=[True, True])
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    client.pipeline = MagicMock(return_value=pipe)

    return client


def _msg(role: str, content: str) -> dict[str, Any]:
    return {"role": role, "content": content}


# ─── Key helpers ─────────────────────────────────────────────────────────


def test_messages_key_scoped_by_user_id() -> None:
    assert _messages_key(1, "sess") == "messages:1:sess"
    # Different users must produce different keys for the same session_id
    assert _messages_key(1, "sess") != _messages_key(2, "sess")


def test_summary_key_scoped_by_user_id() -> None:
    assert _summary_key(1, "sess") == "summary:1:sess"
    assert _summary_key(1, "sess") != _summary_key(2, "sess")


# ─── get_conversation_state ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_conversation_state_returns_messages_and_summary() -> None:
    client = _make_client()
    msgs = [_msg("user", "hi"), _msg("assistant", "hello")]
    summary_bytes = b"Student is CS major, completed CSCI 1300"
    client.get = AsyncMock(return_value=summary_bytes)

    with patch(
        "chat_service.core.memory.redis_service.get_messages",
        new=AsyncMock(return_value=msgs),
    ):
        result = await get_conversation_state(client, user_id=USER_ID, session_id=SESSION_ID)

    assert result["messages"] == msgs
    assert result["summary"] == "Student is CS major, completed CSCI 1300"


@pytest.mark.asyncio
async def test_get_conversation_state_summary_none_when_key_missing() -> None:
    client = _make_client()
    client.get = AsyncMock(return_value=None)

    with patch(
        "chat_service.core.memory.redis_service.get_messages",
        new=AsyncMock(return_value=[]),
    ):
        result = await get_conversation_state(client, user_id=USER_ID, session_id=SESSION_ID)

    assert result["summary"] is None
    assert result["messages"] == []


@pytest.mark.asyncio
async def test_get_conversation_state_summary_none_on_redis_error() -> None:
    """Summary fetch failure is silently swallowed; messages are still returned."""
    client = _make_client()
    msgs = [_msg("user", "hi")]
    client.get = AsyncMock(side_effect=RedisConnectionError("down"))

    with patch(
        "chat_service.core.memory.redis_service.get_messages",
        new=AsyncMock(return_value=msgs),
    ):
        result = await get_conversation_state(client, user_id=USER_ID, session_id=SESSION_ID)

    assert result["messages"] == msgs
    assert result["summary"] is None  # graceful degradation


@pytest.mark.asyncio
async def test_get_conversation_state_uses_correct_summary_key() -> None:
    """Client.get is called with the user-scoped summary key."""
    client = _make_client()
    client.get = AsyncMock(return_value=None)

    with patch(
        "chat_service.core.memory.redis_service.get_messages",
        new=AsyncMock(return_value=[]),
    ):
        await get_conversation_state(client, user_id=USER_ID, session_id=SESSION_ID)

    client.get.assert_called_once_with(_summary_key(USER_ID, SESSION_ID))


# ─── save_messages ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_messages_below_threshold_returns_false() -> None:
    client = _make_client()
    client.llen = AsyncMock(return_value=MAX_RECENT_MESSAGES)  # exactly at limit
    msgs = [_msg("user", "x"), _msg("assistant", "y")]

    with patch(
        "chat_service.core.memory.redis_service.append_messages",
        new=AsyncMock(return_value=None),
    ) as mock_append:
        result = await save_messages(client, user_id=USER_ID, session_id=SESSION_ID, messages=msgs)

    mock_append.assert_awaited_once()
    assert result is False


@pytest.mark.asyncio
async def test_save_messages_above_threshold_returns_true() -> None:
    client = _make_client()
    client.llen = AsyncMock(return_value=MAX_RECENT_MESSAGES + 1)
    msgs = [_msg("user", "x"), _msg("assistant", "y")]

    with patch(
        "chat_service.core.memory.redis_service.append_messages",
        new=AsyncMock(return_value=None),
    ):
        result = await save_messages(client, user_id=USER_ID, session_id=SESSION_ID, messages=msgs)

    assert result is True


@pytest.mark.asyncio
async def test_save_messages_llen_failure_returns_false() -> None:
    """llen failure is non-fatal; save_messages returns False."""
    client = _make_client()
    client.llen = AsyncMock(side_effect=Exception("network blip"))

    with patch(
        "chat_service.core.memory.redis_service.append_messages",
        new=AsyncMock(return_value=None),
    ):
        result = await save_messages(
            client, user_id=USER_ID, session_id=SESSION_ID, messages=[_msg("user", "hi")]
        )

    assert result is False


@pytest.mark.asyncio
async def test_save_messages_propagates_redis_error_from_append() -> None:
    """append_messages failure propagates so caller can apply graceful degradation."""
    client = _make_client()

    with patch(
        "chat_service.core.memory.redis_service.append_messages",
        new=AsyncMock(side_effect=RedisServiceError("Redis down")),
    ):
        with pytest.raises(RedisServiceError):
            await save_messages(
                client, user_id=USER_ID, session_id=SESSION_ID, messages=[_msg("user", "hi")]
            )


@pytest.mark.asyncio
async def test_save_messages_checks_correct_key() -> None:
    """llen is called on the user-scoped messages key."""
    client = _make_client()
    client.llen = AsyncMock(return_value=5)

    with patch(
        "chat_service.core.memory.redis_service.append_messages",
        new=AsyncMock(return_value=None),
    ):
        await save_messages(
            client, user_id=USER_ID, session_id=SESSION_ID, messages=[_msg("user", "hi")]
        )

    client.llen.assert_awaited_once_with(_messages_key(USER_ID, SESSION_ID))


# ─── save_summary ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_summary_runs_set_and_ltrim() -> None:
    client = _make_client()
    pipe = client.pipeline.return_value

    await save_summary(client, user_id=USER_ID, session_id=SESSION_ID, summary="CS major")

    pipe.set.assert_called_once()
    set_args = pipe.set.call_args
    assert set_args.args[0] == _summary_key(USER_ID, SESSION_ID)
    assert set_args.args[1] == "CS major"

    pipe.ltrim.assert_called_once()
    ltrim_args = pipe.ltrim.call_args
    assert ltrim_args.args[0] == _messages_key(USER_ID, SESSION_ID)
    # ltrim keeps last _POST_SUMMARY_KEEP entries
    assert ltrim_args.args[1] == -_POST_SUMMARY_KEEP
    assert ltrim_args.args[2] == -1


@pytest.mark.asyncio
async def test_save_summary_uses_transaction_pipeline() -> None:
    client = _make_client()
    await save_summary(client, user_id=USER_ID, session_id=SESSION_ID, summary="summary text")
    client.pipeline.assert_called_once_with(transaction=True)


@pytest.mark.asyncio
async def test_save_summary_timeout_raises_redis_timeout_error() -> None:
    client = _make_client()
    pipe = client.pipeline.return_value
    pipe.execute = AsyncMock(side_effect=RedisLibraryTimeoutError())

    with pytest.raises(RedisTimeoutError):
        await save_summary(client, user_id=USER_ID, session_id=SESSION_ID, summary="x")


@pytest.mark.asyncio
async def test_save_summary_connection_error_raises_redis_service_error() -> None:
    client = _make_client()
    pipe = client.pipeline.return_value
    pipe.execute = AsyncMock(side_effect=RedisConnectionError("down"))

    with pytest.raises(RedisServiceError):
        await save_summary(client, user_id=USER_ID, session_id=SESSION_ID, summary="x")
