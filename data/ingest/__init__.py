from __future__ import annotations

__all__ = ["ingest_courses", "ingest_requirements", "parse_classes", "parse_requirements"]


def __getattr__(name: str):  # noqa: N807
    if name in ("ingest_courses", "parse_classes"):
        from data.ingest.ingest_courses import ingest_courses, parse_classes

        globals().update({"ingest_courses": ingest_courses, "parse_classes": parse_classes})
        return globals()[name]
    if name in ("ingest_requirements", "parse_requirements"):
        from data.ingest.ingest_requirements import ingest_requirements, parse_requirements

        globals().update(
            {"ingest_requirements": ingest_requirements, "parse_requirements": parse_requirements}
        )
        return globals()[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
