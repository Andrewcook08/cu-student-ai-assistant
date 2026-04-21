"""Unit tests for chat_service.core.tools (CHAT-005 / CUAI-37).

All eight tools are tested against mocked service layers — no live database,
Neo4j, or LLM instance is required.  The fixture pattern mirrors
``test_postgres_service.py`` and ``test_neo4j_service.py``: AsyncMock for
I/O calls, MagicMock for context managers.

Critical guarantees that are load-bearing for security:
- ``user_id`` is NOT present in ``get_student_profile.tool_call_schema`` or
  ``save_decision.tool_call_schema`` (the LLM cannot forge it).
- ``user_id`` IS injectable at invoke time and reaches the service layer as
  an int (the JWT subject is always an int-as-str from the auth middleware).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from chat_service.core.tools import ToolSet, make_tools
from langchain_core.tools import BaseTool

# ─── Shared fixtures ─────────────────────────────────────────────────────


def _make_neo4j_driver() -> MagicMock:
    """Minimal mock AsyncDriver — session() returns a no-op async CM."""
    driver = MagicMock()
    # Individual tests override session().run as needed.
    return driver


def _make_postgres_sessionmaker(
    session: MagicMock | None = None,
) -> MagicMock:
    """Build a mock ``async_sessionmaker`` that yields *session* on entry.

    Returns a callable mock so ``postgres_sessionmaker()`` returns an async
    context manager that yields the supplied session.
    """
    if session is None:
        session = MagicMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)

    sessionmaker = MagicMock(return_value=ctx)
    return sessionmaker


def _make_ollama_client() -> MagicMock:
    """Minimal mock httpx.AsyncClient."""
    return MagicMock()


def _default_toolset() -> ToolSet:
    """Return a ToolSet with fully mocked (but unconfigured) service handles."""
    return make_tools(
        neo4j_driver=_make_neo4j_driver(),
        postgres_sessionmaker=_make_postgres_sessionmaker(),
        ollama_client=_make_ollama_client(),
    )


# ─── ToolSet shape ───────────────────────────────────────────────────────


def test_make_tools_returns_exactly_eight_tools() -> None:
    toolset = _default_toolset()
    assert len(toolset.tools) == 8


def test_make_tools_registry_has_expected_names() -> None:
    toolset = _default_toolset()
    expected = {
        "search_courses",
        "lookup_course",
        "check_prerequisites",
        "get_degree_requirements",
        "get_student_profile",
        "find_schedule_conflicts",
        "save_decision",
        "remove_decision",
    }
    assert set(toolset.registry.keys()) == expected


def test_all_tools_are_base_tool_subclasses() -> None:
    toolset = _default_toolset()
    for t in toolset.tools:
        assert isinstance(t, BaseTool), f"{t.name!r} is not a BaseTool subclass"


def test_tools_list_and_registry_are_consistent() -> None:
    """Every tool in tools[] must appear in registry under its own name."""
    toolset = _default_toolset()
    for t in toolset.tools:
        assert toolset.registry[t.name] is t


# ─── InjectedToolArg safety guarantees ──────────────────────────────────


def _tool_call_schema_props(tool: BaseTool) -> dict[str, Any]:
    """Return the tool_call_schema properties dict, normalizing Pydantic vs raw dict."""
    schema_obj = tool.tool_call_schema
    if isinstance(schema_obj, dict):
        props: dict[str, Any] = schema_obj.get("properties", {})
        return props
    full: dict[str, Any] = schema_obj.model_json_schema()
    result: dict[str, Any] = full.get("properties", {})
    return result


def test_get_student_profile_user_id_not_in_tool_call_schema() -> None:
    """user_id must be absent from the schema the LLM sees."""
    toolset = _default_toolset()
    props = _tool_call_schema_props(toolset.registry["get_student_profile"])
    assert "user_id" not in props, (
        "user_id appeared in get_student_profile's tool_call_schema — "
        "the LLM could forge it, which breaks the trust boundary."
    )


def test_save_decision_user_id_not_in_tool_call_schema() -> None:
    """user_id must be absent from the schema the LLM sees."""
    toolset = _default_toolset()
    props = _tool_call_schema_props(toolset.registry["save_decision"])
    assert "user_id" not in props, (
        "user_id appeared in save_decision's tool_call_schema — "
        "the LLM could forge it, which breaks the trust boundary."
    )


def test_save_decision_llm_visible_params_are_correct() -> None:
    """LLM-visible params are exactly: course_code, decision_type, notes."""
    toolset = _default_toolset()
    props = set(_tool_call_schema_props(toolset.registry["save_decision"]).keys())
    assert props == {"course_code", "decision_type", "notes"}


# ─── get_student_profile ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_student_profile_injects_user_id_as_int() -> None:
    """user_id string '42' is cast to int 42 before reaching get_student_data."""
    expected_profile = {"user_id": 42, "program": "CS", "completed": [], "decisions": []}
    session = MagicMock()

    with patch(
        "chat_service.core.tools.postgres_service.get_student_data",
        new=AsyncMock(return_value=expected_profile),
    ) as mock_get:
        toolset = make_tools(
            neo4j_driver=_make_neo4j_driver(),
            postgres_sessionmaker=_make_postgres_sessionmaker(session),
            ollama_client=_make_ollama_client(),
        )
        tool = toolset.registry["get_student_profile"]
        result = await tool.ainvoke({"user_id": "42"})

    mock_get.assert_awaited_once_with(session, user_id=42)
    assert result == expected_profile


@pytest.mark.asyncio
async def test_get_student_profile_returns_plain_dict() -> None:
    expected: dict[str, Any] = {"user_id": 1, "program": None, "completed": [], "decisions": []}
    session = MagicMock()

    with patch(
        "chat_service.core.tools.postgres_service.get_student_data",
        new=AsyncMock(return_value=expected),
    ):
        toolset = make_tools(
            neo4j_driver=_make_neo4j_driver(),
            postgres_sessionmaker=_make_postgres_sessionmaker(session),
            ollama_client=_make_ollama_client(),
        )
        result = await toolset.registry["get_student_profile"].ainvoke({"user_id": "1"})

    assert isinstance(result, dict)


# ─── lookup_course ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lookup_course_returns_course_dict_on_hit() -> None:
    course_data: dict[str, Any] = {
        "code": "CSCI 2270",
        "title": "Data Structures",
        "credits": "4",
        "description": "Fundamental data structures.",
        "instruction_mode": "In-Person",
        "campus": "Boulder",
        "prerequisites_raw": "CSCI 1300",
        "topic_titles": None,
        "attributes": [],
        "sections": [],
    }
    session = MagicMock()

    with patch(
        "chat_service.core.tools.postgres_service.lookup_course",
        new=AsyncMock(return_value=course_data),
    ) as mock_lookup:
        toolset = make_tools(
            neo4j_driver=_make_neo4j_driver(),
            postgres_sessionmaker=_make_postgres_sessionmaker(session),
            ollama_client=_make_ollama_client(),
        )
        result = await toolset.registry["lookup_course"].ainvoke({"course_code": "CSCI 2270"})

    mock_lookup.assert_awaited_once_with(session, course_code="CSCI 2270")
    # Tool trims the result for LLM context efficiency
    assert result["code"] == "CSCI 2270"
    assert result["title"] == "Data Structures"
    assert result["credits"] == "4"
    assert result["prerequisites_raw"] == "CSCI 1300"
    assert result["instruction_mode"] == "In-Person"
    assert result["total_sections"] == 0
    assert result["open_sections"] == 0
    # Full fields like description, campus, attributes are trimmed out
    assert "description" not in result
    assert "campus" not in result


@pytest.mark.asyncio
async def test_lookup_course_not_found_returns_error_dict() -> None:
    """postgres_service.lookup_course returns None → tool returns error dict."""
    session = MagicMock()

    with patch(
        "chat_service.core.tools.postgres_service.lookup_course",
        new=AsyncMock(return_value=None),
    ):
        toolset = make_tools(
            neo4j_driver=_make_neo4j_driver(),
            postgres_sessionmaker=_make_postgres_sessionmaker(session),
            ollama_client=_make_ollama_client(),
        )
        result = await toolset.registry["lookup_course"].ainvoke({"course_code": "XXXX 9999"})

    assert result == {"error": "Course not found", "course_code": "XXXX 9999"}


# ─── SYN-033: lookup_course error-path sanitization ──────────────────────


@pytest.mark.asyncio
async def test_lookup_course_long_code_truncated_in_error() -> None:
    """A course_code longer than 20 chars must be truncated to 20 in the error dict.

    Prevents the LLM-controlled input from being reflected at arbitrary length
    in downstream responses or logs.
    """
    long_code = "ABCDEFGHIJ1234567890EXTRA30"  # 27 chars of valid [A-Z0-9] characters
    session = MagicMock()

    with patch(
        "chat_service.core.tools.postgres_service.lookup_course",
        new=AsyncMock(return_value=None),
    ):
        toolset = make_tools(
            neo4j_driver=_make_neo4j_driver(),
            postgres_sessionmaker=_make_postgres_sessionmaker(session),
            ollama_client=_make_ollama_client(),
        )
        result = await toolset.registry["lookup_course"].ainvoke({"course_code": long_code})

    reflected = result["course_code"]
    assert len(reflected) <= 20, (
        f"Reflected course_code has {len(reflected)} chars — expected ≤20 after truncation"
    )
    assert reflected == long_code[:20], (
        f"Reflected code {reflected!r} is not the first 20 chars of the input"
    )


@pytest.mark.asyncio
async def test_lookup_course_special_chars_stripped_in_error() -> None:
    """Special characters in course_code must be stripped before appearing in the error dict.

    Ensures that an angle-bracket injection payload cannot be reflected verbatim.
    Valid [A-Z0-9 ] characters (uppercase + digits + space) must survive the filter
    while HTML/script special chars are removed.

    Input: "<b>CSCI 1300" — angle-bracket tag is stripped, leaving "BCSCI 1300"
    after uppercasing.  The safe course code fragment "CSCI 1300" is present in
    the 20-char window and must appear in the reflected value.
    """
    # "<b>CSCI 1300" → upper: "<B>CSCI 1300" → strip non-[A-Z0-9 ]: "BCSCI 1300"
    raw_input = "<b>CSCI 1300"
    session = MagicMock()

    with patch(
        "chat_service.core.tools.postgres_service.lookup_course",
        new=AsyncMock(return_value=None),
    ):
        toolset = make_tools(
            neo4j_driver=_make_neo4j_driver(),
            postgres_sessionmaker=_make_postgres_sessionmaker(session),
            ollama_client=_make_ollama_client(),
        )
        result = await toolset.registry["lookup_course"].ainvoke({"course_code": raw_input})

    reflected = result["course_code"]

    # Dangerous characters must be absent.
    for bad_char in ("<", ">", "(", ")", "/", '"'):
        assert bad_char not in reflected, (
            f"Dangerous character {bad_char!r} survived sanitization in {reflected!r}"
        )
    # Lowercase letters must be absent (uppercased then filtered).
    assert reflected == reflected.upper(), f"Lowercase chars survived in {reflected!r}"

    # Safe alphanumeric content must survive the filter.
    assert "CSCI 1300" in reflected, (
        f"Expected 'CSCI 1300' to survive sanitization, got {reflected!r}"
    )


# ─── check_prerequisites ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_prerequisites_delegates_to_neo4j() -> None:
    expected: dict[str, Any] = {
        "course": {"code": "CSCI 3104", "title": "Algorithms"},
        "edges": [
            {
                "from": "CSCI 3104",
                "to": "CSCI 2270",
                "type": "REQUIRED",
                "min_grade": "C-",
                "raw_text": "CSCI 2270",
            }
        ],
    }

    with patch(
        "chat_service.core.tools.neo4j_service.get_prerequisite_chain",
        new=AsyncMock(return_value=expected),
    ) as mock_prereq:
        toolset = make_tools(
            neo4j_driver=_make_neo4j_driver(),
            postgres_sessionmaker=_make_postgres_sessionmaker(),
            ollama_client=_make_ollama_client(),
        )
        result = await toolset.registry["check_prerequisites"].ainvoke({"course_code": "CSCI 3104"})

    mock_prereq.assert_awaited_once()
    assert result == expected


# ─── get_degree_requirements ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_degree_requirements_delegates_to_neo4j() -> None:
    expected: dict[str, Any] = {
        "program": {
            "name": "Computer Science - BA",
            "type": "Bachelor of Arts",
            "total_credits": "120",
        },
        "requirements": [],
    }

    with patch(
        "chat_service.core.tools.neo4j_service.get_degree_requirements",
        new=AsyncMock(return_value=expected),
    ) as mock_req:
        toolset = make_tools(
            neo4j_driver=_make_neo4j_driver(),
            postgres_sessionmaker=_make_postgres_sessionmaker(),
            ollama_client=_make_ollama_client(),
        )
        result = await toolset.registry["get_degree_requirements"].ainvoke(
            {"program": "Computer Science - BA"}
        )

    mock_req.assert_awaited_once()
    assert result == expected


# ─── find_schedule_conflicts ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_schedule_conflicts_delegates_to_postgres() -> None:
    conflicts: list[dict[str, Any]] = [
        {
            "course_a": "CSCI 2270",
            "crn_a": "30002",
            "meets_a": "MWF 10-10:50a",
            "course_b": "CSCI 2400",
            "crn_b": "40001",
            "meets_b": "MWF 10-10:50a",
            "overlap_days": ["F", "M", "W"],
        }
    ]
    session = MagicMock()

    with patch(
        "chat_service.core.tools.postgres_service.get_schedule_conflicts",
        new=AsyncMock(return_value=conflicts),
    ) as mock_conflicts:
        toolset = make_tools(
            neo4j_driver=_make_neo4j_driver(),
            postgres_sessionmaker=_make_postgres_sessionmaker(session),
            ollama_client=_make_ollama_client(),
        )
        result = await toolset.registry["find_schedule_conflicts"].ainvoke(
            {"course_codes": ["CSCI 2270", "CSCI 2400"]}
        )

    mock_conflicts.assert_awaited_once_with(session, course_codes=["CSCI 2270", "CSCI 2400"])
    assert result == conflicts
    assert isinstance(result, list)


# ─── save_decision ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_decision_injects_user_id_as_int() -> None:
    """user_id '7' is cast to int 7 and passed to save_student_decision."""
    expected: dict[str, Any] = {
        "id": 1,
        "user_id": 7,
        "course_code": "CSCI 2270",
        "decision_type": "planned",
        "notes": None,
        "created_at": "2026-04-07T00:00:00",
    }
    session = MagicMock()

    with patch(
        "chat_service.core.tools.postgres_service.save_student_decision",
        new=AsyncMock(return_value=expected),
    ) as mock_save:
        toolset = make_tools(
            neo4j_driver=_make_neo4j_driver(),
            postgres_sessionmaker=_make_postgres_sessionmaker(session),
            ollama_client=_make_ollama_client(),
        )
        tool = toolset.registry["save_decision"]
        result = await tool.ainvoke(
            {
                "course_code": "CSCI 2270",
                "decision_type": "planned",
                "user_id": "7",
            }
        )

    mock_save.assert_awaited_once_with(
        session,
        user_id=7,
        course_code="CSCI 2270",
        decision_type="planned",
        notes=None,
    )
    assert result == expected


@pytest.mark.asyncio
async def test_save_decision_passes_notes_when_provided() -> None:
    expected: dict[str, Any] = {
        "id": 2,
        "user_id": 3,
        "course_code": "MATH 2400",
        "decision_type": "interested",
        "notes": "Need to check prereqs first",
        "created_at": "2026-04-07T00:00:00",
    }
    session = MagicMock()

    with patch(
        "chat_service.core.tools.postgres_service.save_student_decision",
        new=AsyncMock(return_value=expected),
    ) as mock_save:
        toolset = make_tools(
            neo4j_driver=_make_neo4j_driver(),
            postgres_sessionmaker=_make_postgres_sessionmaker(session),
            ollama_client=_make_ollama_client(),
        )
        await toolset.registry["save_decision"].ainvoke(
            {
                "course_code": "MATH 2400",
                "decision_type": "interested",
                "notes": "Need to check prereqs first",
                "user_id": "3",
            }
        )

    mock_save.assert_awaited_once_with(
        session,
        user_id=3,
        course_code="MATH 2400",
        decision_type="interested",
        notes="Need to check prereqs first",
    )


# ─── search_courses ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_courses_calls_embedding_then_vector_search() -> None:
    """Embedding is obtained first, then passed to vector_search."""
    fake_embedding = [0.1, 0.2, 0.3]
    fake_results: list[dict[str, Any]] = [
        {
            "code": "CSCI 5622",
            "title": "Machine Learning",
            "credits": "3",
            "description": "",
            "instruction_mode": "In-Person",
            "score": 0.95,
        },
        {
            "code": "CSCI 4830",
            "title": "Special Topics: ML",
            "credits": "3",
            "description": "",
            "instruction_mode": "In-Person",
            "score": 0.88,
        },
    ]

    with (
        patch(
            "chat_service.core.tools.llm_service.get_embedding",
            new=AsyncMock(return_value=fake_embedding),
        ) as mock_embed,
        patch(
            "chat_service.core.tools.neo4j_service.vector_search",
            new=AsyncMock(return_value=fake_results),
        ) as mock_search,
    ):
        toolset = _default_toolset()
        result = await toolset.registry["search_courses"].ainvoke({"query": "machine learning"})

    # Embedding call happens first
    mock_embed.assert_awaited_once()
    # vector_search receives the embedding produced by get_embedding
    mock_search.assert_awaited_once()
    assert mock_search.await_args is not None
    pos_args, kw_args = mock_search.await_args
    passed_embedding = kw_args.get("embedding") or (pos_args[1] if len(pos_args) > 1 else None)
    assert passed_embedding == fake_embedding

    assert result == fake_results


@pytest.mark.asyncio
async def test_search_courses_post_filters_by_department() -> None:
    """When department is provided, only matching course codes are returned."""
    all_results: list[dict[str, Any]] = [
        {
            "code": "CSCI 5622",
            "title": "Machine Learning",
            "credits": "3",
            "description": "",
            "instruction_mode": "In-Person",
            "score": 0.95,
        },
        {
            "code": "ECEN 5612",
            "title": "Random Signals",
            "credits": "3",
            "description": "",
            "instruction_mode": "In-Person",
            "score": 0.82,
        },
    ]

    with (
        patch(
            "chat_service.core.tools.llm_service.get_embedding",
            new=AsyncMock(return_value=[0.1]),
        ),
        patch(
            "chat_service.core.tools.neo4j_service.vector_search",
            new=AsyncMock(return_value=all_results),
        ),
    ):
        toolset = _default_toolset()
        result = await toolset.registry["search_courses"].ainvoke(
            {"query": "machine learning", "department": "CSCI"}
        )

    # Only the CSCI course should survive the post-filter
    assert len(result) == 1
    assert result[0]["code"] == "CSCI 5622"


@pytest.mark.asyncio
async def test_search_courses_no_filter_returns_all() -> None:
    """Without filters, all vector_search results pass through unchanged."""
    all_results: list[dict[str, Any]] = [
        {
            "code": "CSCI 5622",
            "title": "ML",
            "credits": "3",
            "description": "",
            "instruction_mode": "In-Person",
            "score": 0.95,
        },
        {
            "code": "ECEN 5612",
            "title": "Signals",
            "credits": "3",
            "description": "",
            "instruction_mode": "Online",
            "score": 0.80,
        },
    ]

    with (
        patch(
            "chat_service.core.tools.llm_service.get_embedding",
            new=AsyncMock(return_value=[0.1]),
        ),
        patch(
            "chat_service.core.tools.neo4j_service.vector_search",
            new=AsyncMock(return_value=all_results),
        ),
    ):
        toolset = _default_toolset()
        result = await toolset.registry["search_courses"].ainvoke({"query": "electives"})

    assert result == all_results


@pytest.mark.asyncio
async def test_search_courses_post_filters_by_instruction_mode() -> None:
    """instruction_mode filter removes courses whose mode doesn't match."""
    all_results: list[dict[str, Any]] = [
        {
            "code": "CSCI 5622",
            "title": "ML",
            "credits": "3",
            "description": "",
            "instruction_mode": "In-Person",
            "score": 0.95,
        },
        {
            "code": "CSCI 5832",
            "title": "NLP",
            "credits": "3",
            "description": "",
            "instruction_mode": "Online",
            "score": 0.90,
        },
    ]

    with (
        patch(
            "chat_service.core.tools.llm_service.get_embedding",
            new=AsyncMock(return_value=[0.1]),
        ),
        patch(
            "chat_service.core.tools.neo4j_service.vector_search",
            new=AsyncMock(return_value=all_results),
        ),
    ):
        toolset = _default_toolset()
        result = await toolset.registry["search_courses"].ainvoke(
            {"query": "AI courses", "instruction_mode": "In-Person"}
        )

    assert len(result) == 1
    assert result[0]["code"] == "CSCI 5622"
