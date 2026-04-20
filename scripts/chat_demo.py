#!/usr/bin/env python3
"""Interactive chat demo for the CU Student AI Assistant.

Prerequisites:
  1. Docker services up: docker compose up -d postgres neo4j redis
  2. Data ingested (courses, programs, prereqs, embeddings)
  3. Chat service running:
       cd services/chat-service && source ../../.env && source ../../.env.local && \
       uv run uvicorn chat_service.main:app --port 8001

Usage:
  cd <project-root>
  source .env && source .env.local
  uv run python scripts/chat_demo.py

  Then just type messages and press Enter. Type 'quit' to exit.

Try these:
  - "What CS courses are available?"
  - "Tell me about Data Structures"
  - "What are the prerequisites for CSCI 3104?"
  - "Can you help me plan my schedule for next semester?"
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import websockets

# --- Config ---
CHAT_SERVICE_URL = "ws://localhost:8001"
USER_ID = 8  # test user created during E2E testing


def _get_token() -> str:
    """Generate a JWT for the test user."""
    # Import from the shared package so we use the same secret/algorithm
    from shared.auth import create_access_token

    return create_access_token(USER_ID)


async def chat_session() -> None:
    session_id = f"demo-{uuid.uuid4().hex[:8]}"
    token = _get_token()
    url = f"{CHAT_SERVICE_URL}/ws/chat/{session_id}?token={token}"

    print("=" * 60)
    print("  CU Student AI Assistant — Interactive Demo")
    print("=" * 60)
    print(f"  Session: {session_id}")
    print(f"  User ID: {USER_ID}")
    print()
    print("  Type a message and press Enter.")
    print("  Type 'quit' or Ctrl+C to exit.")
    print("=" * 60)
    print()

    try:
        async with websockets.connect(url) as ws:
            while True:
                # Read user input
                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input("\033[1;36mYou:\033[0m ")
                    )
                except EOFError:
                    break

                if user_input.strip().lower() in ("quit", "exit", "q"):
                    print("\nGoodbye!")
                    break

                if not user_input.strip():
                    continue

                # Send message
                await ws.send(json.dumps({"message": user_input}))

                # Receive typing indicator
                raw = await ws.recv()
                data = json.loads(raw)
                if data.get("type") == "typing":
                    print("\033[2m  (thinking...)\033[0m", end="", flush=True)

                # Receive response
                raw = await ws.recv()
                data = json.loads(raw)

                if data.get("type") == "chat_response":
                    print(f"\r\033[1;32mAssistant:\033[0m {data['reply']}")

                    # Show structured data (CourseCards) if present
                    cards = data.get("structured_data")
                    if cards:
                        print(f"\n\033[1;33m  [{len(cards)} course card(s)]:\033[0m")
                        for card in cards[:5]:  # show first 5
                            code = card.get("code", "?")
                            title = card.get("title", "?")
                            credits = card.get("credits", "?")
                            print(f"    • {code}: {title} ({credits} cr)")
                        if len(cards) > 5:
                            print(f"    ... and {len(cards) - 5} more")

                print()

    except websockets.exceptions.ConnectionClosedError as e:
        print(f"\nConnection closed: {e}")
    except ConnectionRefusedError:
        print("\n\033[1;31mError:\033[0m Could not connect to chat service at", CHAT_SERVICE_URL)
        print("Make sure the chat service is running:")
        print("  cd services/chat-service && source ../../.env && source ../../.env.local && \\")
        print("    uv run uvicorn chat_service.main:app --port 8001")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(chat_session())
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
