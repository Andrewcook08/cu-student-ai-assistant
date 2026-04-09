"""Tests for GET /api/courses/{code} — API-002 (CUAI-27)."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Auth lock-in
# ---------------------------------------------------------------------------


def test_course_detail_requires_auth(client):
    """GET /api/courses/{code} without a Bearer token must return 401 or 403."""
    response = client.get("/api/courses/FAKE 9999")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Route behaviour
# ---------------------------------------------------------------------------


def test_course_detail_404_for_nonexistent(client, auth_headers):
    response = client.get("/api/courses/FAKE 9999", headers=auth_headers)
    assert response.status_code == 404


def test_course_detail_404_message(client, auth_headers):
    response = client.get("/api/courses/FAKE 9999", headers=auth_headers)
    data = response.json()
    assert "detail" in data


def test_course_detail_response_shape_when_exists(client, auth_headers):
    """If the course exists, it must have expected fields."""
    # First ensure there's at least one course
    list_resp = client.get("/api/courses?limit=1", headers=auth_headers)
    items = list_resp.json()["items"]
    if not items:
        return  # Skip — no data seeded in test DB

    code = items[0]["code"]
    response = client.get(f"/api/courses/{code}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "code" in data
    assert "title" in data
    assert "credits" in data
    assert "dept" in data
    assert "sections" in data
    assert "attributes" in data  # included_attributes=True for detail endpoint


def test_course_detail_includes_sections(client, auth_headers):
    list_resp = client.get("/api/courses?limit=1", headers=auth_headers)
    items = list_resp.json()["items"]
    if not items:
        return

    code = items[0]["code"]
    response = client.get(f"/api/courses/{code}", headers=auth_headers)
    data = response.json()
    assert isinstance(data["sections"], list)
