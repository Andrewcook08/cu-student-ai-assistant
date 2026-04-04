from __future__ import annotations

import sys
from pathlib import Path

from data.ingest.ingest_courses import parse_classes

EXPECTED_COURSES = 3410  # 3735 raw entries, deduplicated by course code (topics courses)
EXPECTED_SECTIONS = 9470  # deduplicated: topics courses share sections across raw entries
EXPECTED_DEPARTMENTS = 152


def validate_db(results: list[tuple[str, bool]]) -> None:
    """Validate row/node counts against live PostgreSQL and Neo4j instances."""
    # --- Lazy imports: only needed when --db is passed ---
    from neo4j import GraphDatabase  # noqa: PLC0415
    from shared.config import settings  # noqa: PLC0415
    from sqlalchemy import create_engine, text  # noqa: PLC0415

    # ── PostgreSQL ──────────────────────────────────────────────────────────
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        pg_courses = conn.execute(text("SELECT count(*) FROM courses")).scalar_one()
        pg_sections = conn.execute(text("SELECT count(*) FROM sections")).scalar_one()
        pg_attrs_with_college = conn.execute(
            text("SELECT count(*) FROM course_attributes WHERE college IS NOT NULL")
        ).scalar_one()
        pg_eng_hum = conn.execute(
            text(
                "SELECT count(*) FROM course_attributes"
                " WHERE college LIKE '%Engineering%'"
                " AND category LIKE '%Humanities%'"
            )
        ).scalar_one()

    results.append((
        f"[PG] courses == {EXPECTED_COURSES} (got {pg_courses})",
        pg_courses == EXPECTED_COURSES,
    ))
    results.append((
        f"[PG] sections == {EXPECTED_SECTIONS} (got {pg_sections})",
        pg_sections == EXPECTED_SECTIONS,
    ))
    results.append((
        f"[PG] course_attributes with college IS NOT NULL (got {pg_attrs_with_college})",
        pg_attrs_with_college > 0,
    ))
    results.append((
        f"[PG] Engineering courses with Humanities category (got {pg_eng_hum})",
        pg_eng_hum > 0,
    ))

    # ── Neo4j ───────────────────────────────────────────────────────────────
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as neo_session:
            n4j_courses = neo_session.run(
                "MATCH (c:Course) RETURN count(c) AS n"
            ).single()["n"]
            n4j_depts = neo_session.run(
                "MATCH (d:Department) RETURN count(d) AS n"
            ).single()["n"]
            n4j_attrs = neo_session.run(
                "MATCH ()-[r:HAS_ATTRIBUTE]->() RETURN count(r) AS n"
            ).single()["n"]
    finally:
        driver.close()

    results.append((
        f"[N4J] Course nodes == {EXPECTED_COURSES} (got {n4j_courses})",
        n4j_courses == EXPECTED_COURSES,
    ))
    results.append((
        f"[N4J] Department nodes == {EXPECTED_DEPARTMENTS} (got {n4j_depts})",
        n4j_depts == EXPECTED_DEPARTMENTS,
    ))
    results.append((
        f"[N4J] HAS_ATTRIBUTE relationships > 0 (got {n4j_attrs})",
        n4j_attrs > 0,
    ))


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "cu_classes.json"
    courses, sections = parse_classes(path)

    results: list[tuple[str, bool]] = []

    # --- Count checks ---
    actual_courses = len(courses)
    actual_sections = len(sections)
    actual_depts = len({c["dept"] for c in courses})

    results.append((
        f"Course count == {EXPECTED_COURSES} (got {actual_courses})",
        actual_courses == EXPECTED_COURSES,
    ))
    results.append((
        f"Section count == {EXPECTED_SECTIONS} (got {actual_sections})",
        actual_sections == EXPECTED_SECTIONS,
    ))
    results.append((
        f"Department count == {EXPECTED_DEPARTMENTS} (got {actual_depts})",
        actual_depts == EXPECTED_DEPARTMENTS,
    ))

    # --- All CRNs are numeric strings ---
    non_numeric_crns = [s["crn"] for s in sections if not s["crn"].isdigit()]
    results.append(
        (
            f"All CRNs are numeric strings ({len(non_numeric_crns)} non-numeric found)",
            len(non_numeric_crns) == 0,
        )
    )

    # --- All course codes are unique ---
    codes = [c["code"] for c in courses]
    duplicate_codes = [code for code in set(codes) if codes.count(code) > 1]
    results.append(
        (
            f"All course codes are unique ({len(duplicate_codes)} duplicates found)",
            len(duplicate_codes) == 0,
        )
    )

    # --- DB validation (opt-in via --db flag) ---
    if "--db" in sys.argv:
        validate_db(results)

    # --- Anomaly flags (informational, not PASS/FAIL) ---
    empty_titles = [c["code"] for c in courses if not c["title"].strip()]
    empty_descriptions = [c["code"] for c in courses if not c["description"].strip()]
    empty_codes = [c["code"] for c in courses if not c["code"].strip()]

    topics_courses = [c for c in courses if c["topic_titles"]]
    total_topic_titles = sum(len(c["topic_titles"].split("|")) for c in topics_courses)

    print("=" * 60)
    print("CUAI-20 Acceptance Criteria Validation")
    print("=" * 60)

    all_passed = True
    for label, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {label}")
        if not passed:
            all_passed = False

    print()
    print("Anomaly Report (informational):")
    print(f"  Courses with empty titles:       {len(empty_titles)}")
    print(f"  Courses with empty descriptions: {len(empty_descriptions)}")
    print(f"  Courses with empty codes:        {len(empty_codes)}")
    print(
        f"  [INFO] Courses with topic variants: {len(topics_courses)}"
        f" (total topic titles: {total_topic_titles})"
    )

    print()
    print("=" * 60)
    if all_passed:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
