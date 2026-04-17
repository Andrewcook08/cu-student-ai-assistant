"""python -m data.ingest run --mode={full,upsert,embeddings,validate}"""

from __future__ import annotations

import argparse
import sys
import uuid

from data.ingest.logger import make_logger, timed_step

FAILURE_THRESHOLD_PCT = 5


def _wipe(logger) -> None:
    """Destructive: truncate all ingest tables in postgres and delete all nodes in Neo4j."""
    from neo4j import GraphDatabase
    from shared.config import settings
    from shared.database import SessionLocal, engine
    from shared.models import Base
    from sqlalchemy import text

    from data.ingest.retry import with_retry

    log = logger

    log.info("wiping postgres tables", extra={"step": "wipe"})
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        with_retry(
            lambda: session.execute(
                text(
                    "TRUNCATE courses, sections, course_attributes, "
                    "programs, requirements RESTART IDENTITY CASCADE"
                )
            ),
            on_retry=lambda a, e: log.warning(f"pg wipe retry {a}: {e}", extra={"step": "wipe"}),
        )
        session.commit()
        log.info("postgres wiped", extra={"step": "wipe"})
    finally:
        session.close()

    log.info("wiping neo4j", extra={"step": "wipe"})
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as neo_session:
            with_retry(
                lambda: neo_session.run("MATCH (n) DETACH DELETE n").consume(),
                on_retry=lambda a, e: log.warning(
                    f"neo4j wipe retry {a}: {e}", extra={"step": "wipe"}
                ),
            )
        log.info("neo4j wiped", extra={"step": "wipe"})
    finally:
        driver.close()


def _run_upsert(logger) -> None:
    """Run all 4 ingest steps idempotently."""
    from data.ingest.build_embeddings import build_all_embeddings
    from data.ingest.ingest_courses import ingest_courses
    from data.ingest.ingest_requirements import ingest_requirements
    from data.ingest.parse_prerequisites import run as parse_prereqs
    from data.ingest.retry import with_retry

    steps = [
        ("ingest_courses", ingest_courses),
        ("parse_prerequisites", parse_prereqs),
        ("ingest_requirements", ingest_requirements),
        ("build_embeddings", lambda: build_all_embeddings(logger)),
    ]
    for name, fn in steps:
        with timed_step(logger, name):
            with_retry(
                fn,
                on_retry=lambda attempt, exc, _name=name: logger.warning(
                    f"step retry {attempt}: {exc}",
                    extra={"step": _name},
                ),
            )


def _run_embeddings_only(logger) -> None:
    from data.ingest.build_embeddings import build_all_embeddings

    with timed_step(logger, "build_embeddings"):
        build_all_embeddings(logger)


def _run_validate(logger) -> None:
    """Run all validators against current DB state, no writes."""
    import sys as _sys

    from data.ingest.run_all import validate_neo4j_extras
    from data.ingest.validate_counts import main as validate_counts_main
    from data.ingest.validate_requirements import main as validate_requirements_main

    with timed_step(logger, "validate_counts"):
        orig = _sys.argv[:]
        _sys.argv = [_sys.argv[0], "--db"]
        try:
            validate_counts_main()
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise RuntimeError("validate_counts failed") from None
        finally:
            _sys.argv = orig

    with timed_step(logger, "validate_requirements"):
        try:
            validate_requirements_main()
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise RuntimeError("validate_requirements failed") from None

    with timed_step(logger, "validate_neo4j_extras"):
        if not validate_neo4j_extras():
            raise RuntimeError("neo4j extra checks failed")


def _dry_run_counts(logger) -> None:
    """Print planned row counts without writing anything."""
    from pathlib import Path

    from data.ingest.ingest_courses import parse_classes
    from data.ingest.ingest_requirements import parse_requirements
    from data.ingest.parse_prerequisites import parse_prerequisites

    data_dir = Path(__file__).resolve().parents[1]

    courses, sections = parse_classes(data_dir / "cu_classes.json")
    programs, requirements = parse_requirements(data_dir / "cu_degree_requirements.json")
    edges = parse_prerequisites(courses)

    # Count courses needing embeddings
    try:
        from neo4j import GraphDatabase
        from shared.config import settings

        driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
        try:
            with driver.session() as session:
                missing_emb = session.run(
                    "MATCH (c:Course) WHERE c.embedding IS NULL RETURN count(c) AS n"
                ).single()["n"]
        finally:
            driver.close()
        emb_line = f"  embeddings to generate : {missing_emb} (courses missing embeddings)"
    except Exception:
        emb_line = "  embeddings to generate : (could not connect to Neo4j)"

    print("\n-- dry run: planned writes --")
    print(f"  courses                : {len(courses)}")
    print(f"  sections               : {len(sections)}")
    print(f"  programs               : {len(programs)}")
    print(f"  requirements           : {len(requirements)}")
    print(f"  prerequisite edges     : {len(edges)}")
    print(emb_line)
    print("-- no writes performed --\n")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m data.ingest")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run the ingestion pipeline")
    run_p.add_argument(
        "--mode",
        choices=["full", "upsert", "embeddings", "validate"],
        required=True,
    )
    run_p.add_argument(
        "--dry-run",
        action="store_true",
        help="show planned row counts and exit without writing",
    )
    run_p.add_argument(
        "--i-understand-this-wipes-prod",
        action="store_true",
        dest="confirmed_wipe",
        help="required with --mode=full",
    )

    args = parser.parse_args()

    run_id = str(uuid.uuid4())[:8]
    logger = make_logger(run_id)

    logger.info(f"starting ingest run_id={run_id} mode={args.mode} dry_run={args.dry_run}")

    if args.mode == "full" and not args.confirmed_wipe:
        print(
            "ERROR: --mode=full will wipe all data. "
            "Re-run with --i-understand-this-wipes-prod to confirm.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.dry_run:
        _dry_run_counts(logger)
        sys.exit(0)

    try:
        if args.mode == "full":
            with timed_step(logger, "wipe"):
                _wipe(logger)
            _run_upsert(logger)
            _run_validate(logger)

        elif args.mode == "upsert":
            _run_upsert(logger)
            _run_validate(logger)

        elif args.mode == "embeddings":
            _run_embeddings_only(logger)

        elif args.mode == "validate":
            _run_validate(logger)

    except Exception as exc:
        logger.error(f"pipeline failed: {exc}", exc_info=True)
        sys.exit(1)

    logger.info(f"pipeline completed successfully run_id={run_id}")


if __name__ == "__main__":
    main()
