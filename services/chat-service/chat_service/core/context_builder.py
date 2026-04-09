"""LLM prompt context assembler for the chat service (CHAT-010 / CUAI-42).

Gathers context from Neo4j (Graph RAG) and Postgres (student profile),
wraps each source in XML delimiter tags for RAG context isolation
(SEC-001), and fits the result within a configurable token budget.

Security considerations
-----------------------
SEC-001 requires that retrieved data cannot inject fake XML tags into
the assembled context and trick the LLM into treating attacker-controlled
text as a trusted system section.  :func:`_sanitize_context_data` strips
any of the known delimiter tag names from retrieved text *before* wrapping
it, so a course description containing ``<system>…</system>`` cannot
escape its ``<retrieved_context>`` envelope.  The regex only targets the
specific known tag patterns (both opening and closing forms), so normal
angle-bracket usage such as ``x < 5`` or ``List[int]`` is left intact.

Token budgeting
---------------
Token counts are estimated conservatively as ``len(text) // 4``
(``CHARS_PER_TOKEN = 4``).  This under-estimates the true token count for
dense technical text, which is intentional: we prefer to leave headroom
rather than clip the LLM's context window.

Error handling
--------------
Individual retrieval failures (Postgres or Neo4j) are caught, logged at
WARNING level, and **not** propagated.  :func:`build_context` always
returns a :class:`ContextResult`, possibly with an empty or partial
``text`` field.  Callers that need to surface a database error to the
user should do so via a separate channel; the context builder's job is
to provide *whatever context is available*.

:class:`ContextBuilderError` is the base exception for any error that
*does* propagate (none today, reserved for future validation failures).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chat_service.core.intent_classifier import Intent
from chat_service.services import neo4j_service, postgres_service

logger = logging.getLogger(__name__)


# ─── Constants ──────────────────────────────────────────────────────────

DEFAULT_MAX_CONTEXT_TOKENS: int = 6000
CHARS_PER_TOKEN: int = 4


# ─── Exceptions ─────────────────────────────────────────────────────────


class ContextBuilderError(RuntimeError):
    """Base exception for context_builder failures."""


# ─── Result type ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ContextResult:
    """Assembled LLM prompt context with a conservative token estimate."""

    text: str
    token_estimate: int


# ─── Security: tag sanitization ─────────────────────────────────────────

#: Delimiter tag names used to wrap context sections.  Any of these appearing
#: inside retrieved data would let an attacker fake a trusted section header;
#: we strip them before wrapping.
_DELIMITER_TAGS: frozenset[str] = frozenset(
    {
        "user_profile",
        "retrieved_context",
        "conversation_summary",
        "user_message",
        "system",
        "assistant",
        "tool_result",
    }
)

# Build a single pattern that matches <tag>, </tag>, <tag/>, and
# <tag attr="..."> for every known delimiter.  The ``(?:\s[^>]*)?`` suffix
# allows optional attributes after at least one whitespace character, which
# catches ``<system role="admin">`` without falsely matching ``x < system``
# (no whitespace after "system" before ">").  Case-insensitive flag covers
# ``<SYSTEM>`` variants.
_DELIMITER_TAG_RE: re.Pattern[str] = re.compile(
    r"</?\s*(?:" + "|".join(re.escape(t) for t in _DELIMITER_TAGS) + r")(?:\s[^>]*)?\s*/?>",
    re.IGNORECASE,
)


def _sanitize_context_data(text: str) -> str:
    """Strip known delimiter tags from *text*.

    Only actual XML tag patterns (``<tag>``, ``</tag>``, ``<tag/>``) are
    removed.  Normal angle-bracket usage such as ``x < 5`` or generic type
    annotations is left intact.
    """
    return _DELIMITER_TAG_RE.sub("", text)


# ─── Token estimation ───────────────────────────────────────────────────


def _estimate_tokens(text: str) -> int:
    """Return a conservative token estimate: ``len(text) // CHARS_PER_TOKEN``."""
    return len(text) // CHARS_PER_TOKEN


