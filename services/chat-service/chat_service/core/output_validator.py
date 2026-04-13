"""Output validator for LLM responses (SEC-003 / CUAI-62).

Applies three layers of validation to LLM output before it reaches
the frontend:

1. **Schema enforcement** — validates ``structured_data`` against
   ``CourseCard`` and ``suggested_actions`` against ``Action``.
   Strips invalid entries.
2. **PII scanning** — detects email addresses, CU student ID patterns,
   phone numbers, and SSN fragments in reply text and structured-data
   descriptions.  Redacts matches with ``[REDACTED]``.
3. **Scope check** — detects content outside academic advising (shell
   commands, SQL statements, system paths).  Flags but does not strip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from shared.schemas import Action, CourseCard

# ─── Constants ─────────────────────────────────────────────────────────

#: Replacement token for all redacted PII matches.
_PII_REDACTION: str = "[REDACTED]"

# ─── Compiled patterns ─────────────────────────────────────────────────

#: Email addresses.
_EMAIL_PATTERN: re.Pattern[str] = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

#: CU student ID patterns — 7-9 digit standalone numbers.
_STUDENT_ID_PATTERN: re.Pattern[str] = re.compile(r"\b\d{7,9}\b")

#: US phone numbers in common formats.
_PHONE_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
)

#: Social Security Number fragments (e.g. 123-45-6789).
_SSN_PATTERN: re.Pattern[str] = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

#: Out-of-scope content patterns — multi-word to avoid false positives
#: with academic language (e.g. "drop" in "drop a course").
_SCOPE_PATTERNS: re.Pattern[str] = re.compile(
    r"(?i)"
    r"(?:"
    r"sudo\s"
    r"|rm\s+-rf"
    r"|chmod\s"
    r"|DROP\s+TABLE"
    r"|DELETE\s+FROM"
    r"|INSERT\s+INTO"
    r"|/etc/passwd"
    r"|C:\\Windows"
    r")"
)


# ─── Result type ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of :func:`validate_output`."""

    reply: str
    structured_data: list[dict[str, Any]]
    suggested_actions: list[dict[str, Any]]
    pii_detected: bool
    pii_redacted_count: int
    scope_violation_detected: bool
    invalid_cards_stripped: int
    invalid_actions_stripped: int


# ─── Private helpers ───────────────────────────────────────────────────


def _scan_and_redact_pii(text: str) -> tuple[str, int]:
    """Replace PII matches in *text* with :data:`_PII_REDACTION`.

    Applies patterns in order: SSN, phone, email, student ID.  Returns
    the cleaned text and the total number of substitutions made.
    """
    total = 0
    for pattern in (_SSN_PATTERN, _PHONE_PATTERN, _EMAIL_PATTERN, _STUDENT_ID_PATTERN):
        text, n = pattern.subn(_PII_REDACTION, text)
        total += n
    return text, total


def _validate_structured_data(
    items: list[dict[str, Any]],
    schema_class: type[CourseCard] | type[Action],
) -> tuple[list[dict[str, Any]], int, int]:
    """Validate each dict against *schema_class* and strip invalid entries.

    For :class:`~shared.schemas.CourseCard`:
    - Filters dict keys to those declared in ``model_fields``.
    - Requires ``code`` and ``title`` to be present.
    - Runs PII scanning on ``description`` and ``topic_titles`` string fields.

    For :class:`~shared.schemas.Action`:
    - Requires ``type`` and ``label`` to be present.

    Returns a ``(valid_items, stripped_count, pii_redacted_count)`` tuple.
    """
    valid: list[dict[str, Any]] = []
    stripped = 0
    pii_count = 0

    for item in items:
        if not isinstance(item, dict):
            stripped += 1
            continue

        if schema_class is CourseCard:
            # Filter to known fields only
            allowed = set(CourseCard.model_fields.keys())
            filtered = {k: v for k, v in item.items() if k in allowed}

            # Require mandatory fields
            if not filtered.get("code") or not filtered.get("title"):
                stripped += 1
                continue

            # Validate against Pydantic model
            try:
                card = CourseCard(**filtered).model_dump(exclude_none=True)
            except Exception:
                stripped += 1
                continue

            # PII scan on text fields
            for field in ("description", "topic_titles"):
                value = card.get(field)
                if isinstance(value, str):
                    cleaned, n = _scan_and_redact_pii(value)
                    card[field] = cleaned
                    pii_count += n

            valid.append(card)

        else:  # Action
            try:
                action = Action(**item).model_dump(exclude_none=True)
            except Exception:
                stripped += 1
                continue
            valid.append(action)

    return valid, stripped, pii_count


def _check_scope(text: str) -> bool:
    """Return ``True`` if *text* contains any out-of-scope content pattern."""
    return bool(_SCOPE_PATTERNS.search(text))


# ─── Public API ────────────────────────────────────────────────────────


def validate_output(
    reply: str,
    structured_data: list[dict[str, Any]],
    suggested_actions: list[dict[str, Any]] | None = None,
) -> ValidationResult:
    """Validate and sanitize LLM output before it reaches the frontend.

    Runs schema enforcement, PII redaction, and scope checking in sequence.
    Returns a :class:`ValidationResult` with the cleaned payload and
    metadata flags.
    """
    if suggested_actions is None:
        suggested_actions = []

    total_pii = 0

    # 1. Schema enforcement
    clean_cards, invalid_cards, card_pii = _validate_structured_data(structured_data, CourseCard)
    total_pii += card_pii

    clean_actions, invalid_actions, _ = _validate_structured_data(suggested_actions, Action)

    # 2. PII scan on reply text
    clean_reply, reply_pii = _scan_and_redact_pii(reply)
    total_pii += reply_pii

    # 3. Scope check on reply text
    scope_violation = _check_scope(clean_reply)

    return ValidationResult(
        reply=clean_reply,
        structured_data=clean_cards,
        suggested_actions=clean_actions,
        pii_detected=total_pii > 0,
        pii_redacted_count=total_pii,
        scope_violation_detected=scope_violation,
        invalid_cards_stripped=invalid_cards,
        invalid_actions_stripped=invalid_actions,
    )
