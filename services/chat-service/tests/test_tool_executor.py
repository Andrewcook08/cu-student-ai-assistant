"""Unit tests for chat_service.core.tool_executor (CHAT-006 / CUAI-38).

Covers every acceptance criterion from the Jira ticket:

1. ``user_id`` in params is ALWAYS replaced with the JWT-authenticated value.
2. Invalid parameters raise ``ValidationError`` (caught and retried once).
3. 11th tool call in one turn returns a rate-limit error.
4. Every tool call is logged to ``tool_audit_log``.
5. Retry re-prompts the LLM with the error message.

Plus regression guards:
- 10th call in a turn is still allowed (off-by-one on the rate limit).
- ``user_id`` is stripped from ``parameters`` in the audit log row.
- Rogue/unknown fields the LLM hallucinates are dropped before invocation.
- The caller's params dict is never mutated (no leak of JWT user_id back
  into the LangChain message history).
- Tool exceptions other than ``ValidationError`` write a *flagged* audit
  row and return a non-retryable error.
- Audit-log write failures are swallowed so the successful tool result
  still reaches the caller (no duplicate ``save_decision`` rows on retry).
- One integration test uses real ``make_tools`` to guard against
  ``_tool_accepts_user_id`` silently breaking on a LangChain upgrade.

Mocks follow the same pattern as ``test_tools.py`` — AsyncMock for I/O,
MagicMock for async context managers — rather than fighting LangChain's
``BaseTool`` machinery with real ``@tool`` functions.  That keeps each
test focused on executor behaviour, not tool-construction plumbing.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from chat_service.core.tool_executor import (
    MAX_TOOL_CALLS_PER_TURN,
    RESULT_SUMMARY_MAX_CHARS,
    ToolExecutor,
)
from chat_service.core.tools import make_tools
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ValidationError
from shared.models import ToolAuditLog

# ─── Fakes ───────────────────────────────────────────────────────────────


def _fake_tool(
    name: str,
    *,
    fields: list[str] | None = None,
    accepts_user_id: bool = False,
    ainvoke_return: Any = None,
    ainvoke_raises: BaseException | None = None,
) -> MagicMock:
    """Build a minimal stand-in for a LangChain ``BaseTool``.

    Only the attributes the executor actually touches are stubbed:
    ``get_input_schema().model_fields`` (for user_id detection AND parameter
    whitelisting) and ``ainvoke`` (for invocation).

    ``fields`` declares the tool's full input schema — the executor will
    drop any params outside this set before invoking.  Pass the LLM-visible
    parameters here; ``accepts_user_id=True`` additionally adds ``user_id``
    to simulate an ``InjectedToolArg`` field.

    Using ``MagicMock(spec=BaseTool)`` catches any accidental coupling to
    other ``BaseTool`` members.
    """
    tool = MagicMock(spec=BaseTool)
    tool.name = name

    declared = list(fields or [])
    if accepts_user_id:
        declared.append("user_id")
    schema = MagicMock()
    schema.model_fields = {f: object() for f in declared}
    tool.get_input_schema = MagicMock(return_value=schema)

    if ainvoke_raises is not None:
        tool.ainvoke = AsyncMock(side_effect=ainvoke_raises)
    else:
        tool.ainvoke = AsyncMock(return_value=ainvoke_return)

    return tool


def _make_sessionmaker() -> tuple[MagicMock, MagicMock]:
    """Build a mock ``async_sessionmaker`` + its inner session.

    Returns ``(sessionmaker, session)`` — the session is the same object
    the executor will see inside ``async with sessionmaker() as session:``,
    so tests can assert on ``session.add`` and ``session.commit`` directly.
    """
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)

    sessionmaker = MagicMock(return_value=ctx)
    return sessionmaker, session


def _make_validation_error() -> ValidationError:
    """Build a real ``pydantic.ValidationError`` — it can't be instantiated
    directly, so we trigger one via a trivial throwaway model."""

    class _M(BaseModel):
        x: int

    try:
        _M(x="not-an-int")
    except ValidationError as exc:
        return exc
    raise AssertionError("unreachable — Pydantic must raise")  # pragma: no cover


# ─── Construction ────────────────────────────────────────────────────────


def test_user_id_tools_detected_at_construction() -> None:
    """Tools whose input schema declares user_id are recognised up front."""
    profile_tool = _fake_tool("get_student_profile", accepts_user_id=True)
    search_tool = _fake_tool("search_courses", fields=["query"])
    sessionmaker, _ = _make_sessionmaker()

    executor = ToolExecutor(
        tool_registry={"get_student_profile": profile_tool, "search_courses": search_tool},
        postgres_sessionmaker=sessionmaker,
    )

    assert executor._user_id_tools == frozenset({"get_student_profile"})


# ─── AC 1: user_id override ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_supplied_user_id_is_overridden_with_jwt_value() -> None:
    """The LLM forges user_id=999; the executor stomps it with the JWT value."""
    tool = _fake_tool("get_student_profile", accepts_user_id=True, ainvoke_return={"ok": True})
    sessionmaker, _ = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"get_student_profile": tool}, postgres_sessionmaker=sessionmaker
    )

    await executor.execute(
        "get_student_profile",
        {"user_id": "999"},  # attacker-supplied
        user_id=42,
        call_count=1,
    )

    tool.ainvoke.assert_awaited_once_with({"user_id": "42"})


@pytest.mark.asyncio
async def test_user_id_injected_when_llm_omits_it() -> None:
    """For an InjectedToolArg tool the LLM omits user_id; executor supplies it."""
    tool = _fake_tool(
        "save_decision",
        fields=["course_code", "decision_type", "notes"],
        accepts_user_id=True,
        ainvoke_return={"id": 1},
    )
    sessionmaker, _ = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"save_decision": tool}, postgres_sessionmaker=sessionmaker
    )

    await executor.execute(
        "save_decision",
        {"course_code": "CSCI 2270", "decision_type": "planned"},
        user_id=42,
        call_count=1,
    )

    tool.ainvoke.assert_awaited_once_with(
        {"course_code": "CSCI 2270", "decision_type": "planned", "user_id": "42"}
    )


@pytest.mark.asyncio
async def test_rogue_user_id_on_tool_without_user_id_is_stripped() -> None:
    """LLM attaches user_id to search_courses — executor drops it."""
    tool = _fake_tool("search_courses", fields=["query"], ainvoke_return=[])
    sessionmaker, _ = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"search_courses": tool}, postgres_sessionmaker=sessionmaker
    )

    await executor.execute(
        "search_courses",
        {"query": "AI", "user_id": "hacker"},
        user_id=42,
        call_count=1,
    )

    tool.ainvoke.assert_awaited_once_with({"query": "AI"})


# ─── AC 2 + 5: ValidationError → retry-eligible error ───────────────────


@pytest.mark.asyncio
async def test_validation_error_returns_retry_payload_with_error_message() -> None:
    """Bad LLM params trigger a retry signal carrying the validator's message."""
    err = _make_validation_error()
    tool = _fake_tool("lookup_course", fields=["course_code"], ainvoke_raises=err)
    sessionmaker, session = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"lookup_course": tool}, postgres_sessionmaker=sessionmaker
    )

    result = await executor.execute(
        "lookup_course", {"course_code": 12345}, user_id=42, call_count=1
    )

    assert result.get("retry") is True
    assert "Invalid parameters for lookup_course" in result["error"]
    # The retry payload must include the validator's message so the LangGraph
    # caller can re-prompt the LLM with concrete corrective feedback.
    assert "x" in result["error"] or "int" in result["error"]
    # Validation failure means NO audit row and NO successful result key.
    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    assert "result" not in result


