"""Postgres async service layer for the chat service.

Backs three slices of the LLM tool layer (CHAT-005 / CUAI-37):

- **Student data read** (``get_student_data``) — returns the user's
  program, completed courses, and prior decisions in one shot. Powers
  the ``get_student_profile`` tool.
- **Decision write** (``save_student_decision``) — append-only insert
  into ``student_decisions``. Powers the ``save_decision`` tool.
- **Schedule conflict detection** (``get_schedule_conflicts``) — joins
  courses to sections, parses the freeform ``meets`` strings, and
  reports overlapping section pairs. Powers the
  ``find_schedule_conflicts`` tool.

The ``AsyncEngine`` is owned by ``main.py`` lifespan (constructed once
via :func:`build_postgres_engine`) and stored on ``app.state``. Helpers
take an ``AsyncSession`` so callers that already have one (e.g. a
request scope) can compose without spinning up a second session;
:func:`postgres_session` is the convenience context manager for
ad-hoc callers.

This async engine is **independent** of ``shared.shared.database``.
That module exposes a *sync* engine used by ``course-search-api``
which still runs on synchronous SQLAlchemy. The chat service is async
end-to-end and needs its own ``asyncpg``-backed engine. The two
engines connect to the same Postgres but never share connection
pools, sessions, or sessionmakers.

ADR-14 (trust boundary): ``user_id`` is a positional/keyword argument,
never read from a tool-arguments blob or LLM-supplied dict. The
upstream ``tool_executor`` overrides any LLM-provided ``user_id`` with
the JWT subject before calling these helpers, so by the time we
receive ``user_id`` here it is the authenticated identity.

ADR-33 (parameterization): every query goes through SQLAlchemy
expressions or bound parameters. There is intentionally no ``text()``
+ f-string composition anywhere in this module — Postgres injection is
not a possible failure mode.

Errors share a common :class:`PostgresError` base so callers can catch
any database failure with a single ``except``:

- :class:`PostgresError`        — base class; catch this for any failure
- :class:`PostgresServiceError` — connection / protocol / unexpected
  ``SQLAlchemyError`` failures, surfaced with a user-facing message and
  the underlying exception chained via ``raise ... from exc``

``ValueError`` from input validation (e.g. an invalid
``decision_type``) is *not* wrapped — the tool executor turns it into a
"retry-once with corrected arguments" loop, which would be defeated by
a generic service error.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from shared.models import (
    Course,
    Program,
    Section,
    StudentDecision,
    User,
)
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload


class PostgresError(RuntimeError):
    """Base class for postgres_service failures — catch this for any DB error."""


class PostgresServiceError(PostgresError):
    """Raised when Postgres is unreachable, errors out, or returns unexpectedly."""


# ─── Constants ──────────────────────────────────────────────────────────

#: Allowed values for ``StudentDecision.decision_type``. Validated at the
#: service boundary so the tool_executor surfaces invalid LLM output as a
#: ``ValueError`` (retry-once "Invalid parameters") rather than a generic
#: 500-class error.
VALID_DECISION_TYPES: frozenset[str] = frozenset({"planned", "interested", "not_interested"})

#: Documents the audit-log retention stance at the code level so the
#: SEC review's "retention policy documented" AC ties back to a real
#: importable symbol. POC keeps everything; production target is
#: 90-day retention via a scheduled prune job (future work).
TOOL_AUDIT_LOG_RETENTION_POLICY: str = (
    "POC: tool_audit_log rows are retained indefinitely (no automated pruning). "
    "Production target (future work): retain 90 days, scheduled job drops older "
    "rows. Documented in docs/architecture.md § Audit log retention."
)

_SERVICE_MESSAGE = "The database is temporarily unavailable. Please try again."

# Single-letter day codes used internally. ``Th`` is normalized to ``R``
# at parse time so downstream comparison only ever sees one
# representation of Thursday.
_VALID_DAY_CODES: frozenset[str] = frozenset({"M", "T", "W", "R", "F", "S", "U"})

# Sentinel meets strings that mean "no scheduled time" — comparing them
# would be meaningless, so the parser returns ``None`` and the conflict
# detector skips the section.
_UNSCHEDULED_MEETS: frozenset[str] = frozenset({"tba", "no time assigned", "arranged", "arr"})

# ``<hour>(:<minute>)?(<a|p>)?`` — anchored, no leading/trailing whitespace.
# Hour 1-12, optional :MM in 0-59. The am/pm marker is optional here
# because CU's real data uses a "start inherits from end" convention
# (e.g. ``"1-2:30p"`` means 1pm-2:30pm). ``_parse_meets`` enforces that
# the end token has a marker and the start either has its own marker
# or inherits the end's.
_TIME_RE = re.compile(r"^(?P<hour>1[0-2]|[1-9])(?::(?P<minute>[0-5][0-9]))?(?P<ampm>[ap])?$")


# ─── Engine factory + session helper ────────────────────────────────────


def _to_async_url(database_url: str) -> str:
    """Rewrite a sync Postgres URL to its asyncpg equivalent.

    Idempotent: an already-asyncpg URL passes through unchanged. Handles
    the three sync schemes the rest of the codebase uses today
    (``postgresql://``, ``postgresql+psycopg://``, ``postgresql+psycopg2://``)
    so an env var copied from course-search-api works without edits.
    """
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
        if database_url.startswith(prefix):
            return "postgresql+asyncpg://" + database_url[len(prefix) :]
    return database_url


def build_postgres_engine(database_url: str) -> AsyncEngine:
    """Construct the long-lived async engine used by the chat service.

    Called once from ``main.py`` lifespan and stored on
    ``app.state.postgres_engine``. ``pool_pre_ping=True`` so a stale
    connection (e.g. after Postgres restarts in dev) is detected and
    replaced on checkout instead of surfacing a confusing
    ``InterfaceError`` mid-request.
    """
    return create_async_engine(_to_async_url(database_url), pool_pre_ping=True)


@asynccontextmanager
async def postgres_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Yield a single ``AsyncSession`` bound to *engine*.

    ``expire_on_commit=False`` so attributes loaded before commit
    (e.g. ``decision.created_at`` populated by ``server_default``) stay
    accessible after we ``await session.refresh()`` — otherwise the
    ORM marks them expired and the next access triggers an
    awkward implicit re-load on a closed session.
    """
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session


# ─── Student data read ──────────────────────────────────────────────────


async def get_student_data(session: AsyncSession, *, user_id: int) -> dict[str, Any]:
    """Return the user's program, completed courses, and prior decisions.

    Single trip to the DB: the ``User`` row is fetched with both
    relationships eager-loaded via ``selectinload``, and the ``Program``
    name is grabbed via an outer join so missing-program users still
    return cleanly.

    Returns a stable shape even when the user does not exist — the
    auth layer is the right place to reject unknown users, and the
    tool callers should not crash on a deleted account.
    """
    try:
        stmt = (
            select(User, Program.name)
            .outerjoin(Program, Program.id == User.program_id)
            .options(
                selectinload(User.completed_courses),
                selectinload(User.decisions),
            )
            .where(User.id == user_id)
        )
        result = await session.execute(stmt)
        row = result.first()
    except (SQLAlchemyError, DBAPIError) as exc:
        raise PostgresServiceError(_SERVICE_MESSAGE) from exc

    if row is None:
        return {
            "user_id": user_id,
            "program": None,
            "completed": [],
            "decisions": [],
        }

    user: User = row[0]
    program_name: str | None = row[1]

    completed = sorted(
        ({"course_code": cc.course_code, "grade": cc.grade} for cc in user.completed_courses),
        key=lambda c: c["course_code"] or "",
    )

    decisions = sorted(
        (
            {
                "course_code": d.course_code,
                "decision_type": d.decision_type,
                "notes": d.notes,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in user.decisions
        ),
        key=lambda d: d["created_at"] or "",
        reverse=True,
    )

    return {
        "user_id": user_id,
        "program": program_name,
        "completed": completed,
        "decisions": decisions,
    }


# ─── Decision write ─────────────────────────────────────────────────────


async def save_student_decision(
    session: AsyncSession,
    *,
    user_id: int,
    course_code: str,
    decision_type: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Insert a new ``student_decisions`` row and return its serialized form.

    Validation runs *before* any DB call so a bad ``decision_type``
    never reaches the database. Both validation errors raise
    ``ValueError``, which the tool executor turns into a retry-once
    "Invalid parameters" message — wrapping them in
    ``PostgresServiceError`` would defeat that loop.

    The schema is append-only on purpose: a student can change their
    mind ("interested" → "planned"), and the history is the audit
    trail. We never UPDATE an existing row.
    """
    if decision_type not in VALID_DECISION_TYPES:
        raise ValueError(
            f"Invalid decision_type {decision_type!r}; "
            f"must be one of {sorted(VALID_DECISION_TYPES)}"
        )
    cleaned_code = course_code.strip() if isinstance(course_code, str) else ""
    if not cleaned_code:
        raise ValueError("course_code must be a non-empty string")

    row = StudentDecision(
        user_id=user_id,
        course_code=cleaned_code,
        decision_type=decision_type,
        notes=notes,
    )
    try:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    except (SQLAlchemyError, DBAPIError) as exc:
        # Best-effort rollback so the session is reusable. We swallow
        # the rollback error itself — the original failure is what the
        # caller needs to see.
        with contextlib.suppress(SQLAlchemyError):
            await session.rollback()
        raise PostgresServiceError(_SERVICE_MESSAGE) from exc

    return {
        "id": row.id,
        "user_id": row.user_id,
        "course_code": row.course_code,
        "decision_type": row.decision_type,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ─── Schedule conflict detection ────────────────────────────────────────


async def get_schedule_conflicts(
    session: AsyncSession,
    *,
    course_codes: list[str],
) -> list[dict[str, Any]]:
    """Return overlapping section pairs across the supplied *course_codes*.

    For each pair of **distinct** courses, every combination of their
    sections is checked for day-and-time overlap. Two sections of the
    *same* course are never reported because the student picks one
    section per course — they can't conflict with themselves.

    Sections with a missing or unparseable ``meets`` string are
    silently skipped (the parser returns ``None``); the surfaced
    conflicts are always actual schedule clashes.
    """
    deduped = sorted({code for code in course_codes if code})
    if len(deduped) < 2:
        return []

    try:
        stmt = (
            select(
                Course.code,
                Section.crn,
                Section.section_number,
                Section.meets,
            )
            .join(Section, Section.course_id == Course.id)
            .where(Course.code.in_(deduped))
        )
        result = await session.execute(stmt)
        rows = result.all()
    except (SQLAlchemyError, DBAPIError) as exc:
        raise PostgresServiceError(_SERVICE_MESSAGE) from exc

    # Group rows by course_code and pre-parse ``meets`` once per
    # section. The inner double-loop below would otherwise re-parse
    # course B's sections on every iteration of course A — invisible
    # at today's section counts but strictly wasted work. Sections
    # whose ``meets`` doesn't parse (``None``) are filtered out here
    # so the conflict loop only sees usable slots.
    by_course: dict[str, list[tuple[str, str | None, list[tuple[frozenset[str], int, int]]]]] = {}
    for code, crn, _section_number, meets in rows:
        slots = _parse_meets(meets)
        if slots is None:
            continue
        by_course.setdefault(code, []).append((crn, meets, slots))

    conflicts: list[dict[str, Any]] = []
    course_keys = sorted(by_course.keys())
    for i in range(len(course_keys)):
        code_a = course_keys[i]
        for j in range(i + 1, len(course_keys)):
            code_b = course_keys[j]
            for crn_a, meets_a, slots_a in by_course[code_a]:
                for crn_b, meets_b, slots_b in by_course[code_b]:
                    # A single section can meet at multiple distinct
                    # times (``"MW 12:35-1:50p; Th 7-9:50p"``). We
                    # report the section pair once, with the union of
                    # overlapping days across *every* slot pair.
                    overlap_days: set[str] = set()
                    any_conflict = False
                    for days_a, start_a, end_a in slots_a:
                        for days_b, start_b, end_b in slots_b:
                            common = days_a & days_b
                            if not common:
                                continue
                            if not _time_overlaps(start_a, end_a, start_b, end_b):
                                continue
                            any_conflict = True
                            overlap_days.update(common)
                    if not any_conflict:
                        continue
                    conflicts.append(
                        {
                            "course_a": code_a,
                            "crn_a": crn_a,
                            "meets_a": meets_a,
                            "course_b": code_b,
                            "crn_b": crn_b,
                            "meets_b": meets_b,
                            "overlap_days": sorted(overlap_days),
                        }
                    )

    return conflicts


# ─── Meets-string parser ────────────────────────────────────────────────


def _parse_meets(meets: str | None) -> list[tuple[frozenset[str], int, int]] | None:
    """Parse a CU section ``meets`` string into one or more ``(days, start, end)`` slots.

    A single section can meet at multiple distinct times per week. CU
    encodes this as semicolon-separated slots within one ``meets``
    column: ``"MW 12:35-1:50p; Th 7-9:50p"`` is one section that meets
    Mon+Wed afternoon AND Thursday evening. Each slot is parsed
    independently by :func:`_parse_meets_slot`.

    Returns:
        - ``None`` for unparseable or unscheduled input (``None``,
          ``""``, ``"TBA"``, ``"No Time Assigned"``, ``"Arranged"``,
          non-schedule strings like ``"Meets online (see class notes)"``).
        - A list of ``(days, start, end)`` tuples — at least one — for
          any parseable input. If some slots parse and others don't,
          only the parseable ones are returned (conservative: better
          to report the known slots than drop the whole section).

    The conflict detector treats ``None`` as "skip this section" and
    iterates every slot in the returned list when checking for
    overlaps.
    """
    if meets is None:
        return None
    stripped = meets.strip()
    if not stripped or stripped.lower() in _UNSCHEDULED_MEETS:
        return None

    slots: list[tuple[frozenset[str], int, int]] = []
    for piece in stripped.split(";"):
        piece = piece.strip()
        if not piece:
            continue
        parsed = _parse_meets_slot(piece)
        if parsed is not None:
            slots.append(parsed)

    return slots if slots else None


def _parse_meets_slot(segment: str) -> tuple[frozenset[str], int, int] | None:
    """Parse a single ``<days> <start>-<end>`` slot.

    Accepts ``"MW 11a-12:15p"``, ``"TTh 3:30p-4:45p"``, ``"F 1-2:30p"``
    (start inherits am/pm from end — CU convention), ``"Sa 8:30a-12p"``,
    etc. The day segment is walked one character at a time so ``Th``
    and ``Sa`` are correctly recognized as two-character day codes.

    Returns ``None`` for any malformed slot. The caller
    (:func:`_parse_meets`) may still return other parseable slots for
    the same section.
    """
    # Split on the first run of whitespace: day segment, time segment.
    parts = segment.split(None, 1)
    if len(parts) != 2:
        return None
    day_segment, time_segment = parts

    days = _parse_days(day_segment)
    if days is None:
        return None

    if "-" not in time_segment:
        return None
    start_token, _, end_token = time_segment.partition("-")

    # End token MUST carry an am/pm marker. The start token may omit
    # it and inherit the end's marker — this is the CU convention
    # (``"F 1-2:30p"`` means 1pm-2:30pm). No noon-crossing cases
    # appear in real data, so a plain inherit rule is sufficient.
    end_parsed = _parse_time(end_token.strip())
    if end_parsed is None:
        return None
    end_hour, end_minute_int, end_ampm_opt = end_parsed
    if end_ampm_opt is None:
        return None
    end_ampm: str = end_ampm_opt

    start_parsed = _parse_time(start_token.strip())
    if start_parsed is None:
        return None
    start_hour, start_minute_int, start_ampm_opt = start_parsed
    start_ampm: str = start_ampm_opt if start_ampm_opt is not None else end_ampm

    start_minute = _to_24h(start_hour, start_ampm) * 60 + start_minute_int
    end_minute = _to_24h(end_hour, end_ampm) * 60 + end_minute_int
    if end_minute <= start_minute:
        return None

    return frozenset(days), start_minute, end_minute


def _parse_days(segment: str) -> set[str] | None:
    """Walk a day segment, normalizing ``Th`` → ``R``, ``Sa`` → ``S``, ``Su`` → ``U``.

    CU's real data uses ``Sa`` for Saturday (never bare ``S``) and
    ``Su`` for Sunday (never bare ``U``), so we recognize the two-char
    forms first. ``Th`` is the same pattern — it has to be handled
    before bare ``T`` so ``TTh`` parses as Tue+Thu rather than
    Tue+Tue+h-error.
    """
    days: set[str] = set()
    i = 0
    while i < len(segment):
        ch = segment[i]
        nxt = segment[i + 1] if i + 1 < len(segment) else ""
        if ch == "T" and nxt == "h":
            days.add("R")
            i += 2
            continue
        if ch == "S" and nxt == "a":
            days.add("S")
            i += 2
            continue
        if ch == "S" and nxt == "u":
            days.add("U")
            i += 2
            continue
        if ch in _VALID_DAY_CODES:
            days.add(ch)
            i += 1
            continue
        return None
    if not days:
        return None
    return days


def _parse_time(token: str) -> tuple[int, int, str | None] | None:
    """Parse ``9a`` / ``12:15p`` / ``1`` / ``1:25`` to ``(hour, minute, ampm)``.

    Returns ``(hour_12, minute, ampm)`` where ``ampm`` is ``"a"``, ``"p"``,
    or ``None`` if the token omitted the marker (CU convention: start
    tokens often inherit the end's marker, handled by ``_parse_meets``).
    Returns ``None`` for malformed tokens. Conversion to minutes-since
    midnight is deferred to the caller so marker inheritance can run
    before ``_to_24h``.
    """
    if not token:
        return None
    match = _TIME_RE.match(token)
    if match is None:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    ampm = match.group("ampm")  # ``"a"``, ``"p"``, or ``None``
    return hour, minute, ampm


def _to_24h(hour: int, ampm: str) -> int:
    """Convert a 12-hour clock hour + am/pm marker to a 0-23 hour."""
    if ampm == "a":
        return 0 if hour == 12 else hour
    return 12 if hour == 12 else hour + 12


def _time_overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """Strict-inequality overlap so adjacent times (one ends 11:00, next starts 11:00)
    are NOT a conflict — back-to-back classes are fine, the student just walks over."""
    return a_start < b_end and b_start < a_end
