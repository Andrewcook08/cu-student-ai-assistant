from __future__ import annotations

import re
from pathlib import Path

from data.ingest.ingest_courses import parse_classes

# ── Typo normalization ────────────────────────────────────────────────────────
# Known misspellings in the source data. Applied before any regex matching.
_TYPO_FIXES = {
    "prerequiste": "prerequisite",
    "prerequsite": "prerequisite",
    "prerequsites": "prerequisites",
    "prerequistes": "prerequisites",
}

# ── Regex patterns ────────────────────────────────────────────────────────────
# Full course code: "CSCI 1300", "APPM 2360"
_COURSE_CODE = re.compile(r"[A-Z]{2,4} \d{4}")

# Abbreviated code after "or"/"and": "or 3225", "and 3430"
_ABBREV_CODE = re.compile(r"(?:or|and) (\d{4})")

# Minimum grade extraction: "(minimum grade C-)", "(all minimum grade D-)",
# "(min grade of B+)", etc.
_MIN_GRADE = re.compile(
    r"(?:(?:all\s+)?min(?:imum)?\.?\s+(?:grade\s+)?(?:of\s+)?([A-Z][+-]?))",
    re.IGNORECASE,
)

# Restriction-only string (no prerequisite information)
_RESTRICTION_ONLY = re.compile(r"^Restricted to ", re.IGNORECASE)

# Strings that provide no parseable prerequisite info
_UNPARSEABLE = re.compile(
    r"^(?:Varies by section|May not be open|Nondegree students)",
    re.IGNORECASE,
)


def _normalize_typos(text: str) -> str:
    """Fix known typos in prerequisite strings."""
    for typo, fix in _TYPO_FIXES.items():
        text = text.replace(typo, fix)
    return text


def _extract_min_grade(text: str) -> str | None:
    """Extract the first minimum grade mentioned in the string."""
    m = _MIN_GRADE.search(text)
    if m:
        return m.group(1)
    return None


def _extract_course_codes(text: str, source_code: str) -> list[str]:
    """Extract all course codes from a prerequisite string.

    Handles both full codes ("CSCI 2270") and abbreviated codes ("or 2275")
    by expanding the abbreviated form using the most recently seen department.
    Excludes the source course itself from the result.
    """
    codes: list[str] = []
    last_dept: str | None = None

    # Tokenize to process left-to-right so we can track last_dept
    # We interleave full codes and abbreviated codes by position
    full_matches = [(m.start(), m.group()) for m in _COURSE_CODE.finditer(text)]
    abbrev_matches = [(m.start(), m.group(1)) for m in _ABBREV_CODE.finditer(text)]

    # Merge and sort by position
    events: list[tuple[int, str, bool]] = []  # (pos, value, is_full)
    for pos, code in full_matches:
        events.append((pos, code, True))
    for pos, num in abbrev_matches:
        events.append((pos, num, False))
    events.sort(key=lambda e: e[0])

    for _pos, value, is_full in events:
        if is_full:
            last_dept = value.split()[0]
            codes.append(value)
        elif last_dept is not None:
            # Check this isn't already captured as part of a full code
            expanded = f"{last_dept} {value}"
            if expanded not in codes:
                codes.append(expanded)

    # Remove source course code
    return [c for c in codes if c != source_code]


def _classify_type(text: str) -> str:
    """Classify prerequisite string as 'prerequisite' or 'corequisite'."""
    lower = text.lower()
    if "corequisite" in lower or "co-requisite" in lower or "coreq" in lower:
        return "corequisite"
    return "prerequisite"


def parse_prerequisites(courses: list[dict]) -> list[dict]:
    """Parse prerequisite strings from course data into structured edge records.

    Each edge represents a HAS_PREREQUISITE relationship in the graph:
    source_code -> target_code with type, min_grade, and raw_text.

    Courses with only restrictions (no course codes) or unparseable strings
    produce no edges. The raw_text is always preserved on every edge.

    Returns a list of edge dicts and prints a summary of parsing statistics.
    """
    edges: list[dict] = []
    stats = {"total": 0, "restriction_only": 0, "unparseable": 0, "parsed": 0, "no_codes": 0}

    for course in courses:
        raw = course.get("prerequisites_raw", "")
        if not raw:
            continue

        stats["total"] += 1
        text = _normalize_typos(raw)

        # Skip unparseable strings
        if _UNPARSEABLE.match(text):
            stats["unparseable"] += 1
            continue

        # Check if restriction-only (no course codes at all)
        has_codes = bool(_COURSE_CODE.search(text))

        if not has_codes:
            if _RESTRICTION_ONLY.match(text):
                stats["restriction_only"] += 1
            else:
                stats["unparseable"] += 1
            continue

        # Extract structured data
        source_code = course["code"]
        target_codes = _extract_course_codes(text, source_code)

        if not target_codes:
            stats["no_codes"] += 1
            continue

        stats["parsed"] += 1
        edge_type = _classify_type(text)
        min_grade = _extract_min_grade(text)

        for target in target_codes:
            edges.append({
                "source_code": source_code,
                "target_code": target,
                "type": edge_type,
                "min_grade": min_grade,
                "raw_text": raw,
            })

    parsed_rate = (stats["parsed"] / stats["total"] * 100) if stats["total"] else 0
    print(
        f"Prerequisites: {stats['total']} total, "
        f"{stats['parsed']} parsed ({parsed_rate:.1f}%), "
        f"{stats['restriction_only']} restriction-only, "
        f"{stats['unparseable']} unparseable, "
        f"{stats['no_codes']} no target codes, "
        f"{len(edges)} edges"
    )
    return edges


def write_neo4j_prerequisites(edges: list[dict]) -> None:
    """Write HAS_PREREQUISITE edges to Neo4j.

    TODO: Replace stub with neo4j driver MERGE queries once DATA-001 lands.
    Each edge becomes: (source:Course)-[:HAS_PREREQUISITE {type, min_grade, raw_text}]->
    (target:Course)
    """
    print(f"[STUB] Would write {len(edges)} HAS_PREREQUISITE edges to Neo4j")


def run() -> None:
    """Parse prerequisites from cu_classes.json and write to Neo4j."""
    path = Path(__file__).resolve().parents[1] / "cu_classes.json"
    courses, _ = parse_classes(path)
    edges = parse_prerequisites(courses)
    write_neo4j_prerequisites(edges)


if __name__ == "__main__":
    run()