# ─── AC 3: rate limiting ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_eleventh_call_in_turn_is_rate_limited() -> None:
    """call_count == 11 (i.e. the 11th call) is refused without invoking."""
    tool = _fake_tool("search_courses", fields=["query"])
    sessionmaker, session = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"search_courses": tool}, postgres_sessionmaker=sessionmaker
    )

    result = await executor.execute("search_courses", {"query": "AI"}, user_id=42, call_count=11)

    assert "Rate limit exceeded" in result["error"]
    assert result.get("retry") is not True
    tool.ainvoke.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_tenth_call_still_succeeds() -> None:
    """Off-by-one guard: call_count == 10 (the 10th call) must still run."""
    tool = _fake_tool("search_courses", fields=["query"], ainvoke_return=["hit"])
    sessionmaker, _ = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"search_courses": tool}, postgres_sessionmaker=sessionmaker
    )

    result = await executor.execute(
        "search_courses",
        {"query": "AI"},
        user_id=42,
        call_count=MAX_TOOL_CALLS_PER_TURN,  # == 10
    )

    assert result == {"result": ["hit"]}
    tool.ainvoke.assert_awaited_once()


# ─── AC 4: audit logging ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_successful_call_writes_audit_log_row() -> None:
    """Every successful invocation persists a ``ToolAuditLog`` row."""
    tool = _fake_tool(
        "lookup_course",
        fields=["course_code"],
        ainvoke_return={"code": "CSCI 2270", "title": "Data Structures"},
    )
    sessionmaker, session = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"lookup_course": tool}, postgres_sessionmaker=sessionmaker
    )

    await executor.execute(
        "lookup_course",
        {"course_code": "CSCI 2270"},
        user_id=42,
        call_count=1,
        session_id="ws-abc",
    )

    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    row = session.add.call_args.args[0]
    assert isinstance(row, ToolAuditLog)
    assert row.user_id == 42
    assert row.session_id == "ws-abc"
    assert row.tool_name == "lookup_course"
    assert row.parameters == {"course_code": "CSCI 2270"}
    assert row.result_summary is not None
    assert "CSCI 2270" in row.result_summary


