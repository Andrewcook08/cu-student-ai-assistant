"""Chat WebSocket routes (CHAT-008 / CUAI-40).

Replaces the echo stub with the LangGraph conversation engine.  Each
incoming message is routed through the compiled ``StateGraph`` on
``app.state.conversation_graph``, which orchestrates intent classification,
context building, LLM inference, and tool calling.

Conversation state (last 20 messages + optional running summary) is loaded
from Redis via ``core.memory`` so multi-turn sessions work across reconnections.
The summary is passed into the LangGraph state for context building (MEM-001).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError
from langchain_core.messages import AIMessage, HumanMessage
from shared.auth import decode_access_token

from chat_service.core import memory
from chat_service.core.input_sanitizer import sanitize_message
from chat_service.services.redis_service import RedisError

#: Hard timeout for a single graph invocation (intent + context + LLM + tools).
#: Prevents the WebSocket handler from stalling indefinitely if the LLM hangs
#: or a tool call blocks.
GRAPH_TIMEOUT_SECONDS = 180

#: UUID v4 pattern — session_id must match before the message loop begins.
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

#: Maximum raw frame size in bytes.  Frames exceeding this are rejected
#: with close code 1009 (message too large).
MAX_MESSAGE_BYTES = 4096

#: Per-connection rate limit: at most this many frames per window.
RATE_LIMIT_MESSAGES = 20

#: Rolling window length in seconds for the per-connection rate limit.
RATE_LIMIT_WINDOW_SECONDS = 10

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

    # TODO(P1): replace query-string token with WebSocket subprotocol header
    #   to prevent tokens from appearing in server access logs.
    try:
        user_id = int(decode_access_token(token))
    except (JWTError, ValueError):
        await websocket.close(code=4001, reason="Invalid token")
        return

    if not _UUID4_RE.match(session_id):
        await websocket.close(code=4002, reason="Invalid session_id")
        return

    logger.info("chat: connection accepted user_id=%s session=%s", user_id, session_id)

    app = websocket.app
    graph = app.state.conversation_graph
    redis_client = app.state.redis

    rate_count = 0
    rate_window_start = time.monotonic()

    try:
        while True:
            raw = await websocket.receive_text()

            # ── Size guard ──────────────────────────────────────────
            if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                await websocket.send_json({"type": "error", "code": "message_too_large"})
                await websocket.close(code=1009)
                return

            # ── Per-connection rate limit (in-process token bucket) ─
            now = time.monotonic()
            if now - rate_window_start >= RATE_LIMIT_WINDOW_SECONDS:
                rate_count = 0
                rate_window_start = now
            rate_count += 1
            if rate_count > RATE_LIMIT_MESSAGES:
                await websocket.send_json({"type": "error", "code": "rate_limit"})
                await websocket.close(code=1008)
                return

            try:
                data = json.loads(raw)
                message = data.get("message", "") if isinstance(data, dict) else ""
            except json.JSONDecodeError:
                message = ""

            if not message.strip():
                continue

            # ── Input sanitization (SEC-002) ───────────────────────
            sanitization = sanitize_message(message)
            message = sanitization.content
            injection_warning = sanitization.injection_warning

            # Re-check after sanitization — a message made entirely of
            # control characters would be empty after stripping.
            if not message.strip():
                continue

            if sanitization.injection_flagged:
                logger.info(
                    "chat: injection pattern flagged for user_id=%s session=%s",
                    user_id,
                    session_id,
                )

            # Typing indicator — sent before processing begins.
            await websocket.send_json({"type": "typing"})

            # ── Load conversation state from Redis ──────────────────
            conv_state: dict[str, Any] = {"messages": [], "summary": None}
            try:
                conv_state = await memory.get_conversation_state(
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
            lc_messages = _redis_history_to_langchain(conv_state["messages"])
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
                "conversation_summary": conv_state["summary"],
                "injection_warning": injection_warning,
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
                await memory.save_messages(
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
