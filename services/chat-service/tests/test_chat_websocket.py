"""Tests for the /ws/chat/{session_id} WebSocket endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from shared.auth import create_access_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph_result(
    reply: str = "Hello!",
    structured_data: list | None = None,
    error: str | None = None,
) -> dict:
    """Return a canned LangGraph result dict."""
    return {
        "messages": [AIMessage(content=reply)],
        "structured_data": structured_data or [],
        "error": error,
    }


# ---------------------------------------------------------------------------
# Core happy-path: valid token + message → typing + chat_response
# ---------------------------------------------------------------------------


def test_websocket_valid_token_returns_chat_response(client: TestClient) -> None:
    """Graph reply is forwarded as a chat_response after the typing indicator."""
    from chat_service.main import app

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=_make_graph_result(reply="Hello!"))
    app.state.conversation_graph = mock_graph

    token = create_access_token(1)
    with (
        patch(
            "chat_service.routes.chat.redis_service.get_messages",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "chat_service.routes.chat.redis_service.append_messages",
            new_callable=AsyncMock,
        ),
        client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws,
    ):
        ws.send_json({"message": "hello"})
        assert ws.receive_json() == {"type": "typing"}
        assert ws.receive_json() == {
            "type": "chat_response",
            "reply": "Hello!",
            "session_id": "test-session",
        }


# ---------------------------------------------------------------------------
# structured_data is forwarded when the graph returns it
# ---------------------------------------------------------------------------


def test_websocket_returns_structured_data(client: TestClient) -> None:
    """structured_data from the graph result is included in the response."""
    from chat_service.main import app

    structured = [{"course": "CSCI 1300", "credits": 3}]
    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(
        return_value=_make_graph_result(reply="Here are courses", structured_data=structured)
    )
    app.state.conversation_graph = mock_graph

    token = create_access_token(1)
    with (
        patch(
            "chat_service.routes.chat.redis_service.get_messages",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "chat_service.routes.chat.redis_service.append_messages",
            new_callable=AsyncMock,
        ),
        client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws,
    ):
        ws.send_json({"message": "show me courses"})
        ws.receive_json()  # typing
        response = ws.receive_json()
        assert response["type"] == "chat_response"
        assert response["reply"] == "Here are courses"
        assert response["structured_data"] == structured


# ---------------------------------------------------------------------------
# Auth failures
# ---------------------------------------------------------------------------


def test_websocket_rejects_invalid_token(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/ws/chat/test-session?token=not-a-real-jwt") as ws,
    ):
        ws.receive_text()
    assert exc_info.value.code == 4001


def test_websocket_rejects_missing_token(client: TestClient) -> None:
    # FastAPI rejects the handshake before the WS upgrade when the required
    # `token` query param is missing. TestClient surfaces that as a
    # WebSocketDisconnect.
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/chat/test-session") as ws,
    ):
        ws.receive_text()


# ---------------------------------------------------------------------------
# Empty / whitespace messages are silently ignored
# ---------------------------------------------------------------------------


def test_websocket_empty_message_no_response(client: TestClient) -> None:
    """Empty and whitespace-only messages must not trigger a response."""
    from chat_service.main import app

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=_make_graph_result())
    app.state.conversation_graph = mock_graph

    token = create_access_token(1)
    with (
        patch(
            "chat_service.routes.chat.redis_service.get_messages",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "chat_service.routes.chat.redis_service.append_messages",
            new_callable=AsyncMock,
        ),
        client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws,
    ):
        # Send an empty message then a real one to confirm the loop is still
        # running and the empty one produced no frame.
        ws.send_json({"message": "   "})
        ws.send_json({"message": "hi"})

        # First frame must be the typing indicator for the real message, not a
        # response to the empty one.
        assert ws.receive_json() == {"type": "typing"}
        response = ws.receive_json()
        assert response["type"] == "chat_response"

    # Graph should have been invoked exactly once (for "hi", not "   ").
    mock_graph.ainvoke.assert_called_once()


# ---------------------------------------------------------------------------
# Graph failure → error response (no close)
# ---------------------------------------------------------------------------


def test_websocket_graph_failure_returns_error_response(client: TestClient) -> None:
    """If graph.ainvoke raises, the endpoint sends an error message and stays open."""
    from chat_service.main import app

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("graph exploded"))
    app.state.conversation_graph = mock_graph

    token = create_access_token(1)
    with (
        patch(
            "chat_service.routes.chat.redis_service.get_messages",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "chat_service.routes.chat.redis_service.append_messages",
            new_callable=AsyncMock,
        ),
        client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws,
    ):
        ws.send_json({"message": "trigger failure"})
        ws.receive_json()  # typing
        response = ws.receive_json()
        assert response["type"] == "chat_response"
        assert "went wrong" in response["reply"].lower()
        assert response["session_id"] == "test-session"


# ---------------------------------------------------------------------------
# Redis get_messages failure → graph still runs (graceful fallback)
# ---------------------------------------------------------------------------


def test_websocket_redis_failure_graph_still_runs(client: TestClient) -> None:
    """A RedisError on get_messages must not abort the turn — graph runs with empty history."""
    from chat_service.main import app
    from chat_service.services.redis_service import RedisError

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=_make_graph_result(reply="Fallback reply"))
    app.state.conversation_graph = mock_graph

    token = create_access_token(1)
    with (
        patch(
            "chat_service.routes.chat.redis_service.get_messages",
            new_callable=AsyncMock,
            side_effect=RedisError("redis down"),
        ),
        patch(
            "chat_service.routes.chat.redis_service.append_messages",
            new_callable=AsyncMock,
        ),
        client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws,
    ):
        ws.send_json({"message": "hello despite redis being down"})
        ws.receive_json()  # typing
        response = ws.receive_json()
        assert response["type"] == "chat_response"
        assert response["reply"] == "Fallback reply"

    # Graph must have been called even though Redis was unavailable.
    mock_graph.ainvoke.assert_called_once()


# ---------------------------------------------------------------------------
# Redis append_messages failure → response still sent (graceful)
# ---------------------------------------------------------------------------


def test_websocket_redis_append_failure_response_still_sent(client: TestClient) -> None:
    """A RedisError on append_messages must not abort the turn — response is sent anyway."""
    from chat_service.main import app
    from chat_service.services.redis_service import RedisError

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=_make_graph_result(reply="Persisted reply"))
    app.state.conversation_graph = mock_graph

    token = create_access_token(1)
    with (
        patch(
            "chat_service.routes.chat.redis_service.get_messages",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "chat_service.routes.chat.redis_service.append_messages",
            new_callable=AsyncMock,
            side_effect=RedisError("persist failed"),
        ),
        client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws,
    ):
        ws.send_json({"message": "hello"})
        ws.receive_json()  # typing
        response = ws.receive_json()
        assert response["type"] == "chat_response"
        assert response["reply"] == "Persisted reply"
        assert response["session_id"] == "test-session"

    # Graph must have been called despite the persist failure.
    mock_graph.ainvoke.assert_called_once()


# ---------------------------------------------------------------------------
# Malformed JSON → silently skipped, valid follow-up still works
# ---------------------------------------------------------------------------


def test_websocket_malformed_json_is_silently_skipped(client: TestClient) -> None:
    """Non-JSON text is treated as an empty message and silently ignored."""
    from chat_service.main import app

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=_make_graph_result(reply="Valid reply"))
    app.state.conversation_graph = mock_graph

    token = create_access_token(1)
    with (
        patch(
            "chat_service.routes.chat.redis_service.get_messages",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "chat_service.routes.chat.redis_service.append_messages",
            new_callable=AsyncMock,
        ),
        client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws,
    ):
        # Malformed JSON — should produce no response frame.
        ws.send_text("not json at all")
        # Valid follow-up — should produce typing + chat_response.
        ws.send_json({"message": "real message"})

        # First frame must be the typing indicator for the valid message only.
        assert ws.receive_json() == {"type": "typing"}
        response = ws.receive_json()
        assert response["type"] == "chat_response"
        assert response["reply"] == "Valid reply"

    # Graph invoked once (only for the valid message).
    mock_graph.ainvoke.assert_called_once()


# ---------------------------------------------------------------------------
# Graph timeout → timeout error response, connection stays open
# ---------------------------------------------------------------------------


def test_websocket_graph_timeout_returns_timeout_response(client: TestClient) -> None:
    """When graph.ainvoke times out, the endpoint sends a timeout message and stays open."""
    from chat_service.main import app

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=TimeoutError())
    app.state.conversation_graph = mock_graph

    token = create_access_token(1)
    with (
        patch(
            "chat_service.routes.chat.redis_service.get_messages",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "chat_service.routes.chat.redis_service.append_messages",
            new_callable=AsyncMock,
        ),
        client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws,
    ):
        ws.send_json({"message": "slow query"})
        ws.receive_json()  # typing
        response = ws.receive_json()
        assert response["type"] == "chat_response"
        assert "too long" in response["reply"].lower()
        assert response["session_id"] == "test-session"


# ---------------------------------------------------------------------------
# SEC-009 (CUAI-83) — WS flood / oversized message limits (not yet implemented)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Waiting on CUAI-83 (SEC-009) WS hardening")
def test_websocket_oversized_message_closes_with_1009(client: TestClient) -> None:
    """Oversized message (>4096 bytes) should close with code 1009."""
    token = create_access_token(1)
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws,
    ):
        ws.send_json({"message": "x" * 5000})
        ws.receive_json()
    assert exc_info.value.code == 1009


@pytest.mark.skip(reason="Waiting on CUAI-83 (SEC-009) WS hardening")
def test_websocket_flood_closes_with_1008(client: TestClient) -> None:
    """21st message within 10s should trigger rate limit close with code 1008."""
    token = create_access_token(1)
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws,
    ):
        for i in range(21):
            ws.send_json({"message": f"msg {i}"})
        ws.receive_json()
    assert exc_info.value.code == 1008