@pytest.mark.asyncio
async def test_audit_log_parameters_never_contain_user_id() -> None:
    """user_id is on its own column; it must not be duplicated into parameters."""
    tool = _fake_tool(
        "save_decision",
        fields=["course_code", "decision_type", "notes"],
        accepts_user_id=True,
        ainvoke_return={"id": 1},
    )
    sessionmaker, session = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"save_decision": tool}, postgres_sessionmaker=sessionmaker
    )

    await executor.execute(
        "save_decision",
        {"course_code": "CSCI 2270", "decision_type": "planned"},
        user_id=42,
        call_count=1,
    )

    row = session.add.call_args.args[0]
    assert row.user_id == 42
    assert "user_id" not in row.parameters
    assert row.parameters == {"course_code": "CSCI 2270", "decision_type": "planned"}


@pytest.mark.asyncio
async def test_audit_log_result_summary_is_truncated() -> None:
    """Large tool results are truncated to RESULT_SUMMARY_MAX_CHARS in the log."""
    huge = {"blob": "x" * 5_000}
    tool = _fake_tool("search_courses", fields=["query"], ainvoke_return=huge)
    sessionmaker, session = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"search_courses": tool}, postgres_sessionmaker=sessionmaker
    )

    await executor.execute("search_courses", {"query": "AI"}, user_id=42, call_count=1)

    row = session.add.call_args.args[0]
    assert row.result_summary is not None
    assert len(row.result_summary) == RESULT_SUMMARY_MAX_CHARS


@pytest.mark.asyncio
async def test_validation_error_does_not_write_audit_log() -> None:
    """Failed invocations must not leave audit rows — only successes count."""
    tool = _fake_tool(
        "lookup_course", fields=["course_code"], ainvoke_raises=_make_validation_error()
    )
    sessionmaker, session = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"lookup_course": tool}, postgres_sessionmaker=sessionmaker
    )

    await executor.execute("lookup_course", {"course_code": 1}, user_id=42, call_count=1)

    session.add.assert_not_called()
    session.commit.assert_not_awaited()


