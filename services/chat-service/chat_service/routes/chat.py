"""Chat WebSocket routes."""

import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from shared.auth import decode_access_token

router = APIRouter()


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...),
) -> None:
    """WebSocket endpoint that echoes user messages with a typing indicator.

    The JWT is validated before accepting the handshake. On invalid token the
    connection is closed with code 4001. The user id encoded in the token
    subject is currently unused; it will be consumed by CHAT-008.
    """
    await websocket.accept()
    try:
        int(decode_access_token(token))
    except (JWTError, ValueError):
        # Must accept() before close() so the close frame (code 4001) reaches
        # the client. Closing pre-accept causes ASGI servers to return HTTP 403
        # and the application close code is never delivered.
        await websocket.close(code=4001, reason="Invalid token")
        return

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                message = data.get("message", "") if isinstance(data, dict) else ""
            except json.JSONDecodeError:
                message = ""

            await websocket.send_json({"type": "typing"})
            await websocket.send_json(
                {
                    "type": "chat_response",
                    "reply": f"Echo: {message}",
                    "session_id": session_id,
                }
            )
    except WebSocketDisconnect:
        return
