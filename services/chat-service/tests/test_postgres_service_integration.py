"""Integration tests for postgres_service against a real Postgres instance.

Gated behind the ``integration`` pytest marker so the default
``uv run pytest`` skips them. Run them explicitly with::

    docker compose up -d postgres
    uv run pytest -m integration services/chat-service/tests/test_postgres_service_integration.py

What these tests verify that the unit tests cannot:

- The eager-loaded query in ``get_student_data`` actually round-trips
  the program name + completed courses + decisions in one trip.
- ``save_student_decision`` commits and the row is visible to a fresh
  read on the same session.
- ``get_schedule_conflicts`` correctly joins courses to sections,
  parses the freeform meets strings, and reports overlapping pairs
  while ignoring non-overlapping ones.
- The parameterized-query promise holds: a course code containing a
  classic SQL injection payload persists literally and the ``users``
  table survives.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from chat_service.services.postgres_service import (
    PostgresServiceError,
    build_postgres_engine,
    get_schedule_conflicts,
    get_student_data,
    postgres_session,
    save_student_decision,
)
from shared.models import (
    Base,
    CompletedCourse,
    Course,
    Program,
    Section,
    StudentDecision,
    User,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

pytestmark = pytest.mark.integration


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/cu_chat_test",
    )


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Build an async engine, create tables, tear them down at the end.

    Uses ``Base.metadata.create_all`` / ``drop_all`` via ``run_sync``
    so the test owns the schema lifecycle and parallel runs against
    the same DB don't see leftover state from a previous failure.

    **Safety rail**: the fixture drops every table in ``Base.metadata``
    at setup and teardown. Pointing ``DATABASE_URL`` at a non-test
    database by accident would destroy real data. We refuse to run
    unless the database name contains ``test`` — opt in by naming
    your test DB accordingly (the default ``cu_chat_test`` satisfies
    this).
    """
    url = _database_url()
    db_name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if "test" not in db_name.lower():
        pytest.fail(
            f"Refusing to run destructive integration tests against database "
            f"{db_name!r}. Set DATABASE_URL to a database whose name contains "
            f"'test' (e.g. postgresql://postgres:postgres@localhost:5432/cu_chat_test)."
        )
    eng = build_postgres_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await eng.dispose()


