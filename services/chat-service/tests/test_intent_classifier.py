"""Unit tests for chat_service.core.intent_classifier (CHAT-007 / CUAI-39).

The five Jira acceptance examples are exercised against the heuristic
path with no Ollama dependency.  LLM fallback behaviour is covered
separately by patching ``chat_completion`` and asserting it is only
called when the heuristic returns GENERAL_QUESTION.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from chat_service.core.intent_classifier import Intent, classify_intent
from chat_service.services.ollama_service import OllamaServiceError

# ─── Acceptance criteria (no ollama_client) ──────────────────────────────


@pytest.mark.asyncio
async def test_acceptance_cs_electives_is_course_search() -> None:
    assert await classify_intent("What CS electives are there?") == Intent.COURSE_SEARCH


@pytest.mark.asyncio
async def test_acceptance_prereqs_for_csci_3104_is_prereq_check() -> None:
    assert await classify_intent("What are prerequisites for CSCI 3104?") == Intent.PREREQ_CHECK


@pytest.mark.asyncio
async def test_acceptance_cs_degree_is_degree_planning() -> None:
    assert await classify_intent("What do I need for my CS degree?") == Intent.DEGREE_PLANNING


@pytest.mark.asyncio
async def test_acceptance_schedule_conflicts_is_schedule_help() -> None:
    assert await classify_intent("Can you check my schedule for conflicts?") == Intent.SCHEDULE_HELP


@pytest.mark.asyncio
async def test_acceptance_favorite_color_is_general_question() -> None:
    assert await classify_intent("What is your favorite color?") == Intent.GENERAL_QUESTION


# ─── Edge cases ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_string_is_general_question() -> None:
    assert await classify_intent("") == Intent.GENERAL_QUESTION


@pytest.mark.asyncio
async def test_whitespace_only_is_general_question() -> None:
    assert await classify_intent("   \n\t  ") == Intent.GENERAL_QUESTION


@pytest.mark.asyncio
async def test_case_insensitive_prereq_match() -> None:
    assert await classify_intent("WHAT ARE PREREQS FOR CSCI 3104?") == Intent.PREREQ_CHECK


@pytest.mark.asyncio
async def test_bare_course_code_is_course_search() -> None:
    """A course code with no other keywords should land in COURSE_SEARCH."""
    assert await classify_intent("CSCI 2270") == Intent.COURSE_SEARCH


@pytest.mark.asyncio
async def test_mixed_intent_prereq_wins_over_schedule_due_to_ordering() -> None:
    """Documenting the ordering choice: prereq_check runs before schedule_help.

    A message that mentions both a prerequisite and a schedule conflict
    should be classified as PREREQ_CHECK because that rule fires first.
    """
    message = "what's the prereq for CSCI 3104 and does it conflict with my schedule"
    assert await classify_intent(message) == Intent.PREREQ_CHECK


@pytest.mark.asyncio
async def test_course_code_regex_handles_multi_space() -> None:
    """Double-space and tab between dept and number should still match."""
    assert await classify_intent("CSCI  3104") == Intent.COURSE_SEARCH
    assert await classify_intent("CSCI\t3104") == Intent.COURSE_SEARCH


@pytest.mark.asyncio
async def test_requirements_with_course_code_is_prereq_check() -> None:
    """'requirements for CSCI 3104' is a prereq question, not degree planning.

    Without a course code, 'requirements' still routes to DEGREE_PLANNING.
    The course code is the disambiguator.
    """
    assert await classify_intent("What are the requirements for CSCI 3104?") == Intent.PREREQ_CHECK
    assert (
        await classify_intent("What are the requirements for the CS major?")
        == Intent.DEGREE_PLANNING
    )


@pytest.mark.asyncio
async def test_classify_intent_never_raises_on_weird_input() -> None:
    # Punctuation-only, very long, etc. — should always return an Intent.
    assert await classify_intent("???!!!") == Intent.GENERAL_QUESTION
    assert isinstance(await classify_intent("a" * 5000), Intent)


# ─── Intent enum shape ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("course_search", Intent.COURSE_SEARCH),
        ("prereq_check", Intent.PREREQ_CHECK),
        ("degree_planning", Intent.DEGREE_PLANNING),
        ("schedule_help", Intent.SCHEDULE_HELP),
        ("general_question", Intent.GENERAL_QUESTION),
    ],
)
def test_intent_enum_string_values(value: str, expected: Intent) -> None:
    assert Intent(value) is expected
    # str-mixin: the value compares equal to the raw string for clean
    # JSON / LangGraph state serialisation.
    assert expected == value


def test_intent_enum_has_exactly_five_members() -> None:
    assert len(list(Intent)) == 5


# ─── Performance budget ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heuristic_classification_under_budget() -> None:
    """Heuristic path should run in well under 500ms (budget is generous)."""
    start = time.perf_counter()
    result = await classify_intent("What are prerequisites for CSCI 3104?")
    elapsed = time.perf_counter() - start
    assert result == Intent.PREREQ_CHECK
    assert elapsed < 0.25, f"Heuristic classification took {elapsed:.4f}s (>250ms budget)"


# ─── LLM fallback ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_fallback_used_when_heuristic_returns_general() -> None:
    """When heuristic falls through and a client is provided, LLM is consulted."""
    fake_client = MagicMock()
    with patch(
        "chat_service.core.intent_classifier.chat_completion",
        new=AsyncMock(return_value={"content": "course_search"}),
    ) as mock_chat:
        result = await classify_intent("tell me about stuff", ollama_client=fake_client)

    mock_chat.assert_awaited_once()
    assert result == Intent.COURSE_SEARCH


@pytest.mark.asyncio
async def test_llm_fallback_returns_general_on_ollama_error() -> None:
    fake_client = MagicMock()
    with patch(
        "chat_service.core.intent_classifier.chat_completion",
        new=AsyncMock(side_effect=OllamaServiceError("boom")),
    ):
        result = await classify_intent("ramble ramble", ollama_client=fake_client)
    assert result == Intent.GENERAL_QUESTION


@pytest.mark.asyncio
async def test_llm_fallback_returns_general_on_unknown_label() -> None:
    fake_client = MagicMock()
    with patch(
        "chat_service.core.intent_classifier.chat_completion",
        new=AsyncMock(return_value={"content": "nonsense"}),
    ):
        result = await classify_intent("ramble ramble", ollama_client=fake_client)
    assert result == Intent.GENERAL_QUESTION


@pytest.mark.asyncio
async def test_llm_fallback_returns_general_on_empty_content() -> None:
    fake_client = MagicMock()
    with patch(
        "chat_service.core.intent_classifier.chat_completion",
        new=AsyncMock(return_value={"content": ""}),
    ):
        result = await classify_intent("ramble ramble", ollama_client=fake_client)
    assert result == Intent.GENERAL_QUESTION


@pytest.mark.parametrize(
    "raw_label",
    [
        "course_search.",
        "course_search,",
        "  COURSE_SEARCH\n",
        "course-search",
        "course search",
        "'course_search'",
        # Wrapper-format variants — gpt-oss-tier models routinely emit these
        # even when told "ONLY the label".
        "Intent: course_search",
        "The answer is course_search.",
        "Label: course_search",
        "**course_search**",
    ],
)
@pytest.mark.asyncio
async def test_llm_fallback_normalizes_label_variants(raw_label: str) -> None:
    """Small models routinely add punctuation, case, hyphen, or wrapper variants."""
    fake_client = MagicMock()
    with patch(
        "chat_service.core.intent_classifier.chat_completion",
        new=AsyncMock(return_value={"content": raw_label}),
    ):
        result = await classify_intent("ramble ramble", ollama_client=fake_client)
    assert result == Intent.COURSE_SEARCH


@pytest.mark.asyncio
async def test_llm_fallback_uses_structured_output_schema_and_zero_temp() -> None:
    """Verify the fallback call sets ``format`` (enum schema) and ``options.temperature=0``.

    The whole point of structured outputs is constrained decoding — if we
    don't actually pass the schema, we lose the guarantee. This test pins
    that contract.
    """
    fake_client = MagicMock()
    mock_chat = AsyncMock(return_value={"content": '{"intent": "course_search"}'})
    with patch("chat_service.core.intent_classifier.chat_completion", new=mock_chat):
        await classify_intent("tell me about stuff", ollama_client=fake_client)

    mock_chat.assert_awaited_once()
    _, kwargs = mock_chat.await_args.args, mock_chat.await_args.kwargs
    schema = kwargs["format"]
    assert schema["type"] == "object"
    assert schema["properties"]["intent"]["type"] == "string"
    assert set(schema["properties"]["intent"]["enum"]) == {i.value for i in Intent}
    assert schema["required"] == ["intent"]
    assert kwargs["options"] == {"temperature": 0}


@pytest.mark.parametrize(
    ("json_payload", "expected"),
    [
        ('{"intent": "course_search"}', Intent.COURSE_SEARCH),
        ('{"intent": "prereq_check"}', Intent.PREREQ_CHECK),
        ('{"intent": "degree_planning"}', Intent.DEGREE_PLANNING),
        ('{"intent": "schedule_help"}', Intent.SCHEDULE_HELP),
        ('{"intent": "general_question"}', Intent.GENERAL_QUESTION),
        # Whitespace and newlines around the JSON — Ollama sometimes pads.
        ('  {"intent": "course_search"}  \n', Intent.COURSE_SEARCH),
    ],
)
@pytest.mark.asyncio
async def test_llm_fallback_parses_structured_json(json_payload: str, expected: Intent) -> None:
    """The happy path: ``content`` is a JSON object matching the schema."""
    fake_client = MagicMock()
    with patch(
        "chat_service.core.intent_classifier.chat_completion",
        new=AsyncMock(return_value={"content": json_payload}),
    ):
        result = await classify_intent("ramble ramble", ollama_client=fake_client)
    assert result == expected


@pytest.mark.asyncio
async def test_llm_fallback_handles_json_with_unknown_intent() -> None:
    """Defense in depth: if Ollama somehow returns a JSON object with an
    intent value outside the enum (shouldn't happen with constrained
    decoding, but a buggy server or version mismatch could), fall back
    to GENERAL_QUESTION rather than crashing."""
    fake_client = MagicMock()
    with patch(
        "chat_service.core.intent_classifier.chat_completion",
        new=AsyncMock(return_value={"content": '{"intent": "bogus_label"}'}),
    ):
        result = await classify_intent("ramble ramble", ollama_client=fake_client)
    assert result == Intent.GENERAL_QUESTION


@pytest.mark.asyncio
async def test_llm_fallback_skipped_when_heuristic_matches() -> None:
    """If the heuristic is confident, the LLM must NOT be called even if a client is supplied."""
    fake_client = MagicMock()
    with patch(
        "chat_service.core.intent_classifier.chat_completion",
        new=AsyncMock(return_value={"content": "course_search"}),
    ) as mock_chat:
        result = await classify_intent(
            "What are prerequisites for CSCI 3104?", ollama_client=fake_client
        )

    mock_chat.assert_not_awaited()
    assert result == Intent.PREREQ_CHECK
