from fastapi import APIRouter, HTTPException, Request

from course_search_api.limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request) -> dict:
    """Placeholder — full implementation in AUTH-002.

    Rate limit (5/minute per IP) is enforced here so login brute-force is
    mitigated as soon as this stub is in place, before the real handler lands.
    """
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/register")
@limiter.limit("3/hour")
async def register(request: Request) -> dict:
    """Placeholder — full implementation in AUTH-001.

    Rate limit (3/hour per IP) is enforced here so register spam is
    mitigated before the real handler lands.
    """
    raise HTTPException(status_code=501, detail="Not implemented")
