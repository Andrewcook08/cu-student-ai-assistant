"""Tests for the /ws/chat/{session_id} WebSocket endpoint."""

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from shared.auth import create_access_token


def test_websocket_echoes_message_with_valid_token(client: TestClient) -> None:
    token = create_access_token(1)
    with client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws:
        ws.send_json({"message": "hello"})
        assert ws.receive_json() == {"type": "typing"}
        assert ws.receive_json() == {
            "type": "chat_response",
            "reply": "Echo: hello",
            "session_id": "test-session",
        }


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


def test_websocket_handles_malformed_json(client: TestClient) -> None:
    token = create_access_token(1)
    with client.websocket_connect(f"/ws/chat/test-session?token={token}") as ws:
        ws.send_text("not json")
        assert ws.receive_json() == {"type": "typing"}
        assert ws.receive_json() == {
            "type": "chat_response",
            "reply": "Echo: ",
            "session_id": "test-session",
        }
