"""Unit tests for chat_service.services.neo4j_service (CUAI-34).

The Neo4j driver is mocked — these tests assert the Cypher shape, parameter
wiring, and result-grouping logic without requiring a live database. Mirrors
the mocking pattern established in course-search-api/tests/test_courses_search.py.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from chat_service.services.neo4j_service import (
    get_degree_requirements,
    get_prerequisite_chain,
    vector_search,
)


class _AsyncRecordIter:
    """Async iterator mimicking the neo4j AsyncResult iteration protocol."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records
        self._i = 0

    def __aiter__(self) -> _AsyncRecordIter:
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._i >= len(self._records):
            raise StopAsyncIteration
        rec = self._records[self._i]
        self._i += 1
        return rec


def _make_driver(
    *record_batches: list[dict[str, Any]],
) -> tuple[MagicMock, AsyncMock]:
    """Build a mock AsyncDriver whose session.run yields each batch in turn.

    Pass one batch per expected ``session.run`` call. Returns the driver and
    the ``run`` mock so tests can assert on Cypher and parameters.
    """
    iters = [_AsyncRecordIter(batch) for batch in record_batches]
    run_mock = AsyncMock(side_effect=iters)

    session = MagicMock()
    session.run = run_mock

    # `async with driver.session() as session:` — session() returns an
    # async context manager that yields our mock session.
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session_ctx)
    return driver, run_mock


# ─── vector_search ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vector_search_returns_top_results_with_scores() -> None:
    records = [
        {
            "code": "CSCI 4830",
            "title": "Machine Learning",
            "credits": "3",
            "description": "ML techniques.",
            "instruction_mode": "In Person",
            "score": 0.95,
        },
        {
            "code": "CSCI 5622",
            "title": "Machine Learning",
            "credits": "3",
            "description": "Graduate ML.",
            "instruction_mode": "In Person",
            "score": 0.91,
        },
    ]
    driver, run_mock = _make_driver(records)

    results = await vector_search(driver, embedding=[0.1] * 768, limit=10)

    assert len(results) == 2
    assert results[0]["code"] == "CSCI 4830"
    assert results[0]["score"] == 0.95
    assert results[0]["credits"] == "3"
    assert results[0]["instruction_mode"] == "In Person"


@pytest.mark.asyncio
async def test_vector_search_uses_parameterized_cypher() -> None:
    driver, run_mock = _make_driver([])
    embedding = [0.2] * 768

    await vector_search(driver, embedding=embedding, limit=5)

    run_mock.assert_awaited_once()
    cypher, params = run_mock.await_args.args[0], run_mock.await_args.kwargs
    assert "db.index.vector.queryNodes" in cypher
    # Parameters — not interpolated into Cypher text.
    assert params == {
        "index": "course-embeddings",
        "limit": 5,
        "embedding": embedding,
    }
    # Defense in depth: confirm the literal embedding values never landed
    # in the query string.
    assert "0.2" not in cypher


@pytest.mark.asyncio
async def test_vector_search_respects_default_limit() -> None:
    driver, run_mock = _make_driver([])
    await vector_search(driver, embedding=[0.0] * 768)
    assert run_mock.await_args.kwargs["limit"] == 10


# ─── get_prerequisite_chain ─────────────────────────────────────────────


_COURSE_ROW = [{"code": "CSCI 3104", "title": "Algorithms"}]


@pytest.mark.asyncio
async def test_prerequisite_chain_returns_course_and_edges() -> None:
    edges = [
        {
            "from_code": "CSCI 3104",
            "to_code": "CSCI 2270",
            "type": "prerequisite",
            "min_grade": "C-",
            "raw_text": "CSCI 2270 (min grade C-)",
        },
        {
            "from_code": "CSCI 2270",
            "to_code": "CSCI 1300",
            "type": "prerequisite",
            "min_grade": "C-",
            "raw_text": "CSCI 1300",
        },
    ]
    driver, _ = _make_driver(_COURSE_ROW, edges)

    result = await get_prerequisite_chain(driver, "CSCI 3104")

    assert result["course"] == {"code": "CSCI 3104", "title": "Algorithms"}
    assert len(result["edges"]) == 2
    assert result["edges"][0] == {
        "from": "CSCI 3104",
        "to": "CSCI 2270",
        "type": "prerequisite",
        "min_grade": "C-",
        "raw_text": "CSCI 2270 (min grade C-)",
    }
    assert result["edges"][1]["from"] == "CSCI 2270"


@pytest.mark.asyncio
async def test_prerequisite_chain_deduplicates_edges() -> None:
    # Same edge reached via two different paths should appear once.
    duplicated = [
        {
            "from_code": "CSCI 3104",
            "to_code": "CSCI 2270",
            "type": "prerequisite",
            "min_grade": "C-",
            "raw_text": "x",
        },
        {
            "from_code": "CSCI 3104",
            "to_code": "CSCI 2270",
            "type": "prerequisite",
            "min_grade": "C-",
            "raw_text": "x",
        },
    ]
    driver, _ = _make_driver(_COURSE_ROW, duplicated)

    result = await get_prerequisite_chain(driver, "CSCI 3104")

    assert len(result["edges"]) == 1


@pytest.mark.asyncio
async def test_prerequisite_chain_course_with_no_prereqs() -> None:
    # Course exists but has zero prereq edges.
    driver, _ = _make_driver([{"code": "CSCI 1300", "title": "CS 1"}], [])

    result = await get_prerequisite_chain(driver, "CSCI 1300")

    assert result["course"] == {"code": "CSCI 1300", "title": "CS 1"}
    assert result["edges"] == []


