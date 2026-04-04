from __future__ import annotations

import json
from pathlib import Path


def parse_classes(path: Path) -> tuple[list[dict], list[dict]]:
    """Parse cu_classes.json into flat course and section lists.

    Courses with the same code (topics courses like WRTG 3020, CSCI 7000) are
    deduplicated: the first occurrence's metadata is kept and all sections are
    merged under that single course record.  All unique titles seen for a given
    code are joined into ``topic_titles`` as a pipe-delimited string (empty string
    for non-topics courses).
    """
    data: dict[str, list[dict]] = json.loads(path.read_text())

    course_map: dict[str, dict] = {}
    # tracks all titles seen per code in insertion order (via dict keys)
    title_map: dict[str, dict[str, None]] = {}
    section_map: dict[tuple[str, str], dict] = {}  # (course_code, crn) -> section

    for _dept_key, course_list in data.items():
        for course in course_list:
            code = course["code"]

            if code not in course_map:
                course_map[code] = {
                    "code": code,
                    "dept": code.split()[0],
                    "title": course["title"],
                    "credits": course["credits"],
                    "description": course["description"],
                    "prerequisites_raw": course["prerequisites"],
                    "attributes": course["attributes"],
                    "instruction_mode": course["instruction_mode"],
                    "campus": course["campus"],
                    "grading_mode": course["grading_mode"],
                    "session": course["session"],
                    "dates": course["dates"],
                }
                title_map[code] = {course["title"]: None}
            else:
                title_map[code][course["title"]] = None

            for section in course["sections"]:
                raw_crn: str = section["crn"]
                crn = raw_crn.removeprefix("This section is closed ").strip()
                key = (code, crn)
                if key not in section_map:
                    section_map[key] = {
                        "course_code": code,
                        "crn": crn,
                        "section_number": section["section_number"],
                        "type": section["type"],
                        "meets": section["meets"],
                        "instructor": section["instructor"],
                        "status": section["status"],
                        "campus": section["campus"],
                        "dates": section["dates"],
                    }

    # Attach topic_titles: pipe-delimited string for topics courses, empty string otherwise
    for code, course in course_map.items():
        titles = list(title_map[code].keys())
        course["topic_titles"] = "|".join(titles) if len(titles) > 1 else ""

    return list(course_map.values()), list(section_map.values())


def parse_attributes(raw: str) -> list[tuple[str, str]]:
    """Parse a raw attributes string into (college, category) tuples.

    Each non-empty line is expected to contain ``": "`` as a delimiter between
    the college name and the attribute category.  Lines without the delimiter
    are silently skipped.  Empty input returns an empty list.
    """
    result: list[tuple[str, str]] = []
    for line in raw.split("\n"):
        if not line:
            continue
        if ": " in line:
            college, category = line.split(": ", maxsplit=1)
            result.append((college.strip(), category.strip()))
    return result


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


def write_postgres(courses: list[dict], sections: list[dict]) -> None:
    """Write courses, sections, and course_attributes to PostgreSQL via upserts."""
    from shared.database import SessionLocal, engine
    from shared.models import Base, Course, CourseAttribute, Section
    from sqlalchemy import select

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        # 1. Upsert courses
        if courses:
            course_rows = [
                {
                    "code": c["code"],
                    "dept": c["dept"],
                    "title": c["title"],
                    "credits": c["credits"],
                    "description": c["description"],
                    "prerequisites_raw": c["prerequisites_raw"],
                    "topic_titles": c["topic_titles"],
                    "instruction_mode": c["instruction_mode"],
                    "campus": c["campus"],
                    "grading_mode": c["grading_mode"],
                    "session": c["session"],
                    "dates": c["dates"],
                }
                for c in courses
            ]
            _pg_upsert_batched(
                session, Course, course_rows,
                index_elements=["code"],
                update_cols=[
                    "dept", "title", "credits", "description",
                    "prerequisites_raw", "topic_titles", "instruction_mode",
                    "campus", "grading_mode", "session", "dates",
                ],
            )
            session.flush()

        # 2. Build {code: id} lookup
        rows = session.execute(select(Course.code, Course.id)).all()
        code_to_id = {code: id_ for code, id_ in rows}

        # 3. Upsert sections
        if sections:
            section_rows = [
                {
                    "course_id": code_to_id[s["course_code"]],
                    "crn": s["crn"],
                    "section_number": s["section_number"],
                    "type": s["type"],
                    "meets": s["meets"],
                    "instructor": s["instructor"],
                    "status": s["status"],
                    "campus": s["campus"],
                    "dates": s["dates"],
                }
                for s in sections
            ]
            _pg_upsert_batched(
                session, Section, section_rows,
                index_elements=["course_id", "crn"],
                update_cols=[
                    "section_number", "type", "meets", "instructor",
                    "status", "campus", "dates",
                ],
            )

        # 4. Upsert course_attributes
        attr_rows = []
        for c in courses:
            for college, category in parse_attributes(c.get("attributes", "")):
                attr_rows.append({
                    "course_code": c["code"],
                    "college": college,
                    "category": category,
                })
        if attr_rows:
            _pg_upsert_batched(
                session, CourseAttribute, attr_rows,
                index_elements=["course_code", "college", "category"],
                update_cols=["college", "category"],
            )

        session.commit()
        print(
            f"  PostgreSQL: {len(courses)} courses, "
            f"{len(sections)} sections, {len(attr_rows)} attributes"
        )
    finally:
        session.close()


