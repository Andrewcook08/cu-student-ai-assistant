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


def _pg_upsert_batched(session, model, rows, index_elements, update_cols, batch_size=1000):
    """Execute batched INSERT ... ON CONFLICT DO UPDATE to stay under the 65535 param limit."""
    from sqlalchemy.dialects.postgresql import insert

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        stmt = insert(model).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_={col: getattr(stmt.excluded, col) for col in update_cols},
        )
        session.execute(stmt)


def _pg_insert_batched(session, model, rows, batch_size=1000):
    """Execute batched plain INSERT (no upsert) for models without a unique constraint."""
    from sqlalchemy.dialects.postgresql import insert

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        session.execute(insert(model).values(batch))


def write_postgres(programs: list[dict], requirements: list[dict]) -> None:
    """Write programs and requirements to PostgreSQL.

    Programs are upserted (keyed on name). Requirements are delete-then-inserted
    per program for idempotency (no unique constraint on the requirements table).
    """
    from shared.database import SessionLocal, engine
    from shared.models import Base, Program, Requirement
    from sqlalchemy import delete, select

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        # 1. Upsert programs
        if programs:
            program_rows = [
                {
                    "name": p["program_name"],
                    "type": p["degree_type"],
                    "total_credits": p["total_credits"],
                }
                for p in programs
            ]
            _pg_upsert_batched(
                session, Program, program_rows,
                index_elements=["name"],
                update_cols=["type", "total_credits"],
            )
            session.flush()

        # 2. Build {name: id} lookup
        rows = session.execute(select(Program.name, Program.id)).all()
        name_to_id = {name: id_ for name, id_ in rows}

        # 3. Delete existing requirements for idempotency
        if programs:
            program_ids = [
                name_to_id[p["program_name"]]
                for p in programs
                if p["program_name"] in name_to_id
            ]
            if program_ids:
                session.execute(
                    delete(Requirement).where(Requirement.program_id.in_(program_ids))
                )

        # 4. Insert requirements
        if requirements:
            req_rows = [
                {
                    "program_id": name_to_id[r["program_name"]],
                    "sort_order": r["position"],
                    "requirement_type": r["requirement_type"],
                    "course_code": ",".join(r["course_codes"]) if r["course_codes"] else None,
                    "name": r["name"],
                    "credits": r["credits_text"] or None,
                    "raw_id": r["raw_id"],
                }
                for r in requirements
            ]
            _pg_insert_batched(session, Requirement, req_rows)

        session.commit()
        print(
            f"  PostgreSQL: {len(programs)} programs, "
            f"{len(requirements)} requirements"
        )
    finally:
        session.close()


def _neo4j_batch(tx, query: str, items: list[dict], batch_size: int = 500) -> None:
    """Execute a Cypher query in batches via UNWIND."""
    for i in range(0, len(items), batch_size):
        tx.run(query, rows=items[i : i + batch_size])


def write_neo4j(programs: list[dict], requirements: list[dict]) -> None:
    """Write program/requirement graph to Neo4j.

    Creates Program nodes, Requirement nodes with HAS_REQUIREMENT edges,
    SATISFIED_BY edges to existing Course nodes, and OR_ALTERNATIVE edges
    between or-alternative requirements and their predecessors.
    """
    from neo4j import GraphDatabase
    from shared.config import settings

    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            # 1. Program nodes
            if programs:
                program_rows = [
                    {
                        "name": p["program_name"],
                        "type": p["degree_type"],
                        "total_credits": p["total_credits"],
                    }
                    for p in programs
                ]
                session.execute_write(
                    _neo4j_batch,
                    """
                    UNWIND $rows AS p
                    MERGE (prog:Program {name: p.name})
                    SET prog.type = p.type, prog.total_credits = p.total_credits
                    """,
                    program_rows,
                )

            # 2. Requirement nodes + HAS_REQUIREMENT edges
            if requirements:
                req_rows = [
                    {
                        "program_name": r["program_name"],
                        "sort_order": r["position"],
                        "name": r["name"],
                        "requirement_type": r["requirement_type"],
                        "course_code": ",".join(r["course_codes"]) if r["course_codes"] else None,
                        "raw_text": r["raw_id"],
                        "credits": r["credits_text"] or None,
                    }
                    for r in requirements
                ]
                session.execute_write(
                    _neo4j_batch,
                    """
                    UNWIND $rows AS r
                    MATCH (p:Program {name: r.program_name})
                    MERGE (req:Requirement {program_name: r.program_name, sort_order: r.sort_order})
                    SET req.name = r.name, req.requirement_type = r.requirement_type,
                        req.course_code = r.course_code, req.raw_text = r.raw_text,
                        req.credits = r.credits
                    MERGE (p)-[:HAS_REQUIREMENT]->(req)
                    """,
                    req_rows,
                )

            # 3. SATISFIED_BY edges (requirement → Course)
            satisfied_rows = [
                {
                    "program_name": r["program_name"],
                    "sort_order": r["position"],
                    "course_codes": r["course_codes"],
                }
                for r in requirements
                if r["course_codes"]
            ]
            if satisfied_rows:
                session.execute_write(
                    _neo4j_batch,
                    """
                    UNWIND $rows AS r
                    MATCH (req:Requirement {program_name: r.program_name, sort_order: r.sort_order})
                    UNWIND r.course_codes AS code
                    MATCH (c:Course {code: code})
                    MERGE (req)-[:SATISFIED_BY]->(c)
                    """,
                    satisfied_rows,
                )

            # 4. OR_ALTERNATIVE edges
            or_alt_rows = [
                {
                    "program_name": r["program_name"],
                    "sort_order": r["position"],
                    "pred_sort_order": r["or_predecessor_position"],
                }
                for r in requirements
                if r["or_predecessor_position"] is not None
            ]
            if or_alt_rows:
                session.execute_write(
                    _neo4j_batch,
                    """
                    UNWIND $rows AS r
                    MATCH (req:Requirement {program_name: r.program_name, sort_order: r.sort_order})
                    MATCH (pred:Requirement {
                        program_name: r.program_name,
                        sort_order: r.pred_sort_order})
                    MERGE (req)-[:OR_ALTERNATIVE]->(pred)
                    """,
                    or_alt_rows,
                )

        or_alt_count = len(or_alt_rows) if or_alt_rows else 0
        satisfied_count = len(satisfied_rows) if satisfied_rows else 0
        print(
            f"  Neo4j: {len(programs)} Program nodes, "
            f"{len(requirements)} Requirement nodes, "
            f"{satisfied_count} SATISFIED_BY edges, "
            f"{or_alt_count} OR_ALTERNATIVE edges"
        )
    finally:
        driver.close()


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
