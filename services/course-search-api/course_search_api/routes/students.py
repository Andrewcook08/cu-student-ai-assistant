from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from shared.models import CompletedCourse, Course, User
from sqlalchemy.orm import Session

from course_search_api.dependencies import get_current_user, get_db
from course_search_api.limiter import limiter, user_key_func

router = APIRouter(prefix="/api/students", tags=["students"])

# Hard cap on the number of completed-course entries accepted in one PUT.
_MAX_COMPLETED_COURSES = 200


class CompletedCourseItem(BaseModel):
    course_code: str
    grade: str | None = None


@router.get("/me")
def get_current_student(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return the authenticated user's profile.

    `get_current_user` (see dependencies.py) enforces:
    - valid JWT → 401 if missing/invalid
    - user exists in DB → 401 if not found
    - user.is_active is True → 401 if deactivated (PR #51 fix)
    """
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "program_id": user.program_id,
        "is_active": user.is_active,
    }


@router.put("/me/completed-courses")
@limiter.limit("10/minute", key_func=user_key_func)
def update_completed_courses(
    request: Request,
    courses: Annotated[list[CompletedCourseItem], Field(max_length=_MAX_COMPLETED_COURSES)],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Batch-replace the authenticated user's completed courses.

    Replaces the entire list atomically — existing rows are deleted and the
    supplied list is inserted.  Duplicate course_codes within the payload are
    rejected with 400.  Unknown course_codes are rejected with 422 so that
    callers get a clear error rather than a silent integrity violation.
    """
    # Reject duplicate course_codes within the payload
    codes = [item.course_code for item in courses]
    if len(codes) != len(set(codes)):
        raise HTTPException(
            status_code=400,
            detail="Duplicate course_code values in request",
        )

    # Validate all course_codes exist in the courses table
    if codes:
        existing_codes = {
            row[0] for row in db.query(Course.code).filter(Course.code.in_(codes)).all()
        }
        unknown = set(codes) - existing_codes
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown course codes: {sorted(unknown)}",
            )

    # Atomically replace the user's completed courses
    db.query(CompletedCourse).filter(CompletedCourse.user_id == user.id).delete()
    for item in courses:
        db.add(CompletedCourse(user_id=user.id, course_code=item.course_code, grade=item.grade))
    db.commit()

    rows = db.query(CompletedCourse).filter(CompletedCourse.user_id == user.id).all()
    return {"completed_courses": [{"course_code": r.course_code, "grade": r.grade} for r in rows]}
