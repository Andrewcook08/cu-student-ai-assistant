"""Intent classifier for the chat service (CHAT-007 / CUAI-39).

Maps a raw user message into one of five :class:`Intent` values so the
LangGraph engine (CHAT-008) can pick the right system prompt and
retrieval strategy.

Approach: hybrid heuristic-first, optional LLM fallback.

- A pure regex/keyword pass runs first.  It is instant, deterministic,
  trivially testable, and has no Ollama dependency.  All five Jira
  acceptance examples must hit this path so unit tests don't need
  Ollama.
- If the heuristic returns :data:`Intent.GENERAL_QUESTION` and an
  ``ollama_client`` was supplied, a single LLM call is made to
  ``ollama_service.chat_completion`` as a fallback.  Any failure (timeout,
  malformed response, unknown label) collapses back to
  :data:`Intent.GENERAL_QUESTION` — :func:`classify_intent` never raises.

The :class:`Intent` enum subclasses ``str`` so it serialises cleanly
into LangGraph state and JSON.
"""

from __future__ import annotations

import json
import logging
import re
from enum import StrEnum
from typing import Any

import httpx

from chat_service.services.ollama_service import OllamaError, chat_completion

logger = logging.getLogger(__name__)


class Intent(StrEnum):
    """User-message intent categories used to route the chat pipeline.

    Subclasses :class:`enum.StrEnum` (Python 3.11+) so values serialise
    cleanly into LangGraph state and JSON without any custom encoder.
    """

    COURSE_SEARCH = "course_search"
    PREREQ_CHECK = "prereq_check"
    DEGREE_PLANNING = "degree_planning"
    SCHEDULE_HELP = "schedule_help"
    GENERAL_QUESTION = "general_question"


# ─── Compiled patterns ───────────────────────────────────────────────────

# Course code like "CSCI 2270", "MATH3140", "appm 4570" — matched against
# an uppercased copy of the message so the pattern itself stays simple.
_COURSE_CODE_RE = re.compile(r"\b[A-Z]{2,4}\s*\d{3,4}\b")

# Prereq keywords — any one of these is a strong hit on its own.
_PREREQ_KEYWORDS = (
    "prereq",
    "prerequisite",
    "prerequisites",
    "pre-req",
    "pre req",
)

# Schedule keywords — kept narrow on purpose so "what classes do I need"
# doesn't get pulled in here (that's degree planning).
_SCHEDULE_KEYWORDS = (
    "schedule",
    "conflict",
    "overlap",
    "time slot",
    "meeting time",
    "time conflict",
)

# Degree planning keywords.
_DEGREE_KEYWORDS = (
    "degree",
    "major",
    "minor",
    "graduate",
    "graduation",
    "requirement",
    "requirements",
    "program",
    "track",
    "concentration",
    "gen ed",
    "gen-ed",
)

# Course search keywords (course code presence is handled separately).
_COURSE_SEARCH_KEYWORDS = (
    "course",
    "class",
    "classes",
    "elective",
    "electives",
    "find",
    "search",
    "offered",
    "available",
)

_FALLBACK_SYSTEM_PROMPT = (
    "You are an intent classifier for a university course-planning assistant. "
    "Classify the user's message into exactly one of these intents:\n"
    "- course_search: looking up courses or electives by topic, department, "
    "name, or filters (e.g. 'what CS electives are there?').\n"
    "- prereq_check: asking about prerequisites or what is required before a "
    "specific course (e.g. 'what are the prereqs for CSCI 3104?').\n"
    "- degree_planning: questions about majors, minors, degree requirements, "
    "graduation, or programs (e.g. 'what do I need for my CS degree?').\n"
    "- schedule_help: time conflicts, overlaps, or scheduling specific course "
    "sections (e.g. 'do these two classes conflict?').\n"
    "- general_question: anything else, including off-topic or chit-chat.\n"
    "Respond with a JSON object matching the provided schema."
)


def _build_intent_schema() -> dict[str, Any]:
    """Build the JSON schema Ollama uses for constrained decoding.

    Single source of truth: derived from :class:`Intent` so adding a new
    intent automatically updates the schema. The ``enum`` constraint is
    what Ollama applies as a logit mask, guaranteeing the model can only
    emit one of the five labels.
    """
    return {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": [intent.value for intent in Intent],
            },
        },
        "required": ["intent"],
    }


_INTENT_SCHEMA = _build_intent_schema()
_DETERMINISTIC_OPTIONS = {"temperature": 0}


