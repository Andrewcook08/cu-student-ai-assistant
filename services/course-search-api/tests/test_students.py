"""Tests for /api/students — API-005 (CUAI-78).

Covers GET /me auth boundary (regression for is_active fix, PR #51) and the
PUT /me/completed-courses batch-replace endpoint (CUAI-78).
"""

from __future__ import annotations

from shared.auth import create_access_token, hash_password
from shared.models import Course, User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(db_session, *, email: str, is_active: bool = True) -> User:
    user = User(
        email=email,
        password_hash=hash_password("irrelevant"),
        name="Test User",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_course(db_session, *, code: str) -> Course:
    course = Course(
        code=code,
        title=f"Test Course {code}",
        dept=code.split()[0],
        credits="3",
    )
    db_session.add(course)
    db_session.commit()
    return course


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /me
# ---------------------------------------------------------------------------


def test_students_route_exists(client):
    """The /api/students prefix must be registered (even if empty)."""
    response = client.get("/api/students/me")
    assert response.status_code != 404 or response.status_code == 401


def test_students_me_requires_auth(client):
    """Unauthenticated request to a protected student endpoint must return 401/403."""
    response = client.get("/api/students/me")
    assert response.status_code in (401, 403, 422)


def test_students_me_rejects_invalid_token(client):
    """A syntactically valid but fake JWT must be rejected."""
    fake_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI5OTk5OTkifQ.invalid"
    response = client.get("/api/students/me", headers=_auth(fake_token))
    assert response.status_code in (401, 403)


def test_user_is_active_column_exists_in_model():
    """Regression test for PR #51: User model must have is_active field."""
    columns = {col.name for col in User.__table__.columns}
    assert "is_active" in columns, "User.is_active column missing — regression from PR #51 fix"


def test_inactive_user_rejected(client, db_session):
    """Integration test: is_active=False must cause 401, not 200."""
    user = _make_user(db_session, email="inactive@example.com", is_active=False)
    token = create_access_token(str(user.id))
    response = client.get("/api/students/me", headers=_auth(token))
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PUT /me/completed-courses
# ---------------------------------------------------------------------------


def test_put_completed_courses_requires_auth(client):
    """PUT /me/completed-courses without JWT must return 401/403."""
    response = client.put("/api/students/me/completed-courses", json=[])
    assert response.status_code in (401, 403, 422)


def test_put_completed_courses_empty_list(client, db_session):
    """PUT with an empty list clears all completed courses and returns empty list."""
    user = _make_user(db_session, email="clear@example.com")
    token = create_access_token(str(user.id))

    response = client.put(
        "/api/students/me/completed-courses",
        json=[],
        headers=_auth(token),
    )
    assert response.status_code == 200
    assert response.json()["completed_courses"] == []


def test_put_completed_courses_inserts_and_returns_grades(client, db_session):
    """PUT replaces list and response includes course_code and grade values."""
    user = _make_user(db_session, email="grades@example.com")
    _make_course(db_session, code="CSCI 1300")
    _make_course(db_session, code="CSCI 2270")
    token = create_access_token(str(user.id))

    payload = [
        {"course_code": "CSCI 1300", "grade": "A"},
        {"course_code": "CSCI 2270", "grade": "B+"},
    ]
    response = client.put(
        "/api/students/me/completed-courses",
        json=payload,
        headers=_auth(token),
    )
    assert response.status_code == 200
    result = {item["course_code"]: item["grade"] for item in response.json()["completed_courses"]}
    assert result["CSCI 1300"] == "A"
    assert result["CSCI 2270"] == "B+"


def test_put_completed_courses_replaces_existing(client, db_session):
    """Second PUT fully replaces the first list — replace semantics, not append."""
    user = _make_user(db_session, email="replace@example.com")
    _make_course(db_session, code="CSCI 3308")
    _make_course(db_session, code="CSCI 3287")
    token = create_access_token(str(user.id))

    # First PUT — seed two courses
    client.put(
        "/api/students/me/completed-courses",
        json=[{"course_code": "CSCI 3308"}, {"course_code": "CSCI 3287"}],
        headers=_auth(token),
    )

    # Second PUT — replace with only one course
    response = client.put(
        "/api/students/me/completed-courses",
        json=[{"course_code": "CSCI 3308"}],
        headers=_auth(token),
    )
    assert response.status_code == 200
    codes = [item["course_code"] for item in response.json()["completed_courses"]]
    assert codes == ["CSCI 3308"]


def test_put_completed_courses_null_grade_allowed(client, db_session):
    """grade may be omitted (null) — the field is optional."""
    user = _make_user(db_session, email="nullgrade@example.com")
    _make_course(db_session, code="CSCI 4830")
    token = create_access_token(str(user.id))

    response = client.put(
        "/api/students/me/completed-courses",
        json=[{"course_code": "CSCI 4830"}],
        headers=_auth(token),
    )
    assert response.status_code == 200
    item = response.json()["completed_courses"][0]
    assert item["course_code"] == "CSCI 4830"
    assert item["grade"] is None


def test_put_completed_courses_duplicate_code_returns_400(client, db_session):
    """Duplicate course_code within one payload must return 400."""
    user = _make_user(db_session, email="dup@example.com")
    _make_course(db_session, code="CSCI 1300")
    token = create_access_token(str(user.id))

    response = client.put(
        "/api/students/me/completed-courses",
        json=[{"course_code": "CSCI 1300"}, {"course_code": "CSCI 1300"}],
        headers=_auth(token),
    )
    assert response.status_code == 400


def test_put_completed_courses_unknown_code_returns_422(client, db_session):
    """A course_code that doesn't exist in the courses table must return 422."""
    user = _make_user(db_session, email="unknown@example.com")
    token = create_access_token(str(user.id))

    response = client.put(
        "/api/students/me/completed-courses",
        json=[{"course_code": "FAKE 9999"}],
        headers=_auth(token),
    )
    assert response.status_code == 422


def test_put_completed_courses_oversized_payload_returns_422(client, db_session):
    """A payload exceeding 200 items must be rejected with 422 by the size cap.

    Seeds 201 valid courses so the only failure mode is the size cap, not the
    unknown-code check (both return 422, but this ensures we're testing the right path).
    """
    user = _make_user(db_session, email="oversized@example.com")
    token = create_access_token(str(user.id))

    # Seed 201 valid courses so the unknown-code check cannot mask a broken size cap
    for i in range(201):
        _make_course(db_session, code=f"TEST {i:04d}")

    payload = [{"course_code": f"TEST {i:04d}"} for i in range(201)]
    response = client.put(
        "/api/students/me/completed-courses",
        json=payload,
        headers=_auth(token),
    )
    assert response.status_code == 422
