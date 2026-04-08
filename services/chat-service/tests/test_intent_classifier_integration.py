"""Integration tests for the intent classifier against a real Ollama (gpt-oss:20b).

These tests are gated behind the ``integration`` pytest marker so the
default ``uv run pytest`` skips them. Run them explicitly with::

    uv run pytest -m integration services/chat-service/tests/test_intent_classifier_integration.py

What these tests verify that the unit tests cannot:

- Ollama actually accepts the JSON-schema ``format`` argument and applies
  constrained decoding (the response is parseable JSON every time).
- The model picks the *correct* label for each of the five Jira
  acceptance examples — i.e. the prompt + descriptions + few-label
  schema is sufficient to disambiguate them.
- The full pipeline through ``classify_intent`` works against a live
  ``httpx.AsyncClient`` rather than mocks.

The tests use messages chosen to **bypass the heuristic path** so the
LLM fallback is genuinely exercised. (The Jira acceptance examples all
hit the heuristic, so they would skip the LLM entirely — instead we use
near-paraphrases that the heuristic cannot classify.)
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import httpx
import pytest
from chat_service.core.intent_classifier import Intent, classify_intent

pytestmark = pytest.mark.integration


def _ollama_url() -> str:
    """Resolve Ollama URL — env var wins so CI can point at a different host."""
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")


@pytest.fixture
async def ollama_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Yield a real httpx client pointed at the local Ollama daemon.

    Connection is verified up-front via ``GET /api/tags`` so a missing
    Ollama fails fast and clearly instead of timing out mid-test.
    """
    client = httpx.AsyncClient(
        base_url=_ollama_url(),
        timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=10.0),
    )
    try:
        # Sanity check the connection.
        resp = await client.get("/api/tags")
        resp.raise_for_status()
        yield client
    finally:
        await client.aclose()


# ─── Heuristic-bypassing prompts ─────────────────────────────────────────
#
# Each of these is a paraphrase that does NOT contain any of the heuristic
# keywords (no "prereq", no "schedule", no "degree"/"major", no "course"/
# "class"/"elective", no course code), so the message falls through to the
# LLM fallback path. This forces a real round-trip to gpt-oss:20b for
# every test below.

_LLM_PROMPTS = [
    pytest.param(
        "Show me anything in the machine learning area I could enroll in next term",
        Intent.COURSE_SEARCH,
        id="ml_enrollment_paraphrase",
    ),
    pytest.param(
        "What do I have to take first before I can sign up for data structures?",
        Intent.PREREQ_CHECK,
        id="prereq_paraphrase_no_keyword",
    ),
    pytest.param(
        "Am I on track to finish my computer science studies on time?",
        Intent.DEGREE_PLANNING,
        id="degree_progress_paraphrase",
    ),
    pytest.param(
        "Do these two sections meet at the same time on Tuesdays?",
        Intent.SCHEDULE_HELP,
        id="schedule_paraphrase_no_keyword",
    ),
    pytest.param(
        "What's the weather like in Boulder today?",
        Intent.GENERAL_QUESTION,
        id="off_topic_smalltalk",
    ),
]


@pytest.mark.parametrize(("message", "expected"), _LLM_PROMPTS)
async def test_llm_fallback_picks_correct_intent_for_paraphrases(
    ollama_client: httpx.AsyncClient,
    message: str,
    expected: Intent,
) -> None:
    """gpt-oss:20b + structured output should pick the right label for paraphrases.

    These messages deliberately avoid every heuristic keyword so the LLM
    is the *only* thing classifying them. If this test fails it means
    either (a) the prompt isn't precise enough, (b) the schema isn't
    being applied, or (c) the model needs a different prompt entirely.
    """
    result = await classify_intent(message, ollama_client=ollama_client)
    assert result == expected, (
        f"gpt-oss:20b classified {message!r} as {result!r} (expected {expected!r})"
    )


async def test_llm_fallback_returns_valid_intent_for_every_paraphrase(
    ollama_client: httpx.AsyncClient,
) -> None:
    """Even if the *label* is wrong, the response must always be a valid Intent.

    This is the constrained-decoding contract: with the JSON-schema enum
    in place, Ollama cannot return an out-of-enum value. Failing this
    test means structured output isn't actually being enforced and we'd
    have a silent regression.
    """
    for param in _LLM_PROMPTS:
        message = param.values[0]
        result = await classify_intent(message, ollama_client=ollama_client)
        assert isinstance(result, Intent), (
            f"Expected Intent, got {type(result).__name__}: {result!r}"
        )
