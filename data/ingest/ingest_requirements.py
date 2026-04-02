from __future__ import annotations

import json
import re
from pathlib import Path


def classify_requirement(req_id: str) -> str:
    """Classify a requirement id into a canonical type string.

    Classification is order-dependent; the first match wins:
    1. total_credits  — exact string "Total Credit Hours"
    2. or_alternative — starts with "or" followed by an uppercase letter
    3. corequisite_bundle — contains "&" and a course-code-like pattern
    4. choose_n       — case-insensitive keyword match
    5. cross_listed   — compact form  MATH/STAT 4520
    6. cross_listed   — expanded form APPM 3570/STAT 3100
    7. required       — standard course code
    8. elective       — everything else
    """
    if req_id == "Total Credit Hours":
        return "total_credits"

    if re.match(r"^or[A-Z]", req_id):
        return "or_alternative"

    if "&" in req_id and re.search(r"[A-Z]{2,6}\s+\d{4}", req_id):
        return "corequisite_bundle"

    lower = req_id.lower()
    if any(kw in lower for kw in ("choose", "select", "of the following", "from the following")):
        return "choose_n"

    if re.match(r"^[A-Z]{2,6}(/[A-Z]{2,6})+\s+\d{4}$", req_id):
        return "cross_listed"

    if re.match(r"^[A-Z]{2,6}\s+\d{4}(/[A-Z]{2,6}\s+\d{4})+$", req_id):
        return "cross_listed"

    if re.match(r"^[A-Z]{2,6}\s+\d{4}$", req_id):
        return "required"

    return "elective"


def _expand_segment(segment: str) -> list[str]:
    """Expand a single segment into a list of normalised course codes."""
    # Strip leading "or" prefix when followed by an uppercase letter
    seg = re.sub(r"^or(?=[A-Z])", "", segment).strip()

    # Skip non-course entries
    if not re.search(r"[A-Z]{2,6}\s+\d{4}", seg):
        return []

    # Compact cross-list: MATH/STAT 4520  →  ["MATH 4520", "STAT 4520"]
    m = re.match(r"^((?:[A-Z]{2,6}/)+[A-Z]{2,6})\s+(\d{4})$", seg)
    if m:
        depts = m.group(1).split("/")
        number = m.group(2)
        return [f"{dept} {number}" for dept in depts]

    # Expanded cross-list: APPM 3570/STAT 3100  →  ["APPM 3570", "STAT 3100"]
    # Also handles same-dept multi-number: ECEN 4322/5322  →  ["ECEN 4322", "ECEN 5322"]
    if "/" in seg:
        parts = seg.split("/")
        # Try to parse as DEPT NUMBER(/DEPT NUMBER)+
        courses = []
        last_dept = None
        valid = True
        for part in parts:
            part = part.strip()
            full = re.match(r"^([A-Z]{2,6})\s+(\d{4})$", part)
            if full:
                last_dept = full.group(1)
                courses.append(f"{last_dept} {full.group(2)}")
            else:
                # Bare number — reuse last dept (same-dept multi-number)
                bare = re.match(r"^(\d{4})$", part)
                if bare and last_dept:
                    courses.append(f"{last_dept} {bare.group(1)}")
                else:
                    valid = False
                    break
        if valid and courses:
            return courses

    # Standard course code
    m = re.match(r"^[A-Z]{2,6}\s+\d{4}$", seg)
    if m:
        return [seg]

    return []


def parse_course_codes(req_id: str) -> list[str]:
    """Return a list of normalised course codes extracted from *req_id*.

    Returns an empty list for total_credits and choose_n entries, and for
    anything that contains no recognisable course-code pattern.
    """
    req_type = classify_requirement(req_id)

    if req_type in ("total_credits", "choose_n", "elective"):
        return []

    # Split bundles on "&", otherwise treat as a single segment
    segments = req_id.split("&") if req_type == "corequisite_bundle" else [req_id]

    codes: list[str] = []
    for seg in segments:
        codes.extend(_expand_segment(seg.strip()))
    return codes


def parse_degree_type(program_name: str) -> tuple[str, str]:
    """Split *program_name* on the last " - " into (name_clean, degree_type).

    Returns ``(program_name, "Unknown")`` when no separator is present.
    """
    parts = program_name.rsplit(" - ", maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return program_name, "Unknown"


def parse_requirements(path: Path) -> tuple[list[dict], list[dict]]:
    """Parse *cu_degree_requirements.json* into flat program and requirement lists.

    Returns
    -------
    programs : list[dict]
        Keys: program_name, name_clean, degree_type, total_credits, requirement_count
    requirements : list[dict]
        Keys: program_name, position, requirement_type, raw_id, name,
              course_codes, credits_text, or_predecessor_position
    """
    data: list[dict] = json.loads(path.read_text())

    programs: list[dict] = []
    requirements: list[dict] = []

    credits_pattern = re.compile(r"^\d+(-\d+)?$")

    for program_obj in data:
        program_name: str = program_obj["program"]
        name_clean, degree_type = parse_degree_type(program_name)

        total_credits: str | None = None
        req_count = 0
        last_non_or_position: int | None = None

        for position, req in enumerate(program_obj["requirements"]):
            raw_id: str = req["id"]
            name: str = req["name"]
            req_type = classify_requirement(raw_id)
            course_codes = parse_course_codes(raw_id)
            credits_text = name if credits_pattern.match(name) else ""

            if req_type == "total_credits":
                total_credits = name
                or_predecessor_position = None
            elif req_type == "or_alternative":
                or_predecessor_position = last_non_or_position
            else:
                last_non_or_position = position
                or_predecessor_position = None

            if req_type != "total_credits":
                req_count += 1

            requirements.append(
                {
                    "program_name": program_name,
                    "position": position,
                    "requirement_type": req_type,
                    "raw_id": raw_id,
                    "name": name,
                    "course_codes": course_codes,
                    "credits_text": credits_text,
                    "or_predecessor_position": or_predecessor_position,
                }
            )

        programs.append(
            {
                "program_name": program_name,
                "name_clean": name_clean,
                "degree_type": degree_type,
                "total_credits": total_credits,
                "requirement_count": req_count,
            }
        )

    return programs, requirements


def write_postgres(programs: list[dict], requirements: list[dict]) -> None:
    """Write programs and requirements to PostgreSQL.

    TODO: Replace stub once INFRA-002 lands.
    """
    req_count = len(requirements)
    print(f"[STUB] Would write {len(programs)} programs and {req_count} requirements to PostgreSQL")


def write_neo4j(programs: list[dict], requirements: list[dict]) -> None:
    """Write program/requirement graph to Neo4j.

    TODO: Replace stub once INFRA-002 lands.
    """
    or_alt_count = sum(1 for r in requirements if r["or_predecessor_position"] is not None)
    print(
        f"[STUB] Would write {len(programs)} Program nodes, "
        f"{len(requirements)} Requirement nodes, and {or_alt_count} OR_ALTERNATIVE edges to Neo4j"
    )


def ingest_requirements() -> None:
    path = Path(__file__).resolve().parents[1] / "cu_degree_requirements.json"
    programs, requirements = parse_requirements(path)
    write_postgres(programs, requirements)
    write_neo4j(programs, requirements)
    print(
        f"Ingested {len(programs)} programs and {len(requirements)} requirements from {path.name}"
    )


if __name__ == "__main__":
    ingest_requirements()
