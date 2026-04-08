"""Unit tests for chat_service.services.postgres_service (CUAI-41).

These cover the pure-logic surface — the meets-string parser, the
overlap predicate, and the input-validation guard rails on
``save_student_decision``. The DB-touching helpers are exercised by
``test_postgres_service_integration.py`` against a real Postgres,
because mocking SQLAlchemy adds zero confidence over an integration
test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from chat_service.services.postgres_service import (
    VALID_DECISION_TYPES,
    PostgresServiceError,
    _parse_meets,
    _time_overlaps,
    _to_async_url,
    lookup_course,
    save_student_decision,
)
from sqlalchemy.exc import SQLAlchemyError

# ─── _parse_meets ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("meets", "expected"),
    [
        # Both tokens have am/pm
        ("MW 11a-12:15p", [(frozenset({"M", "W"}), 11 * 60, 12 * 60 + 15)]),
        ("TTh 3:30p-4:45p", [(frozenset({"T", "R"}), 15 * 60 + 30, 16 * 60 + 45)]),
        ("MWF 9a-9:50a", [(frozenset({"M", "W", "F"}), 9 * 60, 9 * 60 + 50)]),
        (
            "MTWThF 8a-8:50a",
            [(frozenset({"M", "T", "W", "R", "F"}), 8 * 60, 8 * 60 + 50)],
        ),
        ("F 12p-12:50p", [(frozenset({"F"}), 720, 770)]),
        ("F 12a-1a", [(frozenset({"F"}), 0, 60)]),
        # Real CU data: start token omits am/pm, inherits from end.
        # ~84% of the real dataset uses this form.
        ("F 1-2:30p", [(frozenset({"F"}), 13 * 60, 14 * 60 + 30)]),
        ("F 1-4p", [(frozenset({"F"}), 13 * 60, 16 * 60)]),
        ("F 10-10:50a", [(frozenset({"F"}), 10 * 60, 10 * 60 + 50)]),
        ("F 12-1p", [(frozenset({"F"}), 12 * 60, 13 * 60)]),
        ("F 12-12:50p", [(frozenset({"F"}), 12 * 60, 12 * 60 + 50)]),
        ("F 11-11:50a", [(frozenset({"F"}), 11 * 60, 11 * 60 + 50)]),
        ("F 1:25-2:15p", [(frozenset({"F"}), 13 * 60 + 25, 14 * 60 + 15)]),
        ("F 10:10a-12p", [(frozenset({"F"}), 10 * 60 + 10, 12 * 60)]),
        # Saturday: CU uses "Sa", never bare "S"
        ("Sa 1-4:30p", [(frozenset({"S"}), 13 * 60, 16 * 60 + 30)]),
        ("Sa 8:30a-12p", [(frozenset({"S"}), 8 * 60 + 30, 12 * 60)]),
        # Multi-slot sections (semicolon-separated). Real CU data has
        # ~35 of these (e.g. a lecture + a separate recitation).
        (
            "MW 12:35-1:50p; Th 7-9:50p",
            [
                (frozenset({"M", "W"}), 12 * 60 + 35, 13 * 60 + 50),
                (frozenset({"R"}), 19 * 60, 21 * 60 + 50),
            ],
        ),
        (
            "F 9a-2p; Sa 8a-5p",
            [
                (frozenset({"F"}), 9 * 60, 14 * 60),
                (frozenset({"S"}), 8 * 60, 17 * 60),
            ],
        ),
    ],
)
def test_parse_meets_happy_paths(
    meets: str, expected: list[tuple[frozenset[str], int, int]]
) -> None:
    assert _parse_meets(meets) == expected


def test_parse_meets_partial_slots_returns_parseable_ones() -> None:
    """If one slot in a multi-slot meets parses and another doesn't,
    return the good ones rather than dropping the whole section."""
    result = _parse_meets("MW 10a-10:50a; BOGUS 99-99")
    assert result == [(frozenset({"M", "W"}), 10 * 60, 10 * 60 + 50)]


@pytest.mark.parametrize(
    "meets",
    [
        None,
        "",
        "   ",
        "TBA",
        "tba",
        "No Time Assigned",
        "Arranged",
        "arr",
        "Meets online (see class notes)",  # CU's non-schedule meets string
        "ZZ 9a-10a",  # unparseable day character
        "MW 9-10",  # NO am/pm anywhere — can't infer
        "MW 9a",  # missing dash
        "MW",  # missing time segment entirely
        "MW 13a-14a",  # invalid hour
        "MW 9a-9a",  # zero-length window
        "MW 10a-9a",  # end before start
    ],
)
def test_parse_meets_unparseable_returns_none(meets: str | None) -> None:
    assert _parse_meets(meets) is None


# ─── _time_overlaps ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("a_start", "a_end", "b_start", "b_end", "expected"),
    [
        (600, 700, 650, 800, True),  # straightforward overlap
        (600, 700, 700, 800, False),  # adjacent — back-to-back is OK
        (600, 700, 500, 600, False),  # adjacent on the other side
        (600, 800, 650, 750, True),  # one window contains the other
        (600, 700, 800, 900, False),  # disjoint
    ],
)
def test_time_overlaps(a_start: int, a_end: int, b_start: int, b_end: int, expected: bool) -> None:
    assert _time_overlaps(a_start, a_end, b_start, b_end) is expected


# ─── _to_async_url ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("input_url", "expected"),
    [
        (
            "postgresql://u:p@h:5432/db",
            "postgresql+asyncpg://u:p@h:5432/db",
        ),
        (
            "postgresql+psycopg://u:p@h:5432/db",
            "postgresql+asyncpg://u:p@h:5432/db",
        ),
        (
            "postgresql+psycopg2://u:p@h:5432/db",
            "postgresql+asyncpg://u:p@h:5432/db",
        ),
        (
            "postgresql+asyncpg://u:p@h:5432/db",
            "postgresql+asyncpg://u:p@h:5432/db",
        ),
    ],
)
def test_to_async_url_rewrites_sync_schemes(input_url: str, expected: str) -> None:
    assert _to_async_url(input_url) == expected


# ─── VALID_DECISION_TYPES ───────────────────────────────────────────────


def test_valid_decision_types_contents() -> None:
    expected = frozenset({"planned", "interested", "not_interested"})
    assert expected == VALID_DECISION_TYPES


# ─── save_student_decision validation ──────────────────────────────────


@pytest.mark.asyncio
async def test_save_student_decision_rejects_invalid_decision_type() -> None:
    session = MagicMock()
    with pytest.raises(ValueError, match="Invalid decision_type"):
        await save_student_decision(
            session,
            user_id=1,
            course_code="CSCI 1300",
            decision_type="nonsense",
        )
    # Validation runs before any session call.
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_save_student_decision_rejects_empty_course_code() -> None:
    session = MagicMock()
    with pytest.raises(ValueError, match="course_code"):
        await save_student_decision(
            session,
            user_id=1,
            course_code="   ",
            decision_type="planned",
        )
    session.add.assert_not_called()


# ─── lookup_course ──────────────────────────────────────────────────────


def _make_section(
    crn: str, section_number: str, type_: str, meets: str, instructor: str, status: str
) -> MagicMock:
    s = MagicMock()
    s.crn = crn
    s.section_number = section_number
    s.type = type_
    s.meets = meets
    s.instructor = instructor
    s.status = status
    return s


def _make_attribute(college: str, category: str) -> MagicMock:
    a = MagicMock()
    a.college = college
    a.category = category
    return a


def _make_course() -> MagicMock:
    course = MagicMock()
    course.code = "CSCI 2270"
    course.title = "Data Structures"
    course.credits = "4"
    course.description = "Fundamental data structures."
    course.instruction_mode = "In-Person"
    course.campus = "Boulder"
    course.prerequisites_raw = "CSCI 1300 min grade C-"
    course.topic_titles = None
    course.sections = [
        _make_section("30002", "001", "LEC", "MWF 10-10:50a", "Smith, J", "Open"),
        _make_section("30001", "010", "REC", "F 11-11:50a", "Doe, A", "Open"),
    ]
    course.attributes = [
        _make_attribute("Engineering", "Humanities & Social Science"),
        _make_attribute("Arts & Sciences", "Natural Science"),
    ]
    return course


def _session_returning(obj: object) -> AsyncMock:
    """Return an AsyncSession mock whose execute() yields a scalars().first() == obj."""
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = obj
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session = MagicMock()
    session.execute = AsyncMock(return_value=result_mock)
    return session


@pytest.mark.asyncio
async def test_lookup_course_returns_structured_dict() -> None:
    """Full dict is returned; sections sorted by crn, attributes by (college, category)."""
    session = _session_returning(_make_course())
    result = await lookup_course(session, course_code="CSCI 2270")

    assert result is not None
    assert result["code"] == "CSCI 2270"
    assert result["title"] == "Data Structures"
    assert result["credits"] == "4"
    assert result["prerequisites_raw"] == "CSCI 1300 min grade C-"

    # Sections sorted by crn ascending: "30001" < "30002"
    assert [s["crn"] for s in result["sections"]] == ["30001", "30002"]
    assert result["sections"][0] == {
        "crn": "30001",
        "section_number": "010",
        "type": "REC",
        "meets": "F 11-11:50a",
        "instructor": "Doe, A",
        "status": "Open",
    }

    # Attributes sorted by (college, category): "Arts & Sciences" < "Engineering"
    assert result["attributes"] == [
        {"college": "Arts & Sciences", "category": "Natural Science"},
        {"college": "Engineering", "category": "Humanities & Social Science"},
    ]


@pytest.mark.asyncio
async def test_lookup_course_returns_none_for_missing_course() -> None:
    """Returns None (not an exception) when the course code is not in the DB."""
    session = _session_returning(None)
    result = await lookup_course(session, course_code="XXXX 9999")
    assert result is None


@pytest.mark.asyncio
async def test_lookup_course_returns_none_for_empty_course_code() -> None:
    """Empty / whitespace course_code returns None without touching the DB."""
    session = MagicMock()
    session.execute = AsyncMock()

    result = await lookup_course(session, course_code="   ")
    assert result is None
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_lookup_course_wraps_sqlalchemy_error_as_postgres_service_error() -> None:
    """SQLAlchemyError is wrapped in PostgresServiceError with the original chained."""
    session = MagicMock()
    original = SQLAlchemyError("connection reset")
    session.execute = AsyncMock(side_effect=original)

    with pytest.raises(PostgresServiceError) as exc_info:
        await lookup_course(session, course_code="CSCI 2270")

    assert exc_info.value.__cause__ is original
