from __future__ import annotations

import sys
import time


def _run_step(step: int, label: str, func: callable) -> None:
    """Run a single ingestion step with timing and error handling."""
    print(f"\nStep {step}/4: {label}")
    print("-" * 60)
    start = time.time()
    try:
        func()
    except SystemExit as exc:
        if exc.code not in (None, 0):
            elapsed = time.time() - start
            print(f"\n  FAILED after {elapsed:.1f}s")
            sys.exit(1)
    except Exception as exc:
        elapsed = time.time() - start
        print(f"\n  ERROR after {elapsed:.1f}s: {exc}")
        sys.exit(1)
    elapsed = time.time() - start
    print(f"  Completed in {elapsed:.1f}s")


def validate_neo4j_extras() -> bool:
    """Additional Neo4j checks not covered by existing validators."""
    from neo4j import GraphDatabase
    from shared.config import settings

    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )

    results: list[tuple[str, bool]] = []
    try:
        with driver.session() as session:
            prereq_edges = session.run(
                "MATCH ()-[r:HAS_PREREQUISITE]->() RETURN count(r) AS n"
            ).single()["n"]
            results.append((
                f"HAS_PREREQUISITE edges > 2000 (got {prereq_edges})",
                prereq_edges > 2000,
            ))

            program_nodes = session.run(
                "MATCH (p:Program) RETURN count(p) AS n"
            ).single()["n"]
            results.append((
                f"Program nodes == 203 (got {program_nodes})",
                program_nodes == 203,
            ))

            courses_with_emb = session.run(
                "MATCH (c:Course) WHERE c.embedding IS NOT NULL RETURN count(c) AS n"
            ).single()["n"]
            results.append((
                f"Courses with embeddings == 3410 (got {courses_with_emb})",
                courses_with_emb == 3410,
            ))

            vector_idx = session.run(
                "SHOW INDEXES YIELD name WHERE name = 'course-embeddings' RETURN count(*) AS n"
            ).single()["n"]
            results.append((
                f"Vector index 'course-embeddings' exists (got {vector_idx})",
                vector_idx == 1,
            ))
    finally:
        driver.close()

    all_passed = True
    for label, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {label}")
        if not passed:
            all_passed = False

    return all_passed


def _run_validation() -> None:
    """Run all validation checks (Step 5)."""
    from data.ingest.validate_counts import main as validate_counts_main
    from data.ingest.validate_requirements import main as validate_requirements_main

    print("\nStep 5: Validation")
    print("-" * 60)

    # 5a: validate_counts with --db flag
    print("\n--- validate_counts (with --db) ---")
    original_argv = sys.argv[:]
    sys.argv = [sys.argv[0], "--db"]
    try:
        validate_counts_main()
    except SystemExit as exc:
        if exc.code not in (None, 0):
            print("  validate_counts FAILED")
            sys.exit(1)
    finally:
        sys.argv = original_argv

    # 5a: validate_requirements
    print("\n--- validate_requirements ---")
    try:
        validate_requirements_main()
    except SystemExit as exc:
        if exc.code not in (None, 0):
            print("  validate_requirements FAILED")
            sys.exit(1)

    # 5b: additional Neo4j checks
    print("\n--- Neo4j extra checks ---")
    if not validate_neo4j_extras():
        print("  Neo4j extra checks FAILED")
        sys.exit(1)


def main() -> None:
    from data.ingest.build_embeddings import build_all_embeddings
    from data.ingest.ingest_courses import ingest_courses
    from data.ingest.ingest_requirements import ingest_requirements
    from data.ingest.parse_prerequisites import run

    print("=" * 60)
    print("CU Data Ingestion Pipeline")
    print("=" * 60)

    total_start = time.time()

    steps: list[tuple[str, callable]] = [
        ("Ingesting courses...", ingest_courses),
        ("Parsing prerequisites...", run),
        ("Ingesting degree requirements...", ingest_requirements),
        ("Building embeddings...", build_all_embeddings),
    ]

    for i, (label, func) in enumerate(steps, 1):
        _run_step(i, label, func)
        print("=" * 60)

    _run_validation()

    total_elapsed = time.time() - total_start
    print("\n" + "=" * 60)
    print(f"All steps completed successfully in {total_elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