@pytest.mark.asyncio
async def test_prerequisite_chain_unknown_course_returns_empty() -> None:
    # Course lookup returns no rows — function must short-circuit before
    # issuing the edge query.
    driver, run_mock = _make_driver([])
    result = await get_prerequisite_chain(driver, "BOGUS 0000")
    assert result == {"course": None, "edges": []}
    assert run_mock.await_count == 1


@pytest.mark.asyncio
async def test_prerequisite_chain_uses_parameterized_course_code() -> None:
    driver, run_mock = _make_driver(_COURSE_ROW, [])
    await get_prerequisite_chain(driver, "CSCI 3104")

    # Both the course query and the edge query use parameters, not
    # interpolation.
    for call in run_mock.await_args_list:
        cypher = call.args[0]
        assert call.kwargs == {"code": "CSCI 3104"}
        assert "'CSCI 3104'" not in cypher
    # The edge query (second call) enforces the depth bound.
    edge_cypher = run_mock.await_args_list[1].args[0]
    assert "HAS_PREREQUISITE*1..5" in edge_cypher


# ─── get_degree_requirements ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_degree_requirements_groups_courses_by_requirement() -> None:
    records = [
        {
            "program_name": "Computer Science - Bachelor of Science (BS)",
            "program_type": "BS",
            "program_total_credits": "128",
            "sort_order": 1,
            "req_name": "Calculus 1",
            "requirement_type": "required",
            "credits": "4",
            "raw_text": "MATH 1300",
            "course_code": "MATH 1300",
            "course_title": "Calculus 1",
            "or_alternative_to": None,
        },
        {
            "program_name": "Computer Science - Bachelor of Science (BS)",
            "program_type": "BS",
            "program_total_credits": "128",
            "sort_order": 2,
            "req_name": "Data Structures",
            "requirement_type": "required",
            "credits": "4",
            "raw_text": "CSCI 2270 or CSCI 2275",
            "course_code": "CSCI 2270",
            "course_title": "Data Structures",
            "or_alternative_to": None,
        },
        {
            "program_name": "Computer Science - Bachelor of Science (BS)",
            "program_type": "BS",
            "program_total_credits": "128",
            "sort_order": 3,
            "req_name": "Data Structures Alt",
            "requirement_type": "or_alternative",
            "credits": "4",
            "raw_text": "CSCI 2275",
            "course_code": "CSCI 2275",
            "course_title": "Data Structures Accelerated",
            "or_alternative_to": "Data Structures",
        },
    ]
    driver, _ = _make_driver(records)

    result = await get_degree_requirements(driver, "Computer Science - Bachelor of Science (BS)")

    assert result["program"] == {
        "name": "Computer Science - Bachelor of Science (BS)",
        "type": "BS",
        "total_credits": "128",
    }
    assert len(result["requirements"]) == 3

    calc = result["requirements"][0]
    assert calc["name"] == "Calculus 1"
    assert calc["requirement_type"] == "required"
    assert calc["courses"] == [{"code": "MATH 1300", "title": "Calculus 1"}]
    assert calc["or_alternative_to"] is None

    alt = result["requirements"][2]
    assert alt["requirement_type"] == "or_alternative"
    assert alt["or_alternative_to"] == "Data Structures"


@pytest.mark.asyncio
async def test_degree_requirements_multiple_satisfying_courses() -> None:
    # One requirement SATISFIED_BY two courses → two rows, merged to one req.
    records = [
        {
            "program_name": "CS BA",
            "program_type": "BA",
            "program_total_credits": "120",
            "sort_order": 5,
            "req_name": "Upper division elective",
            "requirement_type": "choose_n",
            "credits": "3",
            "raw_text": "Choose one",
            "course_code": "CSCI 4830",
            "course_title": "Machine Learning",
            "or_alternative_to": None,
        },
        {
            "program_name": "CS BA",
            "program_type": "BA",
            "program_total_credits": "120",
            "sort_order": 5,
            "req_name": "Upper division elective",
            "requirement_type": "choose_n",
            "credits": "3",
            "raw_text": "Choose one",
            "course_code": "CSCI 4022",
            "course_title": "Data Science",
            "or_alternative_to": None,
        },
    ]
    driver, _ = _make_driver(records)

    result = await get_degree_requirements(driver, "CS BA")

    assert len(result["requirements"]) == 1
    req = result["requirements"][0]
    assert len(req["courses"]) == 2
    assert {"code": "CSCI 4830", "title": "Machine Learning"} in req["courses"]
    assert {"code": "CSCI 4022", "title": "Data Science"} in req["courses"]


@pytest.mark.asyncio
async def test_degree_requirements_unknown_program() -> None:
    driver, _ = _make_driver([])
    result = await get_degree_requirements(driver, "Not A Real Program")
    assert result == {"program": None, "requirements": []}


@pytest.mark.asyncio
async def test_degree_requirements_program_with_no_requirements() -> None:
    # Program exists but has zero HAS_REQUIREMENT edges — OPTIONAL MATCH
    # yields one row with null requirement fields.
    records = [
        {
            "program_name": "Empty Program",
            "program_type": "Minor",
            "program_total_credits": "18",
            "sort_order": None,
            "req_name": None,
            "requirement_type": None,
            "credits": None,
            "raw_text": None,
            "course_code": None,
            "course_title": None,
            "or_alternative_to": None,
        },
    ]
    driver, _ = _make_driver(records)

    result = await get_degree_requirements(driver, "Empty Program")

    assert result["program"]["name"] == "Empty Program"
    assert result["requirements"] == []


@pytest.mark.asyncio
async def test_degree_requirements_uses_parameterized_name() -> None:
    driver, run_mock = _make_driver([])
    await get_degree_requirements(driver, "Computer Science")

    cypher, params = run_mock.await_args.args[0], run_mock.await_args.kwargs
    assert params == {"name": "Computer Science"}
    assert "Computer Science" not in cypher  # never interpolated
