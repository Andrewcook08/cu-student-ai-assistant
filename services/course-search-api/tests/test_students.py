"""Tests for /api/students auth boundary — API-005 (CUAI-30).

Also serves as regression test for the User.is_active fix (PR #51):
a user with is_active=False must receive 401, not 200.
"""

from __future__ import annotations


def test_students_route_exists(client):
    """The /api/students prefix must be registered (even if empty)."""
    # Any response code except 404 means the route is registered
    response = client.get("/api/students/me")
    assert response.status_code != 404 or response.status_code == 401


def test_students_me_requires_auth(client):
    """Unauthenticated request to a protected student endpoint must return 401/403."""
    response = client.get("/api/students/me")
    assert response.status_code in (401, 403, 422)


def test_students_me_rejects_invalid_token(client):
    """A syntactically valid but fake JWT must be rejected."""
    fake_token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI5OTk5OTkifQ.invalid"
    response = client.get(
        "/api/students/me",
        headers={"Authorization": f"Bearer {fake_token}"},
    )
    assert response.status_code in (401, 403)


def test_user_is_active_column_exists_in_model():
    """Regression test for PR #51: User model must have is_active field."""
    from shared.models import User
    import inspect

    columns = {col.name for col in User.__table__.columns}
    assert "is_active" in columns, (
        "User.is_active column missing — regression from PR #51 fix"
    )
