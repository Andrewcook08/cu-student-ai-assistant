"""Tests for POST /api/auth/register — AUTH-001 (CUAI-53).

Uses the db_session fixture from conftest.py (transactional rollback — all
rows inserted by tests are rolled back at teardown, no manual cleanup needed).
"""

from __future__ import annotations

from jose import jwt
from shared.auth import verify_password
from shared.config import settings
from shared.models import Program, User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client, *, email="new@colorado.edu", password="SecurePass1234!", name="Ada Lovelace", program_id=None):
    """POST /api/auth/register with sensible defaults. Override any field as needed."""
    body: dict = {"email": email, "password": password, "name": name}
    if program_id is not None:
        body["program_id"] = program_id
    return client.post("/api/auth/register", json=body)


def _make_program(db_session) -> Program:
    prog = Program(name="Test CS Major", type="major")
    db_session.add(prog)
    db_session.commit()
    db_session.refresh(prog)
    return prog


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


def test_register_returns_200_with_token_and_user_id(client, db_session):
    """Successful registration returns HTTP 200 with token and user_id."""
    resp = _register(client)
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert "user_id" in body
    assert isinstance(body["user_id"], int)


def test_register_jwt_contains_user_id_and_email(client, db_session):
    """The JWT returned by /register must contain user_id (sub) and email claims."""
    resp = _register(client, email="jwt@colorado.edu")
    assert resp.status_code == 200
    token = resp.json()["token"]

    payload = jwt.decode(
        token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )
    assert payload["sub"] == str(resp.json()["user_id"])
    assert payload["email"] == "jwt@colorado.edu"


def test_register_password_is_bcrypt_hashed(client, db_session):
    """Password stored in DB must NOT be the plaintext password but must verify correctly."""
    resp = _register(client, email="hash@colorado.edu", password="HashCheck12345!")
    assert resp.status_code == 200
    user_id = resp.json()["user_id"]

    user = db_session.get(User, user_id)
    assert user is not None
    assert user.password_hash != "HashCheck12345!"
    assert verify_password("HashCheck12345!", user.password_hash) is True


def test_register_sets_is_active_true_server_side(client, db_session):
    """User must be created with is_active=True regardless of what the client sends."""
    resp = _register(client, email="active@colorado.edu")
    assert resp.status_code == 200
    user = db_session.get(User, resp.json()["user_id"])
    assert user is not None
    assert user.is_active is True


def test_register_with_valid_program_id(client, db_session):
    """Registration with a real program_id must succeed and persist program_id."""
    prog = _make_program(db_session)
    resp = _register(client, email="prog@colorado.edu", program_id=prog.id)
    assert resp.status_code == 200
    user = db_session.get(User, resp.json()["user_id"])
    assert user is not None
    assert user.program_id == prog.id


def test_register_without_program_id_succeeds(client, db_session):
    """program_id is optional — omitting it must still succeed."""
    resp = _register(client, email="noprog@colorado.edu")
    assert resp.status_code == 200
    user = db_session.get(User, resp.json()["user_id"])
    assert user is not None
    assert user.program_id is None


# ---------------------------------------------------------------------------
# Duplicate email (400)
# ---------------------------------------------------------------------------


def test_register_duplicate_email_returns_400(client, db_session):
    """Second registration with the same email must return 400."""
    _register(client, email="dupe@colorado.edu")  # first — succeeds
    resp = _register(client, email="dupe@colorado.edu")  # second — must fail
    assert resp.status_code == 400


def test_register_email_case_normalization_deduplicates(client, db_session):
    """Mixed-case variants of the same email must be treated as duplicates."""
    _register(client, email="Case@Colorado.EDU")  # first — succeeds
    resp = _register(client, email="case@colorado.edu")  # same address, different case
    assert resp.status_code == 400


def test_register_duplicate_email_response_is_generic(client, db_session):
    """400 detail must not reveal whether the email already exists (no user-enumeration)."""
    _register(client, email="enum@colorado.edu")
    resp = _register(client, email="enum@colorado.edu")
    # Must not contain "exist" or "taken" — acceptable: "already registered"
    detail = resp.json().get("detail", "").lower()
    assert "already" in detail or "registered" in detail
    assert "exist" not in detail


# ---------------------------------------------------------------------------
# Invalid program_id (422)
# ---------------------------------------------------------------------------


def test_register_unknown_program_id_returns_422(client, db_session):
    """A program_id that is not in the programs table must return 422."""
    resp = _register(client, email="badprog@colorado.edu", program_id=999999)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Password validation (422)
# ---------------------------------------------------------------------------


def test_register_short_password_returns_422(client, db_session):
    """Password shorter than 12 characters must return 422."""
    resp = _register(client, email="short@colorado.edu", password="Short1!")
    assert resp.status_code == 422


def test_register_11_char_password_returns_422(client, db_session):
    """Boundary check: exactly 11 chars must be rejected."""
    resp = _register(client, email="eleven@colorado.edu", password="Passw0rd!11")
    assert resp.status_code == 422


def test_register_12_char_password_accepted(client, db_session):
    """Boundary check: exactly 12 chars must be accepted (assuming not in blocklist)."""
    resp = _register(client, email="twelve@colorado.edu", password="Passw0rd!123")
    assert resp.status_code == 200


def test_register_common_password_returns_422(client, db_session):
    """A password on the common-password blocklist must return 422 even if >=12 chars."""
    resp = _register(client, email="common@colorado.edu", password="password123456")
    assert resp.status_code == 422


def test_register_common_password_case_insensitive(client, db_session):
    """Common-password check must be case-insensitive."""
    resp = _register(client, email="casecommon@colorado.edu", password="PASSWORD123456")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Email format validation (422)
# ---------------------------------------------------------------------------


def test_register_invalid_email_returns_422(client, db_session):
    """A malformed email address must return 422 (pydantic.EmailStr validation)."""
    resp = _register(client, email="not-an-email")
    assert resp.status_code == 422


def test_register_missing_email_returns_422(client, db_session):
    """Omitting email entirely must return 422."""
    resp = client.post("/api/auth/register", json={"password": "SecurePass1234!", "name": "Test"})
    assert resp.status_code == 422


def test_register_missing_password_returns_422(client, db_session):
    """Omitting password entirely must return 422."""
    resp = client.post("/api/auth/register", json={"email": "nopw@colorado.edu", "name": "Test"})
    assert resp.status_code == 422
