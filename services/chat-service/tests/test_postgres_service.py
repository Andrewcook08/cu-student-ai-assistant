"""Unit tests for chat_service.services.postgres_service (CUAI-41).

These cover the pure-logic surface — the meets-string parser, the
overlap predicate, and the input-validation guard rails on
``save_student_decision``. The DB-touching helpers are exercised by
``test_postgres_service_integration.py`` against a real Postgres,
because mocking SQLAlchemy adds zero confidence over an integration
test.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from chat_service.services.postgres_service import (
    VALID_DECISION_TYPES,
    _parse_meets,
    _time_overlaps,
    _to_async_url,
    save_student_decision,
)

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
def test_time_overlaps(
    a_start: int, a_end: int, b_start: int, b_end: int, expected: bool
) -> None:
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
