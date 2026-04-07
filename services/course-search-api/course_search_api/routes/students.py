from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from shared.models import CompletedCourse, User
from sqlalchemy.orm import Session

from course_search_api.dependencies import get_current_user, get_db

router = APIRouter(prefix="/api/students", tags=["students"])


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
def update_completed_courses(
    courses: list[CompletedCourseItem],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Replace the authenticated user's completed course list.

    Accepts a full replacement list of {course_code, grade} pairs.
    All existing completed courses for the user are deleted and replaced.
    """
    db.query(CompletedCourse).filter(CompletedCourse.user_id == user.id).delete()
    for item in courses:
        db.add(
            CompletedCourse(
                user_id=user.id,
                course_code=item.course_code,
                grade=item.grade,
            )
        )
    db.commit()
    rows = db.query(CompletedCourse).filter(CompletedCourse.user_id == user.id).all()
    return {"completed_courses": [{"course_code": r.course_code, "grade": r.grade} for r in rows]}
