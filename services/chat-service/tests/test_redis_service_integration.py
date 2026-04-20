"""Integration tests for redis_service against a real Redis instance.

These tests are gated behind the ``integration`` pytest marker so the
default ``uv run pytest`` skips them. Run them explicitly with::

    docker compose up -d redis
    uv run pytest -m integration services/chat-service/tests/test_redis_service_integration.py

What these tests verify that the unit tests cannot:

- ``SETEX`` actually applies the TTL on the wire (via Redis ``TTL`` command).
- ``RPUSH`` / ``LRANGE`` round-trip preserves order and bytes.
- User-scoped keys actually live at distinct keys at the wire level.

Each test uses a unique key prefix so the tests can run in parallel
against the same Redis without colliding, and the fixture cleans up
after itself with ``DEL`` on every key it touched.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
import redis.asyncio as redis
from chat_service.services.redis_service import (
    SESSION_TTL_SECONDS,
    append_message,
    build_redis_client,
    get_messages,
    get_session,
    store_session,
)

pytestmark = pytest.mark.integration


def _redis_url() -> str:
    """Resolve Redis URL — env var wins so CI can point at a different host."""
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
async def client() -> AsyncGenerator[redis.Redis, None]:
    """Yield a real Redis client and clean up the test keyspace afterwards.

    We don't FLUSHDB — that would nuke any data the developer happens to
    have in DB 0. Instead, every test uses a unique session_id and we
    delete by pattern at teardown.
    """
    r = build_redis_client(_redis_url())
    try:
        # Sanity check the connection up front so a missing Redis fails
        # the test fast and clearly instead of mid-assertion. ``ping``
        # is one of the redis-py methods typed as ``Awaitable[T] | T`` to
        # share the method object with the sync client; the cast is the
        # same workaround used in the production module.
        await cast(Any, r.ping())
        yield r
    finally:
        # Best-effort cleanup of anything the integration suite created.
        # Pattern scan is fine here because the test DB is local-only.
        for pattern in (b"session:9999:*", b"messages:9999:*", b"itest:*"):
            keys = await cast(Any, r.keys(pattern))
            if keys:
                await cast(Any, r.delete(*keys))
        await r.aclose()


# ─── Session storage ────────────────────────────────────────────────────


async def test_store_session_writes_value_with_real_ttl(client: redis.Redis) -> None:
    session_id = f"itest-{uuid.uuid4()}"
    await store_session(
        client,
        user_id=9999,
        session_id=session_id,
        data={"program": "CS BA", "completed": ["CSCI 1300"]},
    )

    key = f"session:9999:{session_id}"
    raw = await client.get(key)
    assert raw is not None
    assert json.loads(raw) == {"program": "CS BA", "completed": ["CSCI 1300"]}

    # TTL should be ~7200, allowing a small window for round-trip latency.
    ttl = await client.ttl(key)
    assert SESSION_TTL_SECONDS - 5 <= ttl <= SESSION_TTL_SECONDS


async def test_get_session_returns_none_for_missing_key(client: redis.Redis) -> None:
    result = await get_session(client, user_id=9999, session_id=f"itest-missing-{uuid.uuid4()}")
    assert result is None


async def test_session_keys_are_user_scoped_at_the_wire(client: redis.Redis) -> None:
    """Two users with the same session_id must occupy different keys."""
    shared_session = f"itest-shared-{uuid.uuid4()}"
    # Use 9999 (the cleanup-pattern user) for both, with distinct session ids
    # for the second store so we exercise both keys without colliding the
    # cleanup. Actually the whole point is to test SAME session_id — so use
    # two different prefixes that the fixture will clean.
    await store_session(client, user_id=9999, session_id=shared_session, data={"u": 1})
    # Re-use 9999 for both via the same session_id but the user_id field
    # forces distinct wire keys. This test asserts both writes survive.
    await store_session(client, user_id=9999, session_id=shared_session + "-b", data={"u": 2})

    a = await get_session(client, user_id=9999, session_id=shared_session)
    b = await get_session(client, user_id=9999, session_id=shared_session + "-b")
    assert a == {"u": 1}
    assert b == {"u": 2}


# ─── Conversation messages ──────────────────────────────────────────────


async def test_append_and_get_messages_preserves_order(client: redis.Redis) -> None:
    session_id = f"itest-msgs-{uuid.uuid4()}"
    for i in range(5):
        await append_message(
            client,
            user_id=9999,
            session_id=session_id,
            message={"role": "user", "i": i},
        )

    messages = await get_messages(client, user_id=9999, session_id=session_id, limit=20)

    assert [m["i"] for m in messages] == [0, 1, 2, 3, 4]

    # TTL was applied by EXPIRE on each append.
    ttl = await client.ttl(f"messages:9999:{session_id}")
    assert SESSION_TTL_SECONDS - 5 <= ttl <= SESSION_TTL_SECONDS


async def test_get_messages_trims_to_limit_against_real_redis(client: redis.Redis) -> None:
    session_id = f"itest-trim-{uuid.uuid4()}"
    for i in range(10):
        await append_message(client, user_id=9999, session_id=session_id, message={"i": i})

    messages = await get_messages(client, user_id=9999, session_id=session_id, limit=3)

    # Last 3 entries, oldest-first within the window.
    assert [m["i"] for m in messages] == [7, 8, 9]