def _heuristic_classify(message: str) -> Intent:
    """Pure heuristic pass. First match wins. Order matters."""
    lowered = message.lower()
    upper = message.upper()
    has_course_code = _COURSE_CODE_RE.search(upper) is not None

    # 1. PREREQ_CHECK — any prereq keyword is a strong signal on its own.
    if any(kw in lowered for kw in _PREREQ_KEYWORDS):
        return Intent.PREREQ_CHECK
    # Backup phrasing: "need to take X before Y" with a course code present.
    if has_course_code and (
        "need to take" in lowered or ("need" in lowered and "before" in lowered)
    ):
        return Intent.PREREQ_CHECK
    # "requirements for CSCI 3104" is a prereq question, not degree planning —
    # the course code is the disambiguator. Without a code, "requirements"
    # falls through to the degree rule below.
    if has_course_code and "requirement" in lowered:
        return Intent.PREREQ_CHECK

    # 2. SCHEDULE_HELP — narrow keyword set.
    if any(kw in lowered for kw in _SCHEDULE_KEYWORDS):
        return Intent.SCHEDULE_HELP

    # 3. DEGREE_PLANNING — degree/major/requirement vocabulary.
    if any(kw in lowered for kw in _DEGREE_KEYWORDS):
        return Intent.DEGREE_PLANNING

    # 4. COURSE_SEARCH — keywords, or a bare course code with no other context.
    if any(kw in lowered for kw in _COURSE_SEARCH_KEYWORDS):
        return Intent.COURSE_SEARCH
    if has_course_code:
        return Intent.COURSE_SEARCH

    # 5. Fallthrough.
    return Intent.GENERAL_QUESTION


def _parse_llm_label(content: str) -> Intent:
    """Parse a raw LLM response into an :class:`Intent`.

    Tolerates the small mutations gpt-oss-tier models routinely add even
    when the system prompt says "ONLY the label": surrounding
    whitespace, case, trailing punctuation, ``-`` / space variants of
    the underscore separator, and wrapper phrasing like
    ``"Intent: course_search"`` or ``"The answer is course_search."``.
    Returns :data:`Intent.GENERAL_QUESTION` for any unknown / empty
    label.
    """
    normalized = content.strip().lower().strip(" .,!?;:'\"\n\t")
    normalized = normalized.replace("-", "_").replace(" ", "_")
    try:
        return Intent(normalized)
    except ValueError:
        pass
    # Wrapper-format fallback: scan for any known label as a substring.
    # Order Intent members by descending value length so "prereq_check"
    # wins over a hypothetical shorter prefix collision (none today, but
    # cheap insurance).
    for intent in sorted(Intent, key=lambda i: -len(i.value)):
        if intent.value in normalized:
            return intent
    return Intent.GENERAL_QUESTION


async def classify_intent(
    message: str,
    *,
    ollama_client: httpx.AsyncClient | None = None,
) -> Intent:
    """Classify *message* into one of the five :class:`Intent` values.

    The function is async even though the heuristic path is synchronous so
    that callers in the LangGraph engine can ``await`` it uniformly with
    other I/O nodes.

    Empty or whitespace-only input always returns
    :data:`Intent.GENERAL_QUESTION`.  When *ollama_client* is provided and
    the heuristic returns :data:`Intent.GENERAL_QUESTION`, a single LLM
    call is made as a fallback; any failure collapses back to
    :data:`Intent.GENERAL_QUESTION`.  This function never raises.
    """
    if not message or not message.strip():
        return Intent.GENERAL_QUESTION

    intent = _heuristic_classify(message)
    if intent is not Intent.GENERAL_QUESTION:
        return intent

    if ollama_client is None:
        return Intent.GENERAL_QUESTION

    try:
        response = await chat_completion(
            ollama_client,
            [
                {"role": "system", "content": _FALLBACK_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            format=_INTENT_SCHEMA,
            options=_DETERMINISTIC_OPTIONS,
        )
        content = response.get("content") or ""
        if not content:
            return Intent.GENERAL_QUESTION
        # Happy path: structured output yields {"intent": "<label>"}.
        # Fall back to the lenient text parser if the JSON shape is wrong
        # so a misbehaving Ollama version (or a future schema mismatch)
        # still degrades gracefully instead of dropping the request.
        try:
            payload = json.loads(content)
            label = payload.get("intent", "") if isinstance(payload, dict) else ""
            if isinstance(label, str) and label:
                return _parse_llm_label(label)
        except (json.JSONDecodeError, TypeError):
            pass
        return _parse_llm_label(content)
    except OllamaError as exc:
        logger.debug("LLM intent fallback failed: %s", exc)
        return Intent.GENERAL_QUESTION
    except Exception as exc:  # pragma: no cover - defensive last resort
        logger.debug("Unexpected error in LLM intent fallback: %s", exc)
        return Intent.GENERAL_QUESTION