# ─── Unknown tool dispatch ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_tool_returns_error_without_touching_db() -> None:
    """Unknown tool name is a hard error and no audit row is written."""
    sessionmaker, session = _make_sessionmaker()
    executor = ToolExecutor(tool_registry={}, postgres_sessionmaker=sessionmaker)

    result = await executor.execute("nonexistent", {}, user_id=42, call_count=1)

    assert "Unknown tool" in result["error"]
    assert result.get("retry") is not True
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


# ─── Happy path sanity ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_successful_call_returns_raw_tool_result_under_result_key() -> None:
    payload = {"code": "CSCI 2270", "title": "Data Structures"}
    tool = _fake_tool("lookup_course", fields=["course_code"], ainvoke_return=payload)
    sessionmaker, _ = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"lookup_course": tool}, postgres_sessionmaker=sessionmaker
    )

    result = await executor.execute(
        "lookup_course", {"course_code": "CSCI 2270"}, user_id=42, call_count=1
    )

    assert result == {"result": payload}


# ─── Parameter whitelisting ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_params_are_stripped_before_invocation() -> None:
    """LLM hallucinates ``bogus`` — it never reaches the tool function."""
    tool = _fake_tool("search_courses", fields=["query"], ainvoke_return=[])
    sessionmaker, _ = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"search_courses": tool}, postgres_sessionmaker=sessionmaker
    )

    await executor.execute(
        "search_courses",
        {"query": "AI", "bogus": "drop table"},
        user_id=42,
        call_count=1,
    )

    tool.ainvoke.assert_awaited_once_with({"query": "AI"})


@pytest.mark.asyncio
async def test_unknown_params_are_stripped_from_audit_log() -> None:
    """Whitelisted out of the invocation AND out of the audit row."""
    tool = _fake_tool("search_courses", fields=["query"], ainvoke_return=[])
    sessionmaker, session = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"search_courses": tool}, postgres_sessionmaker=sessionmaker
    )

    await executor.execute(
        "search_courses",
        {"query": "AI", "bogus": "nope"},
        user_id=42,
        call_count=1,
    )

    row = session.add.call_args.args[0]
    assert row.parameters == {"query": "AI"}
    assert "bogus" not in row.parameters


# ─── Params-dict immutability ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_caller_params_dict_is_not_mutated() -> None:
    """The executor must copy the params dict before sanitising.

    LangChain's message history holds a reference to ``tool_call.args``;
    mutating it in place would leak the internal JWT user_id back into
    the prompt context on the next turn.
    """
    tool = _fake_tool(
        "save_decision",
        fields=["course_code", "decision_type", "notes"],
        accepts_user_id=True,
        ainvoke_return={"id": 1},
    )
    sessionmaker, _ = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"save_decision": tool}, postgres_sessionmaker=sessionmaker
    )

    original = {"course_code": "CSCI 2270", "decision_type": "planned", "user_id": "999"}
    snapshot = dict(original)

    await executor.execute("save_decision", original, user_id=42, call_count=1)

    # The caller still sees what it passed in — the executor worked on a copy.
    assert original == snapshot
    assert original["user_id"] == "999"  # attacker-supplied value preserved for caller


# ─── Tool exceptions (non-ValidationError) ──────────────────────────────


@pytest.mark.asyncio
async def test_tool_exception_writes_flagged_audit_row() -> None:
    """A Neo4jError / TimeoutError from a tool is recorded with flagged=True."""
    tool = _fake_tool(
        "search_courses",
        fields=["query"],
        ainvoke_raises=RuntimeError("upstream Neo4j timeout"),
    )
    sessionmaker, session = _make_sessionmaker()
    executor = ToolExecutor(
        tool_registry={"search_courses": tool}, postgres_sessionmaker=sessionmaker
    )

    result = await executor.execute(
        "search_courses", {"query": "AI"}, user_id=42, call_count=1, session_id="ws-1"
    )

    # Non-retryable: the LLM can't fix a downstream Neo4j outage.
    assert "upstream Neo4j timeout" in result["error"]
    assert result.get("retry") is not True
    assert "result" not in result

    # Audit row written with flagged=True so anomaly detection can find it.
    session.add.assert_called_once()
    row = session.add.call_args.args[0]
    assert isinstance(row, ToolAuditLog)
    assert row.flagged is True
    assert row.tool_name == "search_courses"
    assert row.user_id == 42
    assert row.session_id == "ws-1"
    assert row.parameters == {"query": "AI"}
    assert row.result_summary is not None
    assert "RuntimeError" in row.result_summary
    assert "upstream Neo4j timeout" in row.result_summary


