"""Unit tests for chat_service.services.redis_service (CUAI-36).

The redis.asyncio.Redis client is mocked — these tests assert the wire
shape (keys, TTLs, payloads) and the user_id scoping without spinning up
a real Redis. Mirrors the AsyncMock/MagicMock pattern from
test_llm_service and test_neo4j_service; no new test deps (no
fakeredis, no pytest-redis).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from chat_service.services.redis_service import (
    SESSION_TTL_SECONDS,
    RedisServiceError,
    RedisTimeoutError,
    append_message,
    build_redis_client,
    get_messages,
    get_session,
    store_session,
)
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisLibraryTimeoutError

# ─── Helpers ────────────────────────────────────────────────────────────


def _make_client() -> MagicMock:
    """Build a mock async Redis client with all the methods this module touches."""
    client = MagicMock()
    client.setex = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.rpush = AsyncMock(return_value=1)
    client.expire = AsyncMock(return_value=True)
    client.lrange = AsyncMock(return_value=[])
    client.lpush = AsyncMock(return_value=1)
    client.aclose = AsyncMock(return_value=None)
    return client


# ─── Session storage ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_session_uses_setex_with_2_hour_ttl_and_user_scoped_key() -> None:
    client = _make_client()

    await store_session(client, user_id=42, session_id="abc", data={"foo": "bar"})

    client.setex.assert_awaited_once()
    key, ttl, value = client.setex.await_args.args
    assert key == "session:42:abc"
    assert ttl == SESSION_TTL_SECONDS == 7200
    assert json.loads(value) == {"foo": "bar"}


@pytest.mark.asyncio
async def test_store_session_scopes_keys_by_user_id() -> None:
    client = _make_client()

    await store_session(client, user_id=1, session_id="abc", data={"u": 1})
    await store_session(client, user_id=2, session_id="abc", data={"u": 2})

    keys = [call.args[0] for call in client.setex.await_args_list]
    assert keys == ["session:1:abc", "session:2:abc"]
    assert keys[0] != keys[1]


@pytest.mark.asyncio
async def test_get_session_round_trips_json_payload() -> None:
    client = _make_client()
    client.get = AsyncMock(return_value=json.dumps({"foo": "bar"}).encode("utf-8"))

    result = await get_session(client, user_id=42, session_id="abc")

    client.get.assert_awaited_once_with("session:42:abc")
    assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_get_session_returns_none_on_miss() -> None:
    client = _make_client()
    client.get = AsyncMock(return_value=None)

    assert await get_session(client, user_id=42, session_id="abc") is None


@pytest.mark.asyncio
async def test_get_session_malformed_json_raises_service_error() -> None:
    client = _make_client()
    client.get = AsyncMock(return_value=b"not-json{")

    with pytest.raises(RedisServiceError) as excinfo:
        await get_session(client, user_id=42, session_id="abc")

    assert "unexpected response" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None


@pytest.mark.asyncio
async def test_store_session_connection_error_raises_service_error() -> None:
    client = _make_client()
    original = RedisConnectionError("nope")
    client.setex = AsyncMock(side_effect=original)

    with pytest.raises(RedisServiceError) as excinfo:
        await store_session(client, user_id=1, session_id="abc", data={})

    assert "temporarily unavailable" in str(excinfo.value)
    assert excinfo.value.__cause__ is original


@pytest.mark.asyncio
async def test_store_session_library_timeout_raises_redis_timeout_error() -> None:
    client = _make_client()
    original = RedisLibraryTimeoutError("slow")
    client.setex = AsyncMock(side_effect=original)

    with pytest.raises(RedisTimeoutError) as excinfo:
        await store_session(client, user_id=1, session_id="abc", data={})

    assert excinfo.value.__cause__ is original


@pytest.mark.asyncio
async def test_get_session_library_timeout_raises_redis_timeout_error() -> None:
    client = _make_client()
    original = RedisLibraryTimeoutError("slow")
    client.get = AsyncMock(side_effect=original)

    with pytest.raises(RedisTimeoutError) as excinfo:
        await get_session(client, user_id=1, session_id="abc")

    assert excinfo.value.__cause__ is original


@pytest.mark.asyncio
async def test_store_session_round_trips_nested_json() -> None:
    """Nested dicts/lists must survive the JSON encode/decode boundary intact."""
    client = _make_client()
    payload = {"nested": {"x": [1, 2, 3]}, "tools": [{"name": "search"}]}

    await store_session(client, user_id=1, session_id="abc", data=payload)

    written = client.setex.await_args.args[2]
    # Hand the same bytes back to get_session via a fresh mock and verify
    # the round-trip preserves structure (not just shape).
    client.get = AsyncMock(return_value=written.encode("utf-8"))
    result = await get_session(client, user_id=1, session_id="abc")

    assert result == payload


# ─── Conversation message cache ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_message_rpush_then_expire_with_2_hour_ttl() -> None:
    client = _make_client()

    await append_message(
        client,
        user_id=42,
        session_id="abc",
        message={"role": "user", "content": "hello"},
    )

    client.rpush.assert_awaited_once()
    key, value = client.rpush.await_args.args
    assert key == "messages:42:abc"
    assert json.loads(value) == {"role": "user", "content": "hello"}

    client.expire.assert_awaited_once_with("messages:42:abc", SESSION_TTL_SECONDS)


@pytest.mark.asyncio
async def test_get_messages_preserves_order_oldest_first() -> None:
    client = _make_client()
    client.lrange = AsyncMock(
        return_value=[
            json.dumps({"i": 1}).encode("utf-8"),
            json.dumps({"i": 2}).encode("utf-8"),
            json.dumps({"i": 3}).encode("utf-8"),
        ]
    )

    messages = await get_messages(client, user_id=42, session_id="abc", limit=20)

    client.lrange.assert_awaited_once_with("messages:42:abc", -20, -1)
    assert messages == [{"i": 1}, {"i": 2}, {"i": 3}]


@pytest.mark.asyncio
async def test_get_messages_trims_to_limit_via_lrange_window() -> None:
    client = _make_client()
    client.lrange = AsyncMock(return_value=[])

    await get_messages(client, user_id=42, session_id="abc", limit=5)

    # The trimming is enforced server-side via the LRANGE bounds; the
    # client only ever asks for the last `limit` entries.
    client.lrange.assert_awaited_once_with("messages:42:abc", -5, -1)


@pytest.mark.asyncio
async def test_get_messages_zero_limit_short_circuits() -> None:
    client = _make_client()

    result = await get_messages(client, user_id=42, session_id="abc", limit=0)

    assert result == []
    client.lrange.assert_not_called()


@pytest.mark.asyncio
async def test_get_messages_empty_list_returns_empty() -> None:
    client = _make_client()
    client.lrange = AsyncMock(return_value=[])

    result = await get_messages(client, user_id=42, session_id="abc")

    assert result == []


@pytest.mark.asyncio
async def test_append_message_library_timeout_raises_redis_timeout_error() -> None:
    client = _make_client()
    original = RedisLibraryTimeoutError("slow")
    client.rpush = AsyncMock(side_effect=original)

    with pytest.raises(RedisTimeoutError) as excinfo:
        await append_message(
            client, user_id=1, session_id="abc", message={"role": "user", "content": "x"}
        )

    assert excinfo.value.__cause__ is original


@pytest.mark.asyncio
async def test_get_messages_library_timeout_raises_redis_timeout_error() -> None:
    client = _make_client()
    original = RedisLibraryTimeoutError("slow")
    client.lrange = AsyncMock(side_effect=original)

    with pytest.raises(RedisTimeoutError) as excinfo:
        await get_messages(client, user_id=1, session_id="abc")

    assert excinfo.value.__cause__ is original


# ─── build_redis_client factory ─────────────────────────────────────────


def test_build_redis_client_passes_password_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_from_url(url: str, **kwargs: Any) -> str:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return "client"

    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(redis_asyncio.Redis, "from_url", staticmethod(fake_from_url))

    build_redis_client("redis://x:6379/0", password="secret")

    assert captured["url"] == "redis://x:6379/0"
    assert captured["kwargs"]["password"] == "secret"
    assert captured["kwargs"]["decode_responses"] is False


def test_build_redis_client_omits_password_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_from_url(url: str, **kwargs: Any) -> str:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return "client"

    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(redis_asyncio.Redis, "from_url", staticmethod(fake_from_url))

    build_redis_client("redis://x:6379/0", password=None)

    assert "password" not in captured["kwargs"]
    assert captured["kwargs"]["decode_responses"] is False
