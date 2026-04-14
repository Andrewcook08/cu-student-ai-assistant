"""Tests for POST /api/auth/login — AUTH-002 (CUAI-54).

Uses the db_session fixture from conftest.py (transactional rollback — all
rows inserted by tests are rolled back at teardown, no manual cleanup needed).
"""

from __future__ import annotations

from unittest.mock import patch

from jose import jwt
from shared.auth import hash_password
from shared.config import settings
from shared.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_user(
    db_session,
    *,
    email: str = "login@colorado.edu",
    password: str = "SecurePass1234!",
    is_active: bool = True,
) -> User:
    """Insert a user directly into the DB with a known password."""
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        name="Test User",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login(client, *, email: str = "login@colorado.edu", password: str = "SecurePass1234!"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


def test_login_returns_200_with_correct_shape(client, db_session):
    """Valid credentials return 200 with access_token, token_type='bearer', expires_in."""
    _create_user(db_session, email="shape@colorado.edu")
    resp = _login(client, email="shape@colorado.edu")
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert isinstance(body["expires_in"], int)
    assert body["expires_in"] > 0


def test_login_expires_in_matches_config(client, db_session):
    """expires_in must equal settings.jwt_expire_minutes * 60 (seconds)."""
    _create_user(db_session, email="expires@colorado.edu")
    resp = _login(client, email="expires@colorado.edu")
    assert resp.status_code == 200
    assert resp.json()["expires_in"] == settings.jwt_expire_minutes * 60


def test_login_jwt_sub_is_user_id_only(client, db_session):
    """JWT sub must be user_id only — no email or PII in the token payload."""
    user = _create_user(db_session, email="jwtcheck@colorado.edu")
    resp = _login(client, email="jwtcheck@colorado.edu")
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == str(user.id)
    assert "email" not in payload


def test_login_email_is_case_insensitive(client, db_session):
    """Login normalises email to lowercase — mixed-case variants must succeed."""
    _create_user(db_session, email="mixedcase@colorado.edu")
    resp = _login(client, email="MixedCase@Colorado.EDU")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Failure paths — 401 for every failure mode (no user enumeration)
# ---------------------------------------------------------------------------


def test_login_unknown_email_returns_401_not_404(client, db_session):
    """Non-existent email must return 401, never 404 — don't leak user existence.

    Also asserts WWW-Authenticate: Bearer is present (RFC 7235).
    """
    resp = _login(client, email="nobody@colorado.edu")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_login_wrong_password_returns_401(client, db_session):
    """Wrong password must return 401."""
    _create_user(db_session, email="wrongpw@colorado.edu")
    resp = _login(client, email="wrongpw@colorado.edu", password="WrongPassword999!")
    assert resp.status_code == 401


def test_login_inactive_user_returns_401(client, db_session):
    """Inactive user must return 401 even when the password is correct."""
    _create_user(db_session, email="inactive@colorado.edu", is_active=False)
    resp = _login(client, email="inactive@colorado.edu")
    assert resp.status_code == 401


def test_login_failure_detail_identical_for_all_failure_modes(client, db_session):
    """The 401 detail string must be identical for no-user, bad-password, and inactive-user.

    Differing messages would allow user-enumeration attacks.
    """
    _create_user(db_session, email="badpw@colorado.edu")
    _create_user(db_session, email="inactive2@colorado.edu", is_active=False)

    resp_no_user = _login(client, email="nobody2@colorado.edu")
    resp_bad_pw = _login(client, email="badpw@colorado.edu", password="Wrong123456!")
    resp_inactive = _login(client, email="inactive2@colorado.edu")

    assert resp_no_user.status_code == resp_bad_pw.status_code == resp_inactive.status_code == 401
    detail_no_user = resp_no_user.json()["detail"]
    detail_bad_pw = resp_bad_pw.json()["detail"]
    detail_inactive = resp_inactive.json()["detail"]
    assert detail_no_user == detail_bad_pw == detail_inactive


def test_login_verify_password_called_even_for_unknown_email(client, db_session):
    """verify_password must be called even when the email doesn't exist.

    If it were skipped, the no-user response would be orders of magnitude
    faster than the bad-password response, leaking which emails are enrolled
    (timing side-channel / user enumeration).
    """
    with patch("course_search_api.routes.auth.verify_password", return_value=False) as mock_vp:
        resp = _login(client, email="nobody@colorado.edu")
    assert resp.status_code == 401
    mock_vp.assert_called_once()


# ---------------------------------------------------------------------------
# Input validation (422)
# ---------------------------------------------------------------------------


def test_login_missing_email_returns_422(client):
    """Omitting email entirely must return 422."""
    resp = client.post("/api/auth/login", json={"password": "SecurePass1234!"})
    assert resp.status_code == 422


def test_login_missing_password_returns_422(client):
    """Omitting password entirely must return 422."""
    resp = client.post("/api/auth/login", json={"email": "test@colorado.edu"})
    assert resp.status_code == 422


def test_login_empty_body_returns_422(client):
    """Empty JSON body must return 422."""
    resp = client.post("/api/auth/login", json={})
    assert resp.status_code == 422


def test_login_empty_password_returns_422(client):
    """Empty string password must return 422 (not reach bcrypt)."""
    resp = client.post("/api/auth/login", json={"email": "test@colorado.edu", "password": ""})
    assert resp.status_code == 422


def test_login_invalid_email_format_returns_422(client):
    """Non-email string must return 422 (pydantic EmailStr validation)."""
    resp = client.post("/api/auth/login", json={"email": "not-an-email", "password": "SecurePass1234!"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_login_rate_limit_returns_429_on_sixth_attempt(client, db_session):
    """The 6th login attempt within one minute must return 429 (5/minute limit).

    Asserts requests 1-5 are NOT 429, proving the limit is exactly 5 and not lower.
    """
    for i in range(5):
        resp = _login(client, email="ratelimit@colorado.edu")
        assert resp.status_code != 429, f"Request {i + 1} was unexpectedly rate-limited"
    resp = _login(client, email="ratelimit@colorado.edu")
    assert resp.status_code == 429