@pytest_asyncio.fixture
async def seeded_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Seed a small dataset and yield an open session against it.

    The seed deliberately includes:
    - one program + one user (with both completed courses and one decision)
    - two courses whose only sections overlap on Mon/Wed mornings
    - a third course on TTh that should NOT be flagged
    - a section with ``meets="TBA"`` to verify the parser skip path
    """
    async with postgres_session(engine) as session:
        program = Program(name="Computer Science BA", type="BA", total_credits="120")
        session.add(program)
        await session.flush()

        user = User(
            email="test@colorado.edu",
            password_hash="x",
            name="Test Student",
            program_id=program.id,
        )
        session.add(user)
        await session.flush()

        session.add_all(
            [
                CompletedCourse(user_id=user.id, course_code="CSCI 1300", grade="A"),
                CompletedCourse(user_id=user.id, course_code="MATH 1300", grade="B+"),
                StudentDecision(
                    user_id=user.id,
                    course_code="CSCI 2270",
                    decision_type="planned",
                    notes="seed",
                ),
            ]
        )

        course_a = Course(code="CSCI 2270", dept="CSCI", title="Data Structures")
        course_b = Course(code="CSCI 2400", dept="CSCI", title="Computer Systems")
        course_c = Course(code="MATH 2400", dept="MATH", title="Calc 3")
        session.add_all([course_a, course_b, course_c])
        await session.flush()

        session.add_all(
            [
                Section(
                    course_id=course_a.id,
                    crn="11111",
                    section_number="001",
                    meets="MW 10a-10:50a",
                ),
                Section(
                    course_id=course_b.id,
                    crn="22222",
                    section_number="001",
                    meets="MW 10:30a-11:20a",
                ),
                Section(
                    course_id=course_c.id,
                    crn="33333",
                    section_number="001",
                    meets="TTh 2p-3:15p",
                ),
                Section(
                    course_id=course_b.id,
                    crn="22223",
                    section_number="002",
                    meets="TBA",
                ),
            ]
        )
        await session.commit()

        # Stash user_id on the session so tests can grab it without
        # re-querying. (Tests use a known email instead — see below.)
        yield session


# ─── get_student_data ───────────────────────────────────────────────────


async def test_get_student_data_returns_full_profile(
    seeded_session: AsyncSession,
) -> None:
    user = (
        await seeded_session.execute(select(User).where(User.email == "test@colorado.edu"))
    ).scalar_one()

    data = await get_student_data(seeded_session, user_id=user.id)

    assert data["user_id"] == user.id
    assert data["program"] == "Computer Science BA"
    assert [c["course_code"] for c in data["completed"]] == ["CSCI 1300", "MATH 1300"]
    assert {c["grade"] for c in data["completed"]} == {"A", "B+"}
    assert len(data["decisions"]) == 1
    assert data["decisions"][0]["course_code"] == "CSCI 2270"
    assert data["decisions"][0]["decision_type"] == "planned"


async def test_get_student_data_unknown_user_returns_empty_shape(
    seeded_session: AsyncSession,
) -> None:
    data = await get_student_data(seeded_session, user_id=999_999)
    assert data == {
        "user_id": 999_999,
        "program": None,
        "completed": [],
        "decisions": [],
    }


# ─── save_student_decision ──────────────────────────────────────────────


async def test_save_student_decision_round_trips(
    seeded_session: AsyncSession,
) -> None:
    user = (
        await seeded_session.execute(select(User).where(User.email == "test@colorado.edu"))
    ).scalar_one()

    saved = await save_student_decision(
        seeded_session,
        user_id=user.id,
        course_code="CSCI 3104",
        decision_type="interested",
        notes="looks fun",
    )

    assert saved["course_code"] == "CSCI 3104"
    assert saved["decision_type"] == "interested"
    assert saved["notes"] == "looks fun"
    assert saved["id"] is not None
    assert saved["created_at"] is not None

    # Visible to a follow-up read on the same session.
    data = await get_student_data(seeded_session, user_id=user.id)
    decision_codes = [d["course_code"] for d in data["decisions"]]
    assert "CSCI 3104" in decision_codes


async def test_save_student_decision_invalid_type_does_not_insert(
    seeded_session: AsyncSession,
) -> None:
    user = (
        await seeded_session.execute(select(User).where(User.email == "test@colorado.edu"))
    ).scalar_one()
    before = (
        await seeded_session.execute(
            select(StudentDecision).where(StudentDecision.user_id == user.id)
        )
    ).all()

    with pytest.raises(ValueError):
        await save_student_decision(
            seeded_session,
            user_id=user.id,
            course_code="CSCI 3104",
            decision_type="bogus",
        )

    after = (
        await seeded_session.execute(
            select(StudentDecision).where(StudentDecision.user_id == user.id)
        )
    ).all()
    assert len(before) == len(after)


async def test_save_student_decision_sql_injection_is_inert(
    seeded_session: AsyncSession,
) -> None:
    """Regression: a SQL-injection payload persists *literally* — the
    parameterized query path means the string never reaches the SQL
    parser as code, only as a value.

    ``StudentDecision.course_code`` is ``String(10)`` so we pick a
    short payload that still contains the classic injection
    metacharacters (``';--``) — the point is that SQLAlchemy binds
    it as a value, not that it's a full ``DROP TABLE`` statement.
    """
    user = (
        await seeded_session.execute(select(User).where(User.email == "test@colorado.edu"))
    ).scalar_one()

    payload = "x';DROP--"  # 9 chars, fits in String(10); has ';-- metachars
    saved = await save_student_decision(
        seeded_session,
        user_id=user.id,
        course_code=payload,
        decision_type="planned",
    )

    assert saved["course_code"] == payload

    # users table is intact and still contains the seeded user.
    users = (await seeded_session.execute(select(User))).scalars().all()
    assert any(u.email == "test@colorado.edu" for u in users)


# ─── get_schedule_conflicts ─────────────────────────────────────────────


async def test_get_schedule_conflicts_detects_overlap(
    seeded_session: AsyncSession,
) -> None:
    conflicts = await get_schedule_conflicts(
        seeded_session,
        course_codes=["CSCI 2270", "CSCI 2400", "MATH 2400"],
    )

    # Exactly one conflict pair: CSCI 2270 vs CSCI 2400 on MW.
    assert len(conflicts) == 1
    c = conflicts[0]
    assert {c["course_a"], c["course_b"]} == {"CSCI 2270", "CSCI 2400"}
    assert sorted(c["overlap_days"]) == ["M", "W"]


async def test_get_schedule_conflicts_empty_input(
    seeded_session: AsyncSession,
) -> None:
    assert await get_schedule_conflicts(seeded_session, course_codes=[]) == []
    assert await get_schedule_conflicts(seeded_session, course_codes=["CSCI 2270"]) == []


# ─── Smoke import for PostgresServiceError ──────────────────────────────


def test_postgres_service_error_importable() -> None:
    assert issubclass(PostgresServiceError, RuntimeError)
