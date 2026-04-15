"""LangChain tool definitions for the CU chat service (CHAT-005 / CUAI-37).

Exposes a single public entry point — :func:`make_tools` — which builds the
eight ``@tool``-decorated async functions and returns them as a
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
8. ``remove_decision``       — delete decision rows in Postgres (user_id injected)

``user_id`` is annotated with :class:`~langchain_core.tools.InjectedToolArg`
on tools 5, 7, and 8.  That annotation causes LangChain to strip ``user_id``
from the JSON schema it sends to the LLM, so the model literally cannot supply or
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

        Results include course code, title, credits, description, and instruction
        mode, but NOT prerequisites or section-level availability.  Follow up
        with ``lookup_course`` for full section details and ``check_prerequisites``
        before recommending any result to the student.
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

        # Trim descriptions to reduce context window usage — the LLM
        # only needs a snippet to decide which courses to investigate
        # further via lookup_course.
        for r in results:
            desc = r.get("description") or ""
            if len(desc) > 120:
                r["description"] = desc[:120] + "…"
            r.pop("score", None)

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

        The returned sections include a ``status`` field (e.g. "Open", "Closed",
        "Waitlisted").  Check section status before recommending a course — a
        course with all sections Closed or Cancelled may not be available.
        The ``meets`` field shows meeting times (days + time range).

        Sections have a ``type`` field: LEC (lecture), REC (recitation), LAB,
        SEM (seminar), etc.  Students typically register for one LEC section
        plus one REC or LAB section.  When recommending, group LEC + REC/LAB
        together and check conflicts for both.  Don't list recitation sections
        as standalone course options.
        """
        async with postgres_sessionmaker() as session:
            result = await postgres_service.lookup_course(session, course_code=course_code)

        if result is None:
            return {"error": "Course not found", "course_code": course_code}

        # Trim the result to reduce context window usage.  The LLM needs
        # code, title, credits, prereq text, and section availability —
        # not full descriptions, topic lists, or gen-ed attributes.
        sections = result.get("sections") or []
        open_sections = [s for s in sections if s.get("status") == "Open"]
        trimmed: dict[str, Any] = {
            "code": result["code"],
            "title": result["title"],
            "credits": result["credits"],
            "prerequisites_raw": result.get("prerequisites_raw"),
            "instruction_mode": result.get("instruction_mode"),
            "total_sections": len(sections),
            "open_sections": len(open_sections),
        }
        # Include meeting times for up to 3 open sections so the LLM
        # can mention availability without the full section dump.
        if open_sections:
            trimmed["sample_sections"] = [
                {
                    "section": s["section_number"],
                    "type": s.get("type", ""),
                    "meets": s["meets"],
                    "instructor": s["instructor"],
                }
                for s in open_sections[:3]
            ]
        return trimmed

    # ── 3. check_prerequisites ──────────────────────────────────────────

    @lc_tool
    async def check_prerequisites(course_code: str) -> dict[str, Any]:
        """Get the full prerequisite chain for a course.

        Returns every ``HAS_PREREQUISITE`` edge reachable from *course_code*
        up to five hops deep, along with the raw prerequisite text for any
        edge whose type is ambiguous.  Use this to verify whether the student
        has satisfied all requirements before recommending the course.

        Each edge in the returned chain includes a ``min_grade`` field (e.g. "C").
        Compare this against the student's actual grade from ``get_student_profile``
        — a grade below ``min_grade`` means the prerequisite is NOT met.  Grade
        ordering: A > A- > B+ > B > B- > C+ > C > C- > D+ > D > D- > F.
        A "D" does NOT satisfy a "C" minimum.
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

        This is typically the starting point for a planning conversation.  After
        identifying remaining requirements, use ``search_courses`` to find courses
        that satisfy them, then ``check_prerequisites`` to verify eligibility.
        """
        result = await neo4j_service.get_degree_requirements(neo4j_driver, program)

        # Trim raw_text from each requirement to reduce context window
        # usage.  The structured fields (name, type, credits, courses)
        # are sufficient for planning; raw_text is verbose catalog prose.
        for req in result.get("requirements") or []:
            req.pop("raw_text", None)

        return result

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

        Call this tool EARLY in any advising conversation — before making course
        recommendations, checking prerequisites, or building schedules.  The
        student's completed courses and grades are essential for determining
        prerequisite eligibility and remaining degree requirements.
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

        IMPORTANT: Always include the student's currently planned/saved courses
        (from get_student_profile decisions) in the list along with any new
        candidates.  The goal is to check new courses against the student's
        existing schedule, not just against each other.

        Call this as a final validation step after selecting a set of courses for
        a schedule.  If conflicts are found, suggest removing one of the
        conflicting courses or choosing a different section.
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

        Offer to call this when the student explicitly commits to a course
        (e.g. "yes, I'll take that" or "add it to my plan").  Do NOT call this
        speculatively — only when the student has clearly decided.
        """
        async with postgres_sessionmaker() as session:
            return await postgres_service.save_student_decision(
                session,
                user_id=int(user_id),
                course_code=course_code,
                decision_type=decision_type,
                notes=notes,
            )

    # ── 8. remove_decision ─────────────────────────────────────────────

    @lc_tool
    async def remove_decision(
        course_code: str,
        *,
        user_id: Annotated[str, InjectedToolArg],
    ) -> dict[str, Any]:
        """Remove a student's saved decision for a course.

        Deletes all decision records for *course_code* belonging to the
        authenticated student.  The ``user_id`` is injected from the
        session — do not include it in your tool call.

        Call this when the student explicitly asks to remove a course from
        their plan (e.g. "remove CSCI 3104" or "I don't want that one
        anymore").  Do NOT call this unless the student clearly asks.
        """
        async with postgres_sessionmaker() as session:
            return await postgres_service.remove_student_decision(
                session,
                user_id=int(user_id),
                course_code=course_code,
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
        remove_decision,
    ]
    registry: dict[str, BaseTool] = {t.name: t for t in tool_list}
    return ToolSet(tools=tool_list, registry=registry)
