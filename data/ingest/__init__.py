from __future__ import annotations

__all__ = ["ingest_courses", "parse_classes"]


def __getattr__(name: str):  # noqa: N807
    if name in __all__:
        from data.ingest.ingest_courses import ingest_courses, parse_classes

        globals().update({"ingest_courses": ingest_courses, "parse_classes": parse_classes})
        return globals()[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