# ─── Pure formatters ────────────────────────────────────────────────────


def _format_courses(courses: list[dict[str, Any]]) -> str:
    """Format a list of vector-search course results as a readable block."""
    if not courses:
        return ""
    lines: list[str] = []
    for course in courses:
        code = course.get("code", "")
        title = course.get("title", "")
        credits = course.get("credits", "")
        mode = course.get("instruction_mode", "")
        description = course.get("description", "") or ""
        score = course.get("score", 0.0)
        lines.append(f"Course: {code} — {title}")
        lines.append(f"Credits: {credits} | Mode: {mode}")
        lines.append(description)
        lines.append(f"Score: {score:.2f}")
        lines.append("")  # blank line separator
    # Drop the trailing blank entry
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _format_prereq_chain(chain: dict[str, Any]) -> str:
    """Format a prerequisite chain dict as a readable block."""
    course = chain.get("course")
    edges: list[dict[str, Any]] = chain.get("edges", [])

    if course is None:
        header = "Course not found."
    else:
        code = course.get("code", "")
        title = course.get("title", "")
        header = f"Prerequisites for {code} — {title}"

    lines: list[str] = [header]
    if not edges:
        lines.append("No prerequisites found.")
    else:
        for edge in edges:
            from_code = edge.get("from", "")
            to_code = edge.get("to", "")
            rel_type = edge.get("type", "")
            min_grade = edge.get("min_grade", "")
            raw_text = edge.get("raw_text")
            lines.append(f"{from_code} → {to_code} ({rel_type}, min grade: {min_grade})")
            if raw_text:
                lines.append(f"  Note: {raw_text}")
    return "\n".join(lines)


def _format_degree_requirements(data: dict[str, Any]) -> str:
    """Format a degree requirements dict as a readable block."""
    program = data.get("program")
    requirements: list[dict[str, Any]] = data.get("requirements", [])

    if program is None:
        return "Degree program not found."

    name = program.get("name", "")
    prog_type = program.get("type", "")
    total_credits = program.get("total_credits", "")
    lines: list[str] = [
        f"Program: {name}",
        f"Type: {prog_type} | Total credits: {total_credits}",
    ]

    for req in requirements:
        req_name = req.get("name", "")
        req_type = req.get("requirement_type", "")
        req_credits = req.get("credits", "")
        courses = req.get("courses", [])
        raw_text = req.get("raw_text")
        or_alt = req.get("or_alternative_to")
        header = f"\n{req_name} ({req_type}, {req_credits} credits)"
        if or_alt:
            header += f" [alternative to: {or_alt}]"
        lines.append(header)
        if courses:
            for c in courses:
                lines.append(f"  - {c.get('code', '')} {c.get('title', '')}")
        elif raw_text:
            lines.append(f"  {raw_text}")
        else:
            lines.append("  No courses listed.")

    return "\n".join(lines)


def _format_student_profile(data: dict[str, Any]) -> str:
    """Format a student profile dict as a readable block."""
    program = data.get("program")
    completed: list[dict[str, Any]] = data.get("completed", [])
    decisions: list[dict[str, Any]] = data.get("decisions", [])

    program_line = f"Program: {program}" if program else "Program: Not declared"
    lines: list[str] = [program_line]

    if completed:
        lines.append("\nCompleted courses:")
        for c in completed:
            code = c.get("course_code", "")
            grade = c.get("grade", "")
            lines.append(f"  {code}: {grade}")
    else:
        lines.append("\nCompleted courses: None on record")

    recent_decisions = decisions[:10]  # keep profile concise
    if recent_decisions:
        lines.append("\nRecent decisions:")
        for d in recent_decisions:
            code = d.get("course_code", "")
            dtype = d.get("decision_type", "")
            notes = d.get("notes") or ""
            created = d.get("created_at", "")
            entry = f"  {code}: {dtype}"
            if notes:
                entry += f" — {notes}"
            if created:
                entry += f" ({created})"
            lines.append(entry)

    return "\n".join(lines)


