"""Chat WebSocket routes (CHAT-008 / CUAI-40).

Replaces the echo stub with the LangGraph conversation engine.  Each
incoming message is routed through the compiled ``StateGraph`` on
``app.state.conversation_graph``, which orchestrates intent classification,
context building, LLM inference, and tool calling.

Conversation history is persisted in Redis (last 20 messages, 2-hour TTL)
so multi-turn sessions work across reconnections.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from langchain_core.messages import AIMessage, HumanMessage
from shared.auth import decode_access_token

from chat_service.services import redis_service
from chat_service.services.redis_service import RedisError

#: Hard timeout for a single graph invocation (intent + context + LLM + tools).
#: Prevents the WebSocket handler from stalling indefinitely if the LLM hangs
#: or a tool call blocks.
GRAPH_TIMEOUT_SECONDS = 180

logger = logging.getLogger(__name__)

router = APIRouter()


def _redis_history_to_langchain(
    history: list[dict[str, Any]],
) -> list[HumanMessage | AIMessage]:
    """Convert Redis message dicts to LangChain message objects.

    Only ``user`` and ``assistant`` roles are converted.  Tool-call
    messages from prior turns are intentionally excluded — they are
    ephemeral to the tool-calling loop and should not be replayed
    into a new turn's context.
    """
    messages: list[HumanMessage | AIMessage] = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content") or ""
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...),
) -> None:
    """WebSocket endpoint for the AI chat service.

    Validates the JWT before accepting the handshake.  Each message is
    processed through the LangGraph conversation engine and the response
    (with optional structured data) is sent back.
    """
    await websocket.accept()
    try:
        user_id = int(decode_access_token(token))
    except (JWTError, ValueError):
        await websocket.close(code=4001, reason="Invalid token")
        return

    app = websocket.app
    graph = app.state.conversation_graph
    redis_client = app.state.redis

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                message = data.get("message", "") if isinstance(data, dict) else ""
            except json.JSONDecodeError:
                message = ""

            if not message.strip():
                continue

            # Typing indicator — sent before processing begins.
            await websocket.send_json({"type": "typing"})

            # ── Load conversation history from Redis ────────────────
            history: list[dict[str, Any]] = []
            try:
                history = await redis_service.get_messages(
                    redis_client, user_id=user_id, session_id=session_id
                )
            except RedisError:
                logger.warning(
                    "chat: Redis history load failed for user_id=%s session=%s, "
                    "proceeding with empty history",
                    user_id,
                    session_id,
                )

            # Convert to LangChain messages and append the new user message.
            lc_messages = _redis_history_to_langchain(history)
            lc_messages.append(HumanMessage(content=message))

            # ── Run the LangGraph engine ────────────────────────────
            initial_state: dict[str, Any] = {
                "messages": lc_messages,
                "user_id": user_id,
                "session_id": session_id,
                "intent": "",
                "context_text": "",
                "call_count": 0,
                "structured_data": [],
                "error": None,
            }

            try:
                result = await asyncio.wait_for(
                    graph.ainvoke(initial_state),
                    timeout=GRAPH_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.error(
                    "chat: graph timed out after %ds for user_id=%s session=%s",
                    GRAPH_TIMEOUT_SECONDS,
                    user_id,
                    session_id,
                )
                await websocket.send_json(
                    {
                        "type": "chat_response",
                        "reply": "The request took too long. Please try again.",
                        "session_id": session_id,
                    }
                )
                continue
            except Exception:
                logger.exception(
                    "chat: LangGraph engine failed for user_id=%s session=%s",
                    user_id,
                    session_id,
                )
                await websocket.send_json(
                    {
                        "type": "chat_response",
                        "reply": "Something went wrong. Please try again.",
                        "session_id": session_id,
                    }
                )
                continue

            # ── Extract reply ───────────────────────────────────────
            if result.get("error"):
                reply = result["error"]
                structured_data = None
            else:
                ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
                reply = (
                    (ai_messages[-1].content or "") if ai_messages else ""
                ) or "I couldn't generate a response. Please try again."
                structured_data = result.get("structured_data") or None

            # ── Persist to Redis ────────────────────────────────────
            try:
                await redis_service.append_messages(
                    redis_client,
                    user_id=user_id,
                    session_id=session_id,
                    messages=[
                        {"role": "user", "content": message},
                        {"role": "assistant", "content": reply},
                    ],
                )
            except RedisError:
                logger.warning(
                    "chat: Redis message persist failed for user_id=%s session=%s",
                    user_id,
                    session_id,
                )

            # ── Send response ───────────────────────────────────────
            response: dict[str, Any] = {
                "type": "chat_response",
                "reply": reply,
                "session_id": session_id,
            }
            if structured_data:
                response["structured_data"] = structured_data

            await websocket.send_json(response)

    except WebSocketDisconnect:
        return
