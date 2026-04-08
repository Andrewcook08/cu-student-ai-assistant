"""LangChain tool definitions for the CU chat service (CHAT-005 / CUAI-37).

Exposes a single public entry point — :func:`make_tools` — which builds the
seven ``@tool``-decorated async functions and returns them as a
:class:`ToolSet`.  No module-level state lives here; all service handles are
injected by the factory so this module is trivially unit-testable.

Tool roster (order matches architecture.md § Tool Calling):

1. ``search_courses``        — vector similarity search in Neo4j
2. ``lookup_course``         — exact code lookup in Postgres
3. ``check_prerequisites``   — prerequisite chain from Neo4j
4. ``get_degree_requirements``— program requirements from Neo4j
5. ``get_student_profile``   — student data from Postgres (user_id injected)
6. ``find_schedule_conflicts``— time-conflict detection in Postgres
7. ``save_decision``         — append decision row in Postgres (user_id injected)

``user_id`` is annotated with :class:`~langchain_core.tools.InjectedToolArg`
on tools 5 and 7.  That annotation causes LangChain to strip ``user_id`` from
the JSON schema it sends to the LLM, so the model literally cannot supply or
forge it.  The tool executor (CHAT-006) injects the authenticated JWT subject
at call time via LangChain's standard injection mechanism.

Post-filtering note (``search_courses``):
    The ``department`` and ``instruction_mode`` parameters are applied as a
    Python list-comprehension post-filter on the ``vector_search`` results
    because structured filtering inside Neo4j's vector index is out of scope
    for CHAT-005.  A ``status`` filter is intentionally NOT exposed: status
    is a per-section attribute and ``neo4j_service.vector_search`` returns
    course-level rows only, so any status filter would be dead code that
    silently empties the result set.  Structured Neo4j filtering and
    section-level search are tracked as future work (CHAT-010 or similar).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

import httpx
from langchain_core.tools import BaseTool, InjectedToolArg
from langchain_core.tools import tool as lc_tool
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chat_service.services import neo4j_service, ollama_service, postgres_service

# ─── Public types ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ToolSet:
    """Container returned by :func:`make_tools`.

    Attributes
    ----------
    tools:
        List of all seven tools, ready to pass to ``llm.bind_tools(...)``.
    registry:
        Dict keyed by tool name for O(1) dispatch in CHAT-006's executor.
    """

    tools: list[BaseTool]
    registry: dict[str, BaseTool]


# ─── Factory ─────────────────────────────────────────────────────────────


def make_tools(
    *,
    neo4j_driver: AsyncDriver,
    postgres_sessionmaker: async_sessionmaker[AsyncSession],
    ollama_client: httpx.AsyncClient,
) -> ToolSet:
    """Build and return the full tool set with injected service handles.

    All seven tools are closures over the three service handles passed here.
    No globals, no module-level state — call this once from ``main.py``
    lifespan and store the result on ``app.state``.

    Parameters
    ----------
    neo4j_driver:
        Long-lived ``AsyncDriver`` from ``main.py`` lifespan.
    postgres_sessionmaker:
        ``async_sessionmaker`` constructed from the long-lived
        ``AsyncEngine``.  Each tool opens its own session with
        ``async with postgres_sessionmaker() as session:``.
    ollama_client:
        Long-lived ``httpx.AsyncClient`` pointed at the Ollama base URL.
    """

    # ── 1. search_courses ───────────────────────────────────────────────

    @lc_tool
    async def search_courses(
        query: str,
        department: str | None = None,
        instruction_mode: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for courses by keyword, topic, or description.

        Use this tool when the student gives you a name, topic, or natural
        language description — e.g. "machine learning electives" or "intro
        physics".  For an exact code like "CSCI 2270", use ``lookup_course``
        instead.

        Optional filters narrow the results in Python after vector search
        (Neo4j structured filtering is future work): ``department`` matches
        the ``code`` prefix (e.g. "CSCI"), ``instruction_mode`` matches the
        course mode (e.g. "In-Person").  Omit any filter you don't need.
        """
        embedding = await ollama_service.get_embedding(ollama_client, query)
        results: list[dict[str, Any]] = await neo4j_service.vector_search(
            neo4j_driver, embedding, limit=10
        )

        # Post-filter in Python: structured filtering inside the Neo4j
        # vector index is out of scope for CHAT-005 (see module docstring).
        if department is not None:
            results = [r for r in results if (r.get("code") or "").startswith(department)]
        if instruction_mode is not None:
            results = [r for r in results if r.get("instruction_mode") == instruction_mode]

        return results

    # ── 2. lookup_course ────────────────────────────────────────────────

    @lc_tool
    async def lookup_course(course_code: str) -> dict[str, Any]:
        """Get full details for a course by its exact code (e.g. "CSCI 2270").

        Use this tool when you already have a specific course code.  Returns
        sections, prerequisite text, topic titles, and gen-ed attributes.
        If you only have a course name or topic, use ``search_courses`` first
        to obtain the code.  Returns an error dict (not an exception) if the
        code is not found — you can try ``search_courses`` in that case.
        """
        async with postgres_sessionmaker() as session:
            result = await postgres_service.lookup_course(session, course_code=course_code)

        if result is None:
            return {"error": "Course not found", "course_code": course_code}
        return result

    # ── 3. check_prerequisites ──────────────────────────────────────────

    @lc_tool
    async def check_prerequisites(course_code: str) -> dict[str, Any]:
        """Get the full prerequisite chain for a course.

        Returns every ``HAS_PREREQUISITE`` edge reachable from *course_code*
        up to five hops deep, along with the raw prerequisite text for any
        edge whose type is ambiguous.  Use this to verify whether the student
        has satisfied all requirements before recommending the course.
        """
        return await neo4j_service.get_prerequisite_chain(neo4j_driver, course_code)

    # ── 4. get_degree_requirements ──────────────────────────────────────

    @lc_tool
    async def get_degree_requirements(program: str) -> dict[str, Any]:
        """Get all requirements for a degree program with satisfying courses.

        Returns the full requirement set for *program* (e.g. "Computer
        Science - Bachelor of Arts (BA)"), including required courses,
        or-alternatives, choose-N groups, and the courses that satisfy each
        requirement.  Pair with ``get_student_profile`` to see which
        requirements the student has already completed.
        """
        return await neo4j_service.get_degree_requirements(neo4j_driver, program)

    # ── 5. get_student_profile ──────────────────────────────────────────

    @lc_tool
    async def get_student_profile(
        user_id: Annotated[str, InjectedToolArg],
    ) -> dict[str, Any]:
        """Get the student's declared program, completed courses, and prior decisions.

        Returns program name, a list of completed courses with grades (for
        checking prerequisite minimums), and prior planning decisions.
        The ``user_id`` is injected from the authenticated session — do not
        include it in your tool call.
        """
        async with postgres_sessionmaker() as session:
            return await postgres_service.get_student_data(session, user_id=int(user_id))

    # ── 6. find_schedule_conflicts ──────────────────────────────────────

    @lc_tool
    async def find_schedule_conflicts(course_codes: list[str]) -> list[dict[str, Any]]:
        """Check for time conflicts between a set of courses.

        Pass a list of course codes (e.g. ``["CSCI 2270", "MATH 2400"]``).
        Returns one entry per conflicting section pair, with the overlapping
        days and raw ``meets`` strings.  An empty list means no conflicts
        were detected.  Sections with unparseable or unscheduled meeting
        times are silently skipped.
        """
        async with postgres_sessionmaker() as session:
            return await postgres_service.get_schedule_conflicts(session, course_codes=course_codes)

    # ── 7. save_decision ────────────────────────────────────────────────

    @lc_tool
    async def save_decision(
        course_code: str,
        decision_type: str,
        notes: str | None = None,
        *,
        user_id: Annotated[str, InjectedToolArg],
    ) -> dict[str, Any]:
        """Save a student's course planning decision for future reference.

        Records the student's intent for *course_code*.  ``decision_type``
        must be one of ``"planned"``, ``"interested"``, or
        ``"not_interested"``.  ``notes`` is optional free text.  The
        ``user_id`` is injected from the authenticated session — do not
        include it in your tool call.  Decisions are append-only; calling
        this again with the same course records a new entry rather than
        overwriting the previous one.
        """
        async with postgres_sessionmaker() as session:
            return await postgres_service.save_student_decision(
                session,
                user_id=int(user_id),
                course_code=course_code,
                decision_type=decision_type,
                notes=notes,
            )

    # ── Assemble ToolSet ─────────────────────────────────────────────────

    tool_list: list[BaseTool] = [
        search_courses,
        lookup_course,
        check_prerequisites,
        get_degree_requirements,
        get_student_profile,
        find_schedule_conflicts,
        save_decision,
    ]
    registry: dict[str, BaseTool] = {t.name: t for t in tool_list}
    return ToolSet(tools=tool_list, registry=registry)