# ─── Intent-specific retrievers ──────────────────────────────────────────


async def _retrieve_for_course_search(
    neo4j_driver: AsyncDriver,
    query_embedding: list[float],
) -> str:
    """Return formatted course search results for the given embedding."""
    courses = await neo4j_service.vector_search(neo4j_driver, query_embedding, limit=10)
    return _format_courses(courses)


async def _retrieve_for_prereq_check(
    neo4j_driver: AsyncDriver,
    query_embedding: list[float] | None,
) -> str:
    """Return formatted prereq chain for the top vector-search hit.

    If no embedding is provided there is no way to identify which course
    the user is asking about, so we return an empty string and let the
    LLM ask for clarification.
    """
    if query_embedding is None:
        return ""

    courses = await neo4j_service.vector_search(neo4j_driver, query_embedding, limit=10)
    if not courses:
        return ""

    top_code: str = courses[0].get("code", "")
    parts: list[str] = []

    # Include the vector search results for context.
    courses_text = _format_courses(courses)
    if courses_text:
        parts.append(courses_text)

    # Fetch and format the prereq chain for the top hit.
    if top_code:
        chain = await neo4j_service.get_prerequisite_chain(neo4j_driver, top_code)
        chain_text = _format_prereq_chain(chain)
        if chain_text:
            parts.append(chain_text)

    return "\n\n".join(parts)


async def _retrieve_for_degree_planning(
    neo4j_driver: AsyncDriver,
    program_name: str | None,
) -> str:
    """Return formatted degree requirements for the student's program."""
    if not program_name:
        return ""
    data = await neo4j_service.get_degree_requirements(neo4j_driver, program_name)
    return _format_degree_requirements(data)


# ─── Budget assembly ────────────────────────────────────────────────────


def _wrap_section(
    tag: str,
    content: str,
    running_tokens: int,
    max_tokens: int,
) -> tuple[str | None, int]:
    """Sanitize *content*, wrap it in *tag*, and fit within *max_tokens*.

    Returns ``(wrapped_string, new_running_tokens)`` or ``(None, running_tokens)``
    when there is no room at all.  If the content must be truncated a
    ``\\n[...truncated]`` suffix is appended so the LLM knows the data is
    incomplete.
    """
    sanitized = _sanitize_context_data(content)
    open_tag = f"<{tag}>"
    close_tag = f"</{tag}>"
    tag_tokens = _estimate_tokens(open_tag + close_tag)
    content_tokens = _estimate_tokens(sanitized)
    available = max_tokens - running_tokens - tag_tokens

    if available <= 0:
        return None, running_tokens

    if content_tokens <= available:
        wrapped = f"{open_tag}{sanitized}{close_tag}"
        return wrapped, running_tokens + _estimate_tokens(wrapped)

    # Truncate content to fit.
    truncation_suffix = "\n[...truncated]"
    suffix_tokens = _estimate_tokens(truncation_suffix)
    char_budget = max(0, (available - suffix_tokens) * CHARS_PER_TOKEN)
    truncated = sanitized[:char_budget] + truncation_suffix
    wrapped = f"{open_tag}{truncated}{close_tag}"
    return wrapped, running_tokens + _estimate_tokens(wrapped)


