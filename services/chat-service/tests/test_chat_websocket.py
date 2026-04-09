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