# ─── Audit-log failure handling ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_commit_failure_does_not_swallow_successful_result() -> None:
    """If the audit-log write fails, the tool result still reaches the caller.

    Critical for ``save_decision``: the tool has already run (possibly
    mutating DB state).  Raising the audit failure would either lose the
    result or trigger a LangGraph retry that duplicates the decision row.
    """
    payload = {"id": 1, "course_code": "CSCI 2270"}
    tool = _fake_tool(
        "save_decision",
        fields=["course_code", "decision_type", "notes"],
        accepts_user_id=True,
        ainvoke_return=payload,
    )

    # Sessionmaker whose commit blows up after the tool has already run.
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock(side_effect=RuntimeError("audit DB down"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    sessionmaker = MagicMock(return_value=ctx)

    executor = ToolExecutor(
        tool_registry={"save_decision": tool}, postgres_sessionmaker=sessionmaker
    )

    result = await executor.execute(
        "save_decision",
        {"course_code": "CSCI 2270", "decision_type": "planned"},
        user_id=42,
        call_count=1,
    )

    # Tool result is returned successfully even though audit failed.
    assert result == {"result": payload}
    # And the tool was called — the caller is not about to retry.
    tool.ainvoke.assert_awaited_once()


# ─── Integration test: real make_tools + real LangChain ─────────────────


@pytest.mark.asyncio
async def test_integration_real_tools_user_id_override_via_make_tools() -> None:
    """Regression guard against LangChain upgrades breaking user_id detection.

    Builds a real ``ToolSet`` via ``make_tools`` with mocked service layers,
    then runs the executor against it.  If a future LangChain release changes
    how ``InjectedToolArg`` fields appear in ``get_input_schema().model_fields``,
    the fake-tool tests above might still pass but this one would fail —
    surfacing the silent breakage in CI.
    """
    expected_profile = {"user_id": 42, "program": "CS", "completed": [], "decisions": []}

    sessionmaker, session = _make_sessionmaker()

    with patch(
        "chat_service.core.tools.postgres_service.get_student_data",
        new=AsyncMock(return_value=expected_profile),
    ) as mock_get:
        toolset = make_tools(
            neo4j_driver=MagicMock(),
            postgres_sessionmaker=MagicMock(return_value=_make_sessionmaker()[0]()),
            ollama_client=MagicMock(),
        )
        executor = ToolExecutor(tool_registry=toolset.registry, postgres_sessionmaker=sessionmaker)

        # The executor must recognise get_student_profile as a user_id-bearing
        # tool even though user_id is InjectedToolArg and absent from the
        # LLM-visible tool_call_schema.
        assert "get_student_profile" in executor._user_id_tools
        assert "save_decision" in executor._user_id_tools
        # And must NOT mark tools without user_id as user_id-bearing.
        assert "search_courses" not in executor._user_id_tools
        assert "lookup_course" not in executor._user_id_tools

        # LLM forges user_id=999 — executor stomps it with JWT user_id=42,
        # which then reaches postgres_service.get_student_data as int(42).
        result = await executor.execute(
            "get_student_profile",
            {"user_id": "999"},
            user_id=42,
            call_count=1,
        )

    assert result == {"result": expected_profile}
    mock_get.assert_awaited_once()
    # The override landed: get_student_data was called with user_id=42, not 999.
    await_args = mock_get.await_args
    assert await_args is not None
    assert await_args.kwargs["user_id"] == 42
