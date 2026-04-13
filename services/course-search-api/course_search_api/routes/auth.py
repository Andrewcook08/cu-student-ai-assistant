from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator
from shared.auth import create_access_token, hash_password
from shared.database import get_db
from shared.models import Program, User
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from course_search_api.limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Top-100 common passwords (12+ chars — shorter ones are blocked by the length
# check first, but are included here for completeness).
_COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "password123456",
        "password12345",
        "password1234567",
        "123456789012",
        "1234567890123",
        "12345678901234",
        "qwerty123456",
        "qwerty1234567",
        "qwertyuiop123",
        "qwerty12345678",
        "abc1234567890",
        "abc123456789",
        "iloveyou12345",
        "iloveyou123456",
        "monkey1234567",
        "dragon1234567",
        "dragon12345678",
        "master12345678",
        "master123456789",
        "sunshine123456",
        "sunshine1234567",
        "princess123456",
        "princess1234567",
        "football123456",
        "football1234567",
        "welcome123456",
        "welcome1234567",
        "michael123456",
        "michael1234567",
        "shadow1234567",
        "shadow12345678",
        "superman123456",
        "batman1234567",
        "letmein123456",
        "passw0rd123456",
        "p@ssword123456",
        "admin123456789",
        "admin1234567890",
        "user1234567890",
        "test1234567890",
        "hello1234567890",
        "111111111111",
        "000000000000",
        "123123123123",
        "aaaaaaaaaaaa",
        "zxcvbnm12345",
        "asdfghjkl123",
        "qazwsxedc1234",
        "trustno11234",
        "superman1234",
    }
)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    program_id: int | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        if v.lower() in _COMMON_PASSWORDS:
            raise ValueError("Password is too common — choose a more unique password")
        return v


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
async def register(
    request: Request,
    body: RegisterRequest,
    db: Session = Depends(get_db),
) -> dict:
    # Normalize email to lowercase so case variants can't bypass uniqueness check.
    email = body.email.lower()

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if body.program_id is not None:
        found = db.query(Program).filter(Program.id == body.program_id).first()
        if found is None:
            raise HTTPException(status_code=422, detail="Unknown program_id")

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        name=body.name,
        program_id=body.program_id,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered") from err
    db.refresh(user)

    token = create_access_token(user.id, user.email)
    return {"token": token, "user_id": user.id}