def _neo4j_batch(tx, query: str, items: list[dict], batch_size: int = 500) -> None:
    """Execute a Cypher query in batches via UNWIND."""
    for i in range(0, len(items), batch_size):
        tx.run(query, rows=items[i : i + batch_size])


def write_neo4j(courses: list[dict], sections: list[dict]) -> None:
    """Write course graph to Neo4j (Department, Course, Section, Attribute nodes)."""
    from neo4j import GraphDatabase
    from shared.config import settings

    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            # 1. Departments
            depts = [{"code": d} for d in sorted({c["dept"] for c in courses})]
            session.execute_write(
                _neo4j_batch,
                "UNWIND $rows AS d MERGE (:Department {code: d.code})",
                depts,
            )

            # 2. Courses + IN_DEPARTMENT
            course_rows = [
                {
                    "code": c["code"],
                    "dept": c["dept"],
                    "title": c["title"],
                    "credits": c["credits"],
                    "description": c["description"],
                    "instruction_mode": c["instruction_mode"],
                    "campus": c["campus"],
                    "topic_titles": c["topic_titles"],
                }
                for c in courses
            ]
            session.execute_write(
                _neo4j_batch,
                """
                UNWIND $rows AS c
                MERGE (course:Course {code: c.code})
                SET course.title = c.title, course.credits = c.credits,
                    course.description = c.description,
                    course.instruction_mode = c.instruction_mode,
                    course.campus = c.campus, course.topic_titles = c.topic_titles
                WITH course, c
                MATCH (dept:Department {code: c.dept})
                MERGE (course)-[:IN_DEPARTMENT]->(dept)
                """,
                course_rows,
            )

            # 3. Sections + HAS_SECTION
            section_rows = [
                {
                    "course_code": s["course_code"],
                    "crn": s["crn"],
                    "section_number": s["section_number"],
                    "type": s["type"],
                    "meets": s["meets"],
                    "instructor": s["instructor"],
                    "status": s["status"],
                    "campus": s["campus"],
                    "dates": s["dates"],
                }
                for s in sections
            ]
            session.execute_write(
                _neo4j_batch,
                """
                UNWIND $rows AS s
                MATCH (course:Course {code: s.course_code})
                MERGE (sec:Section {crn: s.crn})
                SET sec.section_number = s.section_number, sec.type = s.type,
                    sec.meets = s.meets, sec.instructor = s.instructor,
                    sec.status = s.status, sec.campus = s.campus, sec.dates = s.dates
                MERGE (course)-[:HAS_SECTION]->(sec)
                """,
                section_rows,
            )

            # 4. Attributes + HAS_ATTRIBUTE
            attr_rows = []
            for c in courses:
                for college, category in parse_attributes(c.get("attributes", "")):
                    attr_rows.append({
                        "course_code": c["code"],
                        "college": college,
                        "category": category,
                    })
            if attr_rows:
                session.execute_write(
                    _neo4j_batch,
                    """
                    UNWIND $rows AS a
                    MATCH (course:Course {code: a.course_code})
                    MERGE (attr:Attribute {college: a.college, category: a.category})
                    MERGE (course)-[:HAS_ATTRIBUTE]->(attr)
                    """,
                    attr_rows,
                )

        print(
            f"  Neo4j: {len(courses)} Course nodes, {len(depts)} Department nodes, "
            f"{len(sections)} Section nodes, {len(attr_rows)} Attribute edges"
        )
    finally:
        driver.close()


def ingest_courses() -> None:
    path = Path(__file__).resolve().parents[1] / "cu_classes.json"
    courses, sections = parse_classes(path)
    write_postgres(courses, sections)
    write_neo4j(courses, sections)
    print(f"Ingested {len(courses)} courses and {len(sections)} sections from {path.name}")


if __name__ == "__main__":
    ingest_courses()
