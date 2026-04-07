from typing import Any

from fastapi import APIRouter, Depends
from shared.models import User

from course_search_api.dependencies import get_current_user

router = APIRouter(prefix="/api/students", tags=["students"])


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
