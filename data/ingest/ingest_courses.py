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
    sections: list[dict] = []

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
                sections.append(
                    {
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
                )

    # Attach topic_titles: pipe-delimited string for topics courses, empty string otherwise
    for code, course in course_map.items():
        titles = list(title_map[code].keys())
        course["topic_titles"] = "|".join(titles) if len(titles) > 1 else ""

    return list(course_map.values()), sections


def write_postgres(courses: list[dict], sections: list[dict]) -> None:
    """Write courses and sections to PostgreSQL.

    TODO: Replace stub with SQLAlchemy upserts via shared.database once INFRA-002 lands.
    """
    print(f"[STUB] Would write {len(courses)} courses and {len(sections)} sections to PostgreSQL")


def write_neo4j(courses: list[dict], sections: list[dict]) -> None:
    """Write course graph to Neo4j.

    TODO: Replace stub with neo4j driver MERGE queries (Course, Department, Section nodes)
    once INFRA-002 lands.
    """
    dept_count = len({c["dept"] for c in courses})
    print(
        f"[STUB] Would write {len(courses)} Course nodes, "
        f"{dept_count} Department nodes, and {len(sections)} Section nodes to Neo4j"
    )


def ingest_courses() -> None:
    path = Path(__file__).resolve().parents[1] / "cu_classes.json"
    courses, sections = parse_classes(path)
    write_postgres(courses, sections)
    write_neo4j(courses, sections)
    print(f"Ingested {len(courses)} courses and {len(sections)} sections from {path.name}")


if __name__ == "__main__":
    ingest_courses()