def _assemble_with_budget(
    profile_text: str | None,
    summary_text: str | None,
    retrieved_text: str | None,
    max_tokens: int,
) -> ContextResult:
    """Assemble context sections in priority order within *max_tokens*.

    Priority:
    1. ``<user_profile>`` — truncated if it alone exceeds the budget
       (e.g. a student with 50+ completed courses).
    2. ``<conversation_summary>`` — truncated if remaining budget is tight.
    3. ``<retrieved_context>`` — truncated or skipped if budget is exhausted.

    Sections are joined with ``\\n\\n``.  The returned ``token_estimate``
    is computed from the final assembled text so it exactly matches the
    ``text`` field (including join separators).
    """
    sections: list[str] = []
    running_tokens = 0

    if profile_text:
        wrapped, running_tokens = _wrap_section(
            "user_profile",
            profile_text,
            running_tokens,
            max_tokens,
        )
        if wrapped:
            sections.append(wrapped)

    if summary_text:
        wrapped, running_tokens = _wrap_section(
            "conversation_summary",
            summary_text,
            running_tokens,
            max_tokens,
        )
        if wrapped:
            sections.append(wrapped)

    if retrieved_text:
        wrapped, running_tokens = _wrap_section(
            "retrieved_context",
            retrieved_text,
            running_tokens,
            max_tokens,
        )
        if wrapped:
            sections.append(wrapped)

    assembled = "\n\n".join(sections)
    return ContextResult(text=assembled, token_estimate=_estimate_tokens(assembled))


# ─── Public API ─────────────────────────────────────────────────────────


async def build_context(
    intent: Intent,
    user_id: int,
    *,
    query_embedding: list[float] | None = None,
    conversation_summary: str | None = None,
    neo4j_driver: AsyncDriver,
    postgres_sessionmaker: async_sessionmaker[AsyncSession],
    max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
) -> ContextResult:
    """Assemble LLM prompt context for a single chat turn.

    Fetches student profile data from Postgres and intent-appropriate
    graph data from Neo4j, then assembles them into a token-budgeted
    string of XML-delimited sections.

    Individual retrieval failures are caught and logged; the function
    always returns a :class:`ContextResult`.  If all sources fail, the
    returned ``text`` will be an empty string and ``token_estimate``
    will be 0.

    Parameters
    ----------
    intent:
        Routing signal from the intent classifier.
    user_id:
        Authenticated user identity (never taken from LLM output).
    query_embedding:
        Optional vector representation of the user's message; needed for
        Neo4j vector search.
    conversation_summary:
        Optional prior conversation summary for multi-turn continuity.
    neo4j_driver:
        Injected from application state.
    postgres_sessionmaker:
        Injected from application state.
    max_tokens:
        Token budget for the assembled context string.
    """
    # ── Step 1: Fetch student profile ────────────────────────────────────
    profile_data: dict[str, Any] | None = None
    try:
        async with postgres_sessionmaker() as session:
            profile_data = await postgres_service.get_student_data(session, user_id=user_id)
    except Exception as exc:
        logger.warning(
            "context_builder: failed to fetch student profile for user_id=%s: %s",
            user_id,
            exc,
        )

    profile_text: str | None = None
    if profile_data is not None:
        profile_text = _format_student_profile(profile_data)

    # ── Step 2: Intent-routed retrieval ──────────────────────────────────
    retrieved_text: str | None = None
    try:
        if intent is Intent.COURSE_SEARCH:
            if query_embedding is not None:
                retrieved_text = await _retrieve_for_course_search(neo4j_driver, query_embedding)
        elif intent is Intent.PREREQ_CHECK:
            retrieved_text = await _retrieve_for_prereq_check(neo4j_driver, query_embedding)
        elif intent is Intent.DEGREE_PLANNING:
            program_name = profile_data.get("program") if profile_data else None
            retrieved_text = await _retrieve_for_degree_planning(neo4j_driver, program_name)
        # SCHEDULE_HELP and GENERAL_QUESTION: profile is sufficient, no Neo4j call.
    except Exception as exc:
        logger.warning(
            "context_builder: retrieval failed for intent=%s user_id=%s: %s",
            intent,
            user_id,
            exc,
        )

    # ── Step 3: Assemble within token budget ─────────────────────────────
    return _assemble_with_budget(profile_text, conversation_summary, retrieved_text, max_tokens)
