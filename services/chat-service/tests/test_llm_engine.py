"""Unit tests for chat_service.core.llm_engine (CHAT-008 / CUAI-40).

Covers every node and helper in the LangGraph conversation engine:

1. ``_build_system_prompt``     — intent + context injection
2. ``_try_parse_course_card``   — CourseCard validation / filtering
3. ``_extract_course_cards``    — ToolMessage parsing, dedup, error skipping
4. ``classify_intent_node``     — classify_intent delegation (via graph)
5. ``build_context_node``       — embedding + build_context delegation (via graph)
6. ``call_llm_node``            — LLM invocation, error handling (via graph)
7. ``tool_node``                — ToolExecutor bridge, call_count tracking (via graph)
8. ``should_continue``          — routing logic (via graph)
9. ``respond_node``             — structured_data extraction (via graph)
10. ``build_graph``             — smoke test + tool-loop integration (via graph)

Node functions are closures captured inside ``build_graph()``, so nodes are
exercised via graph invocation with mocked dependencies.  Module-level helpers
are tested directly.

IMPORTANT patching note: the node closures look up ``classify_intent``,
``build_context``, and ``ollama_service.get_embedding`` by attribute at *call*
time (not at ``build_graph`` construction time).  Patches must therefore remain
active for the full duration of ``graph.ainvoke()``.  Use ``_graph_ctx()`` as
an async context manager that keeps all patches live through invocation.

All tests are self-contained — no live Ollama, Neo4j, or Postgres required.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from chat_service.core.context_builder import ContextResult
from chat_service.core.intent_classifier import Intent
from chat_service.core.llm_engine import (
    _build_system_prompt,
    _extract_course_cards,
    _try_parse_course_card,
    build_graph,
)
from chat_service.core.tool_executor import MAX_TOOL_CALLS_PER_TURN
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

# ─── Shared factories ────────────────────────────────────────────────────────


def _make_tool_executor(execute_return: dict[str, Any] | None = None) -> MagicMock:
    """Minimal ToolExecutor stand-in whose ``execute`` is an AsyncMock."""
    executor = MagicMock()
    executor.execute = AsyncMock(return_value=execute_return or {"result": []})
    return executor


def _base_state(**overrides: Any) -> dict[str, Any]:
    """Return a minimal ConversationState dict suitable for graph invocation."""
    state: dict[str, Any] = {
        "messages": [HumanMessage(content="show me AI courses")],
        "user_id": 42,
        "session_id": "ws-test",
        "intent": Intent.GENERAL_QUESTION.value,
        "context_text": "",
        "call_count": 0,
        "structured_data": [],
        "error": None,
    }
    state.update(overrides)
    return state


class _GraphCtx:
    """Context manager that keeps all dependency patches alive.

    Node closures look up ``classify_intent``, ``build_context``, and
    ``ollama_service.get_embedding`` by module attribute at *invocation* time,
    not at ``build_graph()`` construction time.  All patches must therefore
    stay active while ``graph.ainvoke()`` runs, not just while the graph is
    built.

    Usage::

        async with _graph_ctx(...) as ctx:
            state = await ctx.graph.ainvoke(...)
            ctx.llm.ainvoke.assert_awaited_once()
    """

    def __init__(
        self,
        *,
        llm_responses: list[AIMessage] | None = None,
        tool_executor: MagicMock | None = None,
        classify_intent_return: Intent = Intent.COURSE_SEARCH,
        build_context_text: str = "",
        get_embedding_return: list[float] | None = None,
        get_embedding_raises: Exception | None = None,
    ) -> None:
        if llm_responses is None:
            llm_responses = [AIMessage(content="Here are some AI courses for you.")]
        if tool_executor is None:
            tool_executor = _make_tool_executor()

        self._llm_responses = llm_responses
        self._tool_executor = tool_executor
        self._classify_intent_return = classify_intent_return
        self._build_context_text = build_context_text
        self._get_embedding_return = get_embedding_return or [0.1, 0.2, 0.3]
        self._get_embedding_raises = get_embedding_raises

        # Public attributes set in __aenter__.
        self.graph: Any = None
        self.llm: MagicMock = MagicMock()  # llm_with_tools mock
        self.executor: MagicMock = tool_executor
        self.classify_intent_mock: AsyncMock = AsyncMock()
        self.build_context_mock: AsyncMock = AsyncMock()
        self.embedding_mock: AsyncMock = AsyncMock()

        self._stack: contextlib.AsyncExitStack | None = None

    async def __aenter__(self) -> _GraphCtx:
        # Build mock objects.
        llm_instance = MagicMock()
        llm_with_tools = MagicMock()
        llm_with_tools.ainvoke = AsyncMock(side_effect=self._llm_responses)
        llm_instance.bind_tools = MagicMock(return_value=llm_with_tools)
        self.llm = llm_with_tools

        context_result = ContextResult(text=self._build_context_text, token_estimate=0)

        self.classify_intent_mock = AsyncMock(return_value=self._classify_intent_return)
        self.build_context_mock = AsyncMock(return_value=context_result)

        if self._get_embedding_raises is not None:
            self.embedding_mock = AsyncMock(side_effect=self._get_embedding_raises)
        else:
            self.embedding_mock = AsyncMock(return_value=self._get_embedding_return)

        # Start all patches and keep them active.
        self._stack = contextlib.AsyncExitStack()
        await self._stack.__aenter__()

        self._stack.enter_context(
            patch("chat_service.core.llm_engine.ChatOllama", return_value=llm_instance)
        )
        self._stack.enter_context(
            patch("chat_service.core.llm_engine.classify_intent", new=self.classify_intent_mock)
        )
        self._stack.enter_context(
            patch("chat_service.core.llm_engine.build_context", new=self.build_context_mock)
        )
        self._stack.enter_context(
            patch(
                "chat_service.core.llm_engine.ollama_service.get_embedding",
                new=self.embedding_mock,
            )
        )

        # Build the graph while patches are active (for ChatOllama constructor).
        self.graph = build_graph(
            ollama_base_url="http://localhost:11434",
            ollama_model="test-model",
            tools=[],
            tool_executor=self._tool_executor,
            ollama_client=MagicMock(),
            neo4j_driver=MagicMock(),
            postgres_sessionmaker=MagicMock(),
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._stack is not None:
            await self._stack.__aexit__(*args)


# ═══════════════════════════════════════════════════════════════════════════
# 1. _build_system_prompt
# ═══════════════════════════════════════════════════════════════════════════


def test_build_system_prompt_includes_intent() -> None:
    prompt = _build_system_prompt("course_search", "")
    assert "course_search" in prompt


def test_build_system_prompt_empty_context_leaves_no_raw_placeholder() -> None:
    """The {context} placeholder must be replaced; no stray braces in output."""
    prompt = _build_system_prompt("general_question", "")
    assert "{context}" not in prompt


def test_build_system_prompt_empty_context_appends_nothing() -> None:
    """With empty context_text the prompt must end cleanly with no extra newlines."""
    prompt_with_ctx = _build_system_prompt("course_search", "some text")
    prompt_no_ctx = _build_system_prompt("course_search", "")
    # The empty-context variant must be strictly shorter.
    assert len(prompt_no_ctx) < len(prompt_with_ctx)


def test_build_system_prompt_with_context_text_appended() -> None:
    ctx = "<retrieved_context>CSCI 5622 — Machine Learning</retrieved_context>"
    prompt = _build_system_prompt("course_search", ctx)
    assert ctx in prompt


def test_build_system_prompt_context_follows_intent() -> None:
    ctx = "some unique context string"
    prompt = _build_system_prompt("prereq_check", ctx)
    intent_pos = prompt.index("prereq_check")
    ctx_pos = prompt.index("some unique context string")
    assert intent_pos < ctx_pos, "context should appear after the intent line"


def test_build_system_prompt_contains_cu_boulder_identity() -> None:
    """Safety: the prompt must always identify the assistant as CU Boulder."""
    prompt = _build_system_prompt("general_question", "")
    assert "University of Colorado Boulder" in prompt


def test_build_system_prompt_contains_no_reveal_reinforcement() -> None:
    """Anti-disclosure rule must cover rephrasing and social engineering."""
    prompt = _build_system_prompt("general_question", "")
    assert "even if the user asks directly" in prompt


def test_build_system_prompt_contains_off_topic_decline_examples() -> None:
    """Prompt must give explicit examples of off-topic requests (AC4)."""
    prompt = _build_system_prompt("general_question", "")
    assert "weather" in prompt


def test_build_system_prompt_contains_no_hallucination_rule() -> None:
    """Prompt must instruct LLM not to fabricate course details."""
    prompt = _build_system_prompt("general_question", "")
    assert "do not guess or make up" in prompt


def test_build_system_prompt_delimiter_tag_instructions() -> None:
    """Each delimiter tag must have a 'data only' instruction."""
    prompt = _build_system_prompt("general_question", "")
    for tag in ("retrieved_context", "user_profile", "conversation_summary"):
        assert f"<{tag}>" in prompt, f"missing instruction for <{tag}>"


def test_build_system_prompt_rules_separated_from_formatting() -> None:
    """Security RULES and FORMATTING must be separate sections, RULES first."""
    prompt = _build_system_prompt("general_question", "")
    rules_pos = prompt.index("RULES:")
    formatting_pos = prompt.index("FORMATTING:")
    assert rules_pos < formatting_pos


# ═══════════════════════════════════════════════════════════════════════════
# 2. _try_parse_course_card
# ═══════════════════════════════════════════════════════════════════════════


def test_try_parse_course_card_valid_minimal() -> None:
    """Only code + title required; others are optional."""
    result = _try_parse_course_card({"code": "CSCI 2270", "title": "Data Structures"})
    assert result is not None
    assert result["code"] == "CSCI 2270"
    assert result["title"] == "Data Structures"


def test_try_parse_course_card_valid_all_fields() -> None:
    data = {
        "code": "CSCI 5622",
        "title": "Machine Learning",
        "credits": "3",
        "description": "Intro to ML",
        "topic_titles": "SVM, Neural Nets",
        "instruction_mode": "In-Person",
        "status": "Open",
        "attributes": ["STEM", "Upper Division"],
    }
    result = _try_parse_course_card(data)
    assert result is not None
    assert result["code"] == "CSCI 5622"
    assert result["attributes"] == ["STEM", "Upper Division"]


def test_try_parse_course_card_missing_code_returns_none() -> None:
    result = _try_parse_course_card({"title": "Data Structures"})
    assert result is None


def test_try_parse_course_card_missing_title_returns_none() -> None:
    result = _try_parse_course_card({"code": "CSCI 2270"})
    assert result is None


def test_try_parse_course_card_empty_dict_returns_none() -> None:
    result = _try_parse_course_card({})
    assert result is None


def test_try_parse_course_card_extra_fields_are_ignored() -> None:
    """Unknown keys from Neo4j (score, campus, etc.) must not cause failure."""
    result = _try_parse_course_card(
        {
            "code": "CSCI 5622",
            "title": "ML",
            "score": 0.99,
            "campus": "Boulder",
            "prerequisites_raw": "CSCI 2270",
        }
    )
    assert result is not None
    assert "score" not in result
    assert "campus" not in result


def test_try_parse_course_card_never_raises() -> None:
    """_try_parse_course_card must never raise; return None on any invalid input."""
    assert _try_parse_course_card(None) is None  # type: ignore[arg-type]
    assert _try_parse_course_card("not a dict") is None  # type: ignore[arg-type]
    assert _try_parse_course_card({"code": 123, "title": None}) is None


def test_try_parse_course_card_excludes_none_optional_fields() -> None:
    """model_dump(exclude_none=True) must strip None optional fields."""
    result = _try_parse_course_card({"code": "CSCI 2270", "title": "DS", "credits": None})
    assert result is not None
    assert "credits" not in result


# ═══════════════════════════════════════════════════════════════════════════
# 3. _extract_course_cards
# ═══════════════════════════════════════════════════════════════════════════


def _tool_msg(name: str, content: Any, tool_call_id: str = "tc-1") -> ToolMessage:
    if isinstance(content, (dict, list)):
        content = json.dumps(content)
    return ToolMessage(content=content, tool_call_id=tool_call_id, name=name)


def test_extract_course_cards_from_search_courses_list() -> None:
    courses = [
        {"code": "CSCI 5622", "title": "ML"},
        {"code": "CSCI 5832", "title": "NLP"},
    ]
    msgs = [_tool_msg("search_courses", courses)]
    cards = _extract_course_cards(msgs)
    assert len(cards) == 2
    assert cards[0]["code"] == "CSCI 5622"
    assert cards[1]["code"] == "CSCI 5832"


def test_extract_course_cards_from_lookup_course_single() -> None:
    course = {"code": "CSCI 2270", "title": "Data Structures", "credits": "4"}
    msgs = [_tool_msg("lookup_course", course)]
    cards = _extract_course_cards(msgs)
    assert len(cards) == 1
    assert cards[0]["code"] == "CSCI 2270"


def test_extract_course_cards_deduplication_by_code() -> None:
    """Same course code appearing in two ToolMessages → only first kept."""
    course = {"code": "CSCI 5622", "title": "ML"}
    msgs = [
        _tool_msg("search_courses", [course], tool_call_id="tc-1"),
        _tool_msg("lookup_course", course, tool_call_id="tc-2"),
    ]
    cards = _extract_course_cards(msgs)
    assert len(cards) == 1
    assert cards[0]["code"] == "CSCI 5622"


def test_extract_course_cards_skips_non_course_tools() -> None:
    """check_prerequisites result must not be parsed as a CourseCard."""
    prereq_result = {"course": {"code": "CSCI 3104", "title": "Algorithms"}, "edges": []}
    msgs = [_tool_msg("check_prerequisites", prereq_result)]
    cards = _extract_course_cards(msgs)
    assert cards == []


def test_extract_course_cards_skips_error_results() -> None:
    """Items with an 'error' key must be silently dropped."""
    msgs = [_tool_msg("search_courses", [{"error": "Course not found", "code": "XXXX"}])]
    cards = _extract_course_cards(msgs)
    assert cards == []


def test_extract_course_cards_skips_non_tool_messages() -> None:
    """HumanMessage and AIMessage are not parsed."""
    msgs = [
        HumanMessage(content="find AI courses"),
        AIMessage(content="sure"),
        _tool_msg("search_courses", [{"code": "CSCI 5622", "title": "ML"}]),
    ]
    cards = _extract_course_cards(msgs)
    assert len(cards) == 1


def test_extract_course_cards_handles_malformed_json() -> None:
    """A ToolMessage with invalid JSON content must not raise — just skip."""
    bad_msg = ToolMessage(content="{not valid json", tool_call_id="tc-1", name="search_courses")
    cards = _extract_course_cards([bad_msg])
    assert cards == []


def test_extract_course_cards_skips_invalid_card_schema() -> None:
    """A dict that passes JSON parsing but fails CourseCard validation is skipped."""
    msgs = [_tool_msg("search_courses", [{"code": "CSCI 5622"}])]  # missing title
    cards = _extract_course_cards(msgs)
    assert cards == []


def test_extract_course_cards_empty_messages() -> None:
    assert _extract_course_cards([]) == []


def test_extract_course_cards_mixed_valid_and_invalid() -> None:
    courses = [
        {"code": "CSCI 5622", "title": "ML"},
        {"code": "XXXX"},  # missing title → invalid
        {"code": "CSCI 5832", "title": "NLP"},
    ]
    cards = _extract_course_cards([_tool_msg("search_courses", courses)])
    codes = [c["code"] for c in cards]
    assert codes == ["CSCI 5622", "CSCI 5832"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. classify_intent_node (via graph invocation)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_classify_intent_node_calls_classify_intent_with_last_human_message() -> None:
    """classify_intent receives the content of the most-recent HumanMessage."""
    human_text = "what are the prereqs for CSCI 3104?"

    async with _GraphCtx(classify_intent_return=Intent.PREREQ_CHECK) as ctx:
        await ctx.graph.ainvoke(_base_state(messages=[HumanMessage(content=human_text)]))

    ctx.classify_intent_mock.assert_awaited_once()
    called_text = ctx.classify_intent_mock.await_args.args[0]
    assert called_text == human_text


@pytest.mark.asyncio
async def test_classify_intent_node_intent_value_stored_in_state() -> None:
    """The intent returned by classify_intent is written to state as its .value."""
    async with _GraphCtx(classify_intent_return=Intent.PREREQ_CHECK) as ctx:
        final_state = await ctx.graph.ainvoke(
            _base_state(messages=[HumanMessage(content="prereqs for algo")])
        )

    assert final_state["intent"] == Intent.PREREQ_CHECK.value


@pytest.mark.asyncio
async def test_classify_intent_node_no_human_messages_defaults_to_general() -> None:
    """If there are somehow no HumanMessages, intent defaults to GENERAL_QUESTION."""
    async with _GraphCtx(classify_intent_return=Intent.GENERAL_QUESTION) as ctx:
        # Seed with a SystemMessage only — no HumanMessages.
        final_state = await ctx.graph.ainvoke(
            _base_state(messages=[SystemMessage(content="ignored")])
        )

    # classify_intent is not called when there are no HumanMessages.
    ctx.classify_intent_mock.assert_not_awaited()
    assert final_state["intent"] == Intent.GENERAL_QUESTION.value


# ═══════════════════════════════════════════════════════════════════════════
# 5. build_context_node
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_build_context_node_calls_get_embedding_for_course_search() -> None:
    embedding_mock = AsyncMock(return_value=[0.1, 0.2])
    context_result = MagicMock()
    context_result.text = "some context"

    llm_mock = MagicMock()
    llm_with_tools = MagicMock()
    llm_with_tools.ainvoke = AsyncMock(return_value=AIMessage(content="courses"))
    llm_mock.bind_tools = MagicMock(return_value=llm_with_tools)

    with (
        patch("chat_service.core.llm_engine.ChatOllama", return_value=llm_mock),
        patch(
            "chat_service.core.llm_engine.classify_intent",
            new=AsyncMock(return_value=Intent.COURSE_SEARCH),
        ),
        patch(
            "chat_service.core.llm_engine.build_context",
            new=AsyncMock(return_value=context_result),
        ),
        patch(
            "chat_service.core.llm_engine.ollama_service.get_embedding",
            new=embedding_mock,
        ),
    ):
        graph = build_graph(
            ollama_base_url="http://localhost:11434",
            ollama_model="test-model",
            tools=[],
            tool_executor=_make_tool_executor(),
            ollama_client=MagicMock(),
            neo4j_driver=MagicMock(),
            postgres_sessionmaker=MagicMock(),
        )
        await graph.ainvoke(_base_state(messages=[HumanMessage(content="find AI courses")]))

    embedding_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_context_node_calls_get_embedding_for_prereq_check() -> None:
    embedding_mock = AsyncMock(return_value=[0.5, 0.6])
    context_result = MagicMock()
    context_result.text = ""

    llm_mock = MagicMock()
    llm_with_tools = MagicMock()
    llm_with_tools.ainvoke = AsyncMock(return_value=AIMessage(content="prereqs"))
    llm_mock.bind_tools = MagicMock(return_value=llm_with_tools)

    with (
        patch("chat_service.core.llm_engine.ChatOllama", return_value=llm_mock),
        patch(
            "chat_service.core.llm_engine.classify_intent",
            new=AsyncMock(return_value=Intent.PREREQ_CHECK),
        ),
        patch(
            "chat_service.core.llm_engine.build_context",
            new=AsyncMock(return_value=context_result),
        ),
        patch(
            "chat_service.core.llm_engine.ollama_service.get_embedding",
            new=embedding_mock,
        ),
    ):
        graph = build_graph(
            ollama_base_url="http://localhost:11434",
            ollama_model="test-model",
            tools=[],
            tool_executor=_make_tool_executor(),
            ollama_client=MagicMock(),
            neo4j_driver=MagicMock(),
            postgres_sessionmaker=MagicMock(),
        )
        await graph.ainvoke(_base_state(messages=[HumanMessage(content="prereqs for CSCI 3104")]))

    embedding_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_context_node_does_not_call_get_embedding_for_general_question() -> None:
    embedding_mock = AsyncMock(return_value=[0.1])
    context_result = MagicMock()
    context_result.text = ""

    llm_mock = MagicMock()
    llm_with_tools = MagicMock()
    llm_with_tools.ainvoke = AsyncMock(return_value=AIMessage(content="hello"))
    llm_mock.bind_tools = MagicMock(return_value=llm_with_tools)

    with (
        patch("chat_service.core.llm_engine.ChatOllama", return_value=llm_mock),
        patch(
            "chat_service.core.llm_engine.classify_intent",
            new=AsyncMock(return_value=Intent.GENERAL_QUESTION),
        ),
        patch(
            "chat_service.core.llm_engine.build_context",
            new=AsyncMock(return_value=context_result),
        ),
        patch(
            "chat_service.core.llm_engine.ollama_service.get_embedding",
            new=embedding_mock,
        ),
    ):
        graph = build_graph(
            ollama_base_url="http://localhost:11434",
            ollama_model="test-model",
            tools=[],
            tool_executor=_make_tool_executor(),
            ollama_client=MagicMock(),
            neo4j_driver=MagicMock(),
            postgres_sessionmaker=MagicMock(),
        )
        await graph.ainvoke(_base_state(messages=[HumanMessage(content="how are you?")]))

    embedding_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_context_node_handles_ollama_error_gracefully() -> None:
    """OllamaError from get_embedding must be swallowed; graph must still complete."""
    from chat_service.services.ollama_service import OllamaError

    context_result = MagicMock()
    context_result.text = ""

    llm_mock = MagicMock()
    llm_with_tools = MagicMock()
    llm_with_tools.ainvoke = AsyncMock(return_value=AIMessage(content="fallback response"))
    llm_mock.bind_tools = MagicMock(return_value=llm_with_tools)

    build_context_mock = AsyncMock(return_value=context_result)

    with (
        patch("chat_service.core.llm_engine.ChatOllama", return_value=llm_mock),
        patch(
            "chat_service.core.llm_engine.classify_intent",
            new=AsyncMock(return_value=Intent.COURSE_SEARCH),
        ),
        patch("chat_service.core.llm_engine.build_context", new=build_context_mock),
        patch(
            "chat_service.core.llm_engine.ollama_service.get_embedding",
            new=AsyncMock(side_effect=OllamaError("embedding service down")),
        ),
    ):
        graph = build_graph(
            ollama_base_url="http://localhost:11434",
            ollama_model="test-model",
            tools=[],
            tool_executor=_make_tool_executor(),
            ollama_client=MagicMock(),
            neo4j_driver=MagicMock(),
            postgres_sessionmaker=MagicMock(),
        )
        final_state = await graph.ainvoke(
            _base_state(messages=[HumanMessage(content="find ML courses")])
        )

    # Graph completes without error; build_context was still called (with None embedding).
    build_context_mock.assert_awaited_once()
    call_kwargs = build_context_mock.await_args.kwargs
    assert call_kwargs["query_embedding"] is None
    # No error set in final state.
    assert final_state.get("error") is None


# ═══════════════════════════════════════════════════════════════════════════
# 6. call_llm_node
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_call_llm_node_happy_path_returns_ai_message() -> None:
    ai_reply = AIMessage(content="Here are some courses.")

    async with _GraphCtx(llm_responses=[ai_reply]) as ctx:
        final_state = await ctx.graph.ainvoke(_base_state())

    # LLM was called exactly once.
    ctx.llm.ainvoke.assert_awaited_once()
    # The AI reply must be in the messages list.
    ai_msgs = [m for m in final_state["messages"] if isinstance(m, AIMessage)]
    assert any(m.content == "Here are some courses." for m in ai_msgs)


@pytest.mark.asyncio
async def test_call_llm_node_skips_llm_when_error_in_state() -> None:
    """If state.error is already set, the LLM node must be a no-op."""
    async with _GraphCtx() as ctx:
        # Inject a pre-existing error into the state before graph entry.
        final_state = await ctx.graph.ainvoke(_base_state(error="upstream failure"))

    # LLM should not be called.
    ctx.llm.ainvoke.assert_not_awaited()
    # Error must persist into final state.
    assert final_state.get("error") == "upstream failure"


@pytest.mark.asyncio
async def test_call_llm_node_exception_sets_error_state() -> None:
    """If ainvoke raises, the node must catch it and set state.error."""
    llm_mock = MagicMock()
    llm_with_tools = MagicMock()
    llm_with_tools.ainvoke = AsyncMock(side_effect=RuntimeError("Ollama crashed"))
    llm_mock.bind_tools = MagicMock(return_value=llm_with_tools)

    context_result = MagicMock()
    context_result.text = ""

    with (
        patch("chat_service.core.llm_engine.ChatOllama", return_value=llm_mock),
        patch(
            "chat_service.core.llm_engine.classify_intent",
            new=AsyncMock(return_value=Intent.GENERAL_QUESTION),
        ),
        patch(
            "chat_service.core.llm_engine.build_context",
            new=AsyncMock(return_value=context_result),
        ),
        patch(
            "chat_service.core.llm_engine.ollama_service.get_embedding",
            new=AsyncMock(return_value=[]),
        ),
    ):
        graph = build_graph(
            ollama_base_url="http://localhost:11434",
            ollama_model="test-model",
            tools=[],
            tool_executor=_make_tool_executor(),
            ollama_client=MagicMock(),
            neo4j_driver=MagicMock(),
            postgres_sessionmaker=MagicMock(),
        )
        final_state = await graph.ainvoke(_base_state())

    assert final_state.get("error") is not None
    assert "unavailable" in final_state["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# 7. tool_node
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tool_node_converts_tool_calls_to_tool_messages() -> None:
    """Each tool_call on the AIMessage must produce a ToolMessage in state."""
    tool_call = {
        "id": "call-abc",
        "name": "search_courses",
        "args": {"query": "machine learning"},
        "type": "tool_call",
    }
    first_response = AIMessage(content="", tool_calls=[tool_call])
    second_response = AIMessage(content="Here are the results.")

    executor = _make_tool_executor(
        execute_return={"result": [{"code": "CSCI 5622", "title": "ML"}]}
    )

    async with _GraphCtx(
        llm_responses=[first_response, second_response],
        tool_executor=executor,
    ) as ctx:
        final_state = await ctx.graph.ainvoke(_base_state())

    # ToolExecutor.execute was called once for the single tool call.
    executor.execute.assert_awaited_once()
    call_kwargs = executor.execute.await_args.kwargs
    assert call_kwargs["tool_name"] == "search_courses"
    assert call_kwargs["params"] == {"query": "machine learning"}

    # A ToolMessage with the correct tool_call_id and name was added to messages.
    tool_msgs = [m for m in final_state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) >= 1
    assert tool_msgs[0].tool_call_id == "call-abc"
    assert tool_msgs[0].name == "search_courses"


@pytest.mark.asyncio
async def test_tool_node_increments_call_count() -> None:
    """call_count in state must be incremented once per tool call."""
    tool_call = {
        "id": "call-1",
        "name": "lookup_course",
        "args": {"course_code": "CSCI 2270"},
        "type": "tool_call",
    }
    first_response = AIMessage(content="", tool_calls=[tool_call])
    second_response = AIMessage(content="Here is the course.")

    executor = _make_tool_executor(execute_return={"result": {"code": "CSCI 2270", "title": "DS"}})

    async with _GraphCtx(
        llm_responses=[first_response, second_response],
        tool_executor=executor,
    ) as ctx:
        final_state = await ctx.graph.ainvoke(_base_state(call_count=0))

    # After one tool call, call_count must be 1.
    assert final_state["call_count"] == 1


@pytest.mark.asyncio
async def test_tool_node_passes_user_id_to_executor() -> None:
    tool_call = {
        "id": "call-u",
        "name": "get_student_profile",
        "args": {},
        "type": "tool_call",
    }
    first_response = AIMessage(content="", tool_calls=[tool_call])
    second_response = AIMessage(content="Profile loaded.")

    executor = _make_tool_executor(execute_return={"result": {"user_id": 99}})

    async with _GraphCtx(
        llm_responses=[first_response, second_response],
        tool_executor=executor,
    ) as ctx:
        await ctx.graph.ainvoke(_base_state(user_id=99))

    call_kwargs = executor.execute.await_args.kwargs
    assert call_kwargs["user_id"] == 99


@pytest.mark.asyncio
async def test_tool_node_error_result_produces_error_tool_message() -> None:
    """When ToolExecutor returns {error: ...}, the ToolMessage content wraps it."""
    tool_call = {
        "id": "call-err",
        "name": "search_courses",
        "args": {"query": "bad query"},
        "type": "tool_call",
    }
    first_response = AIMessage(content="", tool_calls=[tool_call])
    second_response = AIMessage(content="I encountered an error.")

    executor = _make_tool_executor(execute_return={"error": "Course service unavailable"})

    async with _GraphCtx(
        llm_responses=[first_response, second_response],
        tool_executor=executor,
    ) as ctx:
        final_state = await ctx.graph.ainvoke(_base_state())

    tool_msgs = [m for m in final_state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) >= 1
    content = json.loads(tool_msgs[0].content)
    assert "error" in content
    assert content["error"] == "Course service unavailable"


@pytest.mark.asyncio
async def test_tool_node_passes_session_id_to_executor() -> None:
    tool_call = {
        "id": "call-s",
        "name": "lookup_course",
        "args": {"course_code": "CSCI 2270"},
        "type": "tool_call",
    }
    first_response = AIMessage(content="", tool_calls=[tool_call])
    second_response = AIMessage(content="Here you go.")

    executor = _make_tool_executor(execute_return={"result": {}})

    async with _GraphCtx(
        llm_responses=[first_response, second_response],
        tool_executor=executor,
    ) as ctx:
        await ctx.graph.ainvoke(_base_state(session_id="ws-session-42"))

    call_kwargs = executor.execute.await_args.kwargs
    assert call_kwargs["session_id"] == "ws-session-42"


# ═══════════════════════════════════════════════════════════════════════════
# 8. should_continue (routing)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_should_continue_error_routes_to_respond() -> None:
    """When state.error is set, routing must go directly to respond."""
    llm_mock = MagicMock()
    llm_with_tools = MagicMock()
    # LLM raises so error is set in state.
    llm_with_tools.ainvoke = AsyncMock(side_effect=RuntimeError("crash"))
    llm_mock.bind_tools = MagicMock(return_value=llm_with_tools)

    context_result = MagicMock()
    context_result.text = ""

    with (
        patch("chat_service.core.llm_engine.ChatOllama", return_value=llm_mock),
        patch(
            "chat_service.core.llm_engine.classify_intent",
            new=AsyncMock(return_value=Intent.GENERAL_QUESTION),
        ),
        patch(
            "chat_service.core.llm_engine.build_context",
            new=AsyncMock(return_value=context_result),
        ),
        patch(
            "chat_service.core.llm_engine.ollama_service.get_embedding",
            new=AsyncMock(return_value=[]),
        ),
    ):
        graph = build_graph(
            ollama_base_url="http://localhost:11434",
            ollama_model="test-model",
            tools=[],
            tool_executor=_make_tool_executor(),
            ollama_client=MagicMock(),
            neo4j_driver=MagicMock(),
            postgres_sessionmaker=MagicMock(),
        )
        final_state = await graph.ainvoke(_base_state())

    # Error is set and structured_data is empty (respond_node short-circuits).
    assert final_state.get("error") is not None
    assert final_state["structured_data"] == []


@pytest.mark.asyncio
async def test_should_continue_rate_limit_routes_to_respond() -> None:
    """When call_count >= MAX_TOOL_CALLS_PER_TURN, routing must go to respond."""
    # Provide a response with tool_calls — routing should still skip tool_node.
    tool_call = {
        "id": "call-rl",
        "name": "search_courses",
        "args": {"query": "AI"},
        "type": "tool_call",
    }
    ai_with_tool_calls = AIMessage(content="", tool_calls=[tool_call])
    executor = _make_tool_executor()

    async with _GraphCtx(
        llm_responses=[ai_with_tool_calls],
        tool_executor=executor,
    ) as ctx:
        # Pre-seed call_count to the limit so routing goes to respond.
        final_state = await ctx.graph.ainvoke(_base_state(call_count=MAX_TOOL_CALLS_PER_TURN))

    # Tool executor must NOT have been called.
    executor.execute.assert_not_awaited()
    # No ToolMessages were added.
    tool_msgs = [m for m in final_state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 0


@pytest.mark.asyncio
async def test_should_continue_ai_message_with_tool_calls_routes_to_tool_node() -> None:
    """AIMessage.tool_calls present → tool_node must be entered."""
    tool_call = {
        "id": "call-tc",
        "name": "lookup_course",
        "args": {"course_code": "CSCI 2270"},
        "type": "tool_call",
    }
    first_response = AIMessage(content="", tool_calls=[tool_call])
    second_response = AIMessage(content="Here is your course.")

    executor = _make_tool_executor(execute_return={"result": {"code": "CSCI 2270", "title": "DS"}})

    async with _GraphCtx(
        llm_responses=[first_response, second_response],
        tool_executor=executor,
    ) as ctx:
        await ctx.graph.ainvoke(_base_state())

    # ToolExecutor must have been called once.
    executor.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_should_continue_ai_message_without_tool_calls_routes_to_respond() -> None:
    """AIMessage without tool_calls → graph terminates at respond."""
    plain_response = AIMessage(content="No tools needed.")
    executor = _make_tool_executor()

    async with _GraphCtx(llm_responses=[plain_response], tool_executor=executor) as ctx:
        await ctx.graph.ainvoke(_base_state())

    # Tool executor must NOT have been called.
    executor.execute.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════
# 9. respond_node
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_respond_node_extracts_course_cards_from_tool_messages() -> None:
    """CourseCards from ToolMessages end up in final_state.structured_data."""
    courses = [
        {"code": "CSCI 5622", "title": "Machine Learning", "credits": "3"},
        {"code": "CSCI 5832", "title": "Natural Language Processing", "credits": "3"},
    ]
    tool_call = {
        "id": "call-sc",
        "name": "search_courses",
        "args": {"query": "NLP"},
        "type": "tool_call",
    }
    first_response = AIMessage(content="", tool_calls=[tool_call])
    second_response = AIMessage(content="Here are the courses.")

    executor = _make_tool_executor(execute_return={"result": courses})

    async with _GraphCtx(
        llm_responses=[first_response, second_response],
        tool_executor=executor,
    ) as ctx:
        final_state = await ctx.graph.ainvoke(_base_state())

    codes = [c["code"] for c in final_state["structured_data"]]
    assert "CSCI 5622" in codes
    assert "CSCI 5832" in codes


@pytest.mark.asyncio
async def test_respond_node_returns_empty_list_on_error_state() -> None:
    """When state.error is set, respond_node must return structured_data=[]."""
    async with _GraphCtx() as ctx:
        final_state = await ctx.graph.ainvoke(_base_state(error="something went wrong"))

    assert final_state["structured_data"] == []


@pytest.mark.asyncio
async def test_respond_node_empty_when_no_tool_calls() -> None:
    """If the LLM responds directly without tools, structured_data must be []."""
    plain_response = AIMessage(content="Just a plain text answer.")

    async with _GraphCtx(llm_responses=[plain_response]) as ctx:
        final_state = await ctx.graph.ainvoke(_base_state())

    assert final_state["structured_data"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 10. build_graph — smoke + tool-loop integration
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_build_graph_smoke_no_tool_calls() -> None:
    """Smoke test: a single plain LLM response completes the graph successfully."""
    executor = _make_tool_executor()

    async with _GraphCtx(
        llm_responses=[AIMessage(content="No tools needed, here is your answer.")],
        classify_intent_return=Intent.GENERAL_QUESTION,
        tool_executor=executor,
    ) as ctx:
        final_state = await ctx.graph.ainvoke(_base_state())

    # LLM was invoked exactly once.
    ctx.llm.ainvoke.assert_awaited_once()
    # No tool calls were made.
    executor.execute.assert_not_awaited()
    # Final messages list has the AI reply.
    ai_msgs = [m for m in final_state["messages"] if isinstance(m, AIMessage)]
    assert any("No tools needed" in m.content for m in ai_msgs)
    # structured_data is empty (no ToolMessages to parse).
    assert final_state["structured_data"] == []


@pytest.mark.asyncio
async def test_build_graph_tool_loop_two_llm_calls() -> None:
    """Tool loop: LLM calls a tool on first pass, then responds on second pass."""
    tool_call = {
        "id": "call-loop",
        "name": "search_courses",
        "args": {"query": "AI"},
        "type": "tool_call",
    }
    first_response = AIMessage(content="", tool_calls=[tool_call])
    second_response = AIMessage(content="Based on the results, here are AI courses.")

    executor = _make_tool_executor(
        execute_return={
            "result": [{"code": "CSCI 5622", "title": "Machine Learning", "credits": "3"}]
        }
    )

    async with _GraphCtx(
        llm_responses=[first_response, second_response],
        tool_executor=executor,
    ) as ctx:
        final_state = await ctx.graph.ainvoke(_base_state())

    # LLM was called twice.
    assert ctx.llm.ainvoke.await_count == 2
    # Tool executor was called once.
    executor.execute.assert_awaited_once()
    # CourseCard extracted from the ToolMessage.
    codes = [c["code"] for c in final_state["structured_data"]]
    assert "CSCI 5622" in codes


@pytest.mark.asyncio
async def test_build_graph_multiple_tool_calls_in_single_turn() -> None:
    """Multiple tool_calls in one AIMessage → executor called once per call."""
    tool_calls = [
        {
            "id": "call-a",
            "name": "search_courses",
            "args": {"query": "ML"},
            "type": "tool_call",
        },
        {
            "id": "call-b",
            "name": "lookup_course",
            "args": {"course_code": "CSCI 5622"},
            "type": "tool_call",
        },
    ]
    first_response = AIMessage(content="", tool_calls=tool_calls)
    second_response = AIMessage(content="Here is what I found.")

    executor = _make_tool_executor(
        execute_return={"result": {"code": "CSCI 5622", "title": "ML", "credits": "3"}}
    )

    async with _GraphCtx(
        llm_responses=[first_response, second_response],
        tool_executor=executor,
    ) as ctx:
        final_state = await ctx.graph.ainvoke(_base_state())

    # Executor was called twice (once per tool call in the first AIMessage).
    assert executor.execute.await_count == 2
    # call_count must reflect two calls.
    assert final_state["call_count"] == 2


@pytest.mark.asyncio
async def test_build_graph_context_text_stored_in_state() -> None:
    """context_text from build_context must be available in final state."""
    context_text = "<retrieved_context>CSCI 5622 description</retrieved_context>"

    async with _GraphCtx(
        build_context_text=context_text,
        classify_intent_return=Intent.COURSE_SEARCH,
    ) as ctx:
        final_state = await ctx.graph.ainvoke(_base_state())

    assert final_state["context_text"] == context_text


@pytest.mark.asyncio
async def test_tool_node_early_return_when_last_message_is_not_ai_message() -> None:
    """tool_node returns {} when the last message is not an AIMessage with tool_calls.

    This defensive branch (llm_engine.py line 292) is unreachable via the
    normal graph routing (should_continue guards the edge), but the closure
    is callable directly via graph.nodes['tool_node'].bound.afunc.

    Note: the ``bound.afunc`` access path is a LangGraph internal
    (``RunnableCallable``) validated against langgraph >=0.2.  If LangGraph
    changes its compiled-graph node wrapper, this test will need updating.
    """
    async with _GraphCtx() as ctx:
        tool_node_func = ctx.graph.nodes["tool_node"].bound.afunc
        state = _base_state(messages=[HumanMessage(content="hello")])
        result = await tool_node_func(state)

    assert result == {}
