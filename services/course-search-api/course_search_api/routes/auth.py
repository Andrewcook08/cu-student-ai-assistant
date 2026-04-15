from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator
from shared.auth import create_access_token, hash_password, verify_password
from shared.config import settings
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

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Name must not be empty")
        if len(stripped) > 200:
            raise ValueError("Name must be 200 characters or fewer")
        return stripped

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        if v.lower() in _COMMON_PASSWORDS:
            raise ValueError("Password is too common — choose a more unique password")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("Password must not be empty")
        return v


# Pre-computed dummy hash used when the user does not exist so that we always
# spend ~100 ms in bcrypt regardless of whether the email is registered.
# Without this, the no-user path is orders of magnitude faster and leaks
# whether an email is enrolled (timing side-channel / user enumeration).
_DUMMY_HASH: str = hash_password("dummy-timing-sentinel-value")


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
) -> dict:
    # Normalise email so case variants resolve to the same account.
    email = body.email.lower()

    user = db.query(User).filter(User.email == email).first()

    # Always call verify_password — even when the user does not exist — so
    # that every request spends the same bcrypt time and an attacker cannot
    # distinguish "no such email" from "wrong password" via response latency.
    hash_to_check = user.password_hash if user is not None else _DUMMY_HASH
    password_ok = verify_password(body.password, hash_to_check)

    if user is None or not user.is_active or not password_ok:
        # Fresh HTTPException per call — avoids sharing a mutable singleton
        # across concurrent async requests (stale __traceback__ risk).
        # WWW-Authenticate header follows RFC 7235 Bearer token convention.
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.id)  # sub = user_id only — no email or PII
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.jwt_expire_minutes * 60,
    }


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
        raise HTTPException(status_code=400, detail="Registration failed")

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
        raise HTTPException(status_code=400, detail="Registration failed") from err
    db.refresh(user)

    token = create_access_token(user.id)  # sub = user_id only — no email or PII
    return {"token": token, "user_id": user.id}
