import logging

import httpx
import neo4j.exceptions
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from neo4j import AsyncDriver
from shared.models import Course, Section
from sqlalchemy import Integer, cast, distinct, func
from sqlalchemy.orm import Session, joinedload

from course_search_api.dependencies import get_db, get_http_client, get_neo4j_driver
from course_search_api.limiter import limiter
from course_search_api.services.neo4j_service import vector_search
from course_search_api.services.ollama_service import get_embedding

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/courses", tags=["courses"])

# Level → course-number range. Numeric portion extracted from Course.code
# (format "CSCI 1300") via substring regex in SQL.
_LEVEL_RANGES: dict[str, tuple[int, int]] = {
    "undergrad-lower": (1000, 2999),
    "undergrad-upper": (3000, 4999),
    "graduate": (5000, 9999),
}


@router.get("")
def list_courses(
    dept: str | None = Query(None, description="Department code, e.g. CSCI"),
    level: str | None = Query(
        None,
        description="Course level: undergrad-lower, undergrad-upper, or graduate",
    ),
    instruction_mode: str | None = Query(None),
    status: str | None = Query(None, description="Filter by section status"),
    credits: str | None = Query(None),
    q: str | None = Query(None, description="Text search on title/description"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    # Base query — no eager loading yet (applied after count)
    query = db.query(Course)

    if dept:
        query = query.filter(Course.dept == dept.upper())
    if level:
        if level not in _LEVEL_RANGES:
            raise HTTPException(
                status_code=400,
                detail=(f"Invalid level '{level}'. Must be one of: {', '.join(_LEVEL_RANGES)}"),
            )
        low, high = _LEVEL_RANGES[level]
        course_number = cast(func.substring(Course.code, r"[0-9]+"), Integer)
        query = query.filter(course_number.between(low, high))
    if instruction_mode:
        query = query.filter(Course.instruction_mode == instruction_mode)
    if credits:
        query = query.filter(Course.credits == credits)
    if q:
        search = f"%{q}%"
        query = query.filter(Course.title.ilike(search) | Course.description.ilike(search))
    if status:
        # Explicit join for filtering; use distinct to avoid row fan-out on count
        query = query.join(Course.sections).filter(Section.status == status)

    # Count distinct course IDs to avoid fan-out from joins
    total = query.with_entities(func.count(distinct(Course.id))).scalar() or 0

    # Fetch with eager loading after count
    course_ids_query = query.with_entities(Course.id).offset(offset).limit(limit)
    course_ids = [row[0] for row in course_ids_query.all()]
    courses = (
        (
            db.query(Course)
            .options(joinedload(Course.sections))
            .filter(Course.id.in_(course_ids))
            .all()
        )
        if course_ids
        else []
    )

    return {
        "items": [_course_to_dict(c) for c in courses],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/search")
@limiter.limit("30/minute")  # TODO SEC-005: switch key_func to user_key_func once auth is added
async def search_courses(
    request: Request,
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(10, ge=1, le=50),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    driver: AsyncDriver = Depends(get_neo4j_driver),
) -> dict:
    """Semantic course search via Ollama embeddings + Neo4j vector index.

    Generates a 768-dim embedding for *q*, queries the 'course-embeddings'
    vector index, and returns results ranked by cosine similarity.

    Returns 503 if Ollama or Neo4j is temporarily unavailable.
    """
    try:
        embedding = await get_embedding(http_client, q)
        results = await vector_search(driver, embedding, limit=limit)
    except (httpx.HTTPError, neo4j.exceptions.Neo4jError, OSError) as exc:
        logger.exception("Search service error for query %r: %s", q, exc)
        raise HTTPException(
            status_code=503,
            detail="Search service temporarily unavailable",
        ) from exc

    return {
        "query": q,
        "items": [{"code": r["code"], "title": r["title"], "score": r["score"]} for r in results],
    }


@router.get("/{code:path}")
def get_course(code: str, db: Session = Depends(get_db)) -> dict:
    course = (
        db.query(Course)
        .options(joinedload(Course.sections), joinedload(Course.attributes))
        .filter(Course.code == code)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail=f"Course '{code}' not found")
    return _course_to_dict(course, include_attributes=True)


def _aggregate_status(sections: list[Section] | None) -> str | None:
    """Derive a course-level status from its sections.

    Returns "Open" if any section is open, else "Waitlist" if any is waitlisted,
    else "Closed" if sections exist, else None. A course with no sections has
    no meaningful status.
    """
    if not sections:
        return None
    statuses = {s.status for s in sections}
    if "Open" in statuses:
        return "Open"
    if "Waitlist" in statuses:
        return "Waitlist"
    return "Closed"


def _course_to_dict(course: Course, *, include_attributes: bool = False) -> dict:
    result: dict = {
        "code": course.code,
        "title": course.title,
        "credits": course.credits,
        "dept": course.dept,
        "description": course.description,
        "prerequisites_raw": course.prerequisites_raw,
        "instruction_mode": course.instruction_mode,
        "status": _aggregate_status(course.sections),
        "topic_titles": course.topic_titles,
        "sections": [
            {
                "crn": s.crn,
                "type": s.type,
                "section_number": s.section_number,
                "meets": s.meets,
                "instructor": s.instructor,
                "status": s.status,
            }
            for s in (course.sections or [])
        ],
    }
    if include_attributes:
        result["attributes"] = [f"{a.college}: {a.category}" for a in (course.attributes or [])]
    return result
