from fastapi import APIRouter, Depends, HTTPException, Query
from shared.models import Course, Section
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session, joinedload

from course_search_api.dependencies import get_db

router = APIRouter(prefix="/api/courses", tags=["courses"])


@router.get("")
def list_courses(
    dept: str | None = Query(None, description="Department code, e.g. CSCI"),
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
    if instruction_mode:
        query = query.filter(Course.instruction_mode == instruction_mode)
    if credits:
        query = query.filter(Course.credits == credits)
    if q:
        search = f"%{q}%"
        query = query.filter(
            Course.title.ilike(search) | Course.description.ilike(search)
        )
    if status:
        # Explicit join for filtering; use distinct to avoid row fan-out on count
        query = query.join(Course.sections).filter(Section.status == status)

    # Count distinct course IDs to avoid fan-out from joins
    total = query.with_entities(func.count(distinct(Course.id))).scalar() or 0

    # Fetch with eager loading after count
    course_ids_query = query.with_entities(Course.id).offset(offset).limit(limit)
    course_ids = [row[0] for row in course_ids_query.all()]
    courses = (
        db.query(Course)
        .options(joinedload(Course.sections))
        .filter(Course.id.in_(course_ids))
        .all()
    ) if course_ids else []

    return {
        "items": [_course_to_dict(c) for c in courses],
        "total": total,
        "offset": offset,
        "limit": limit,
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


def _course_to_dict(course: Course, *, include_attributes: bool = False) -> dict:
    result: dict = {
        "code": course.code,
        "title": course.title,
        "credits": course.credits,
        "dept": course.dept,
        "description": course.description,
        "prerequisites_raw": course.prerequisites_raw,
        "instruction_mode": course.instruction_mode,
        "topic_titles": course.topic_titles,
        "sections": [
            {
                "crn": s.crn,
                "meets": s.meets,
                "instructor": s.instructor,
                "status": s.status,
            }
            for s in (course.sections or [])
        ],
    }
    if include_attributes:
        result["attributes"] = [
            f"{a.college}: {a.category}" for a in (course.attributes or [])
        ]
    return result
