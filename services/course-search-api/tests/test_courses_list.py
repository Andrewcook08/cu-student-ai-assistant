"""Tests for GET /api/courses — API-001 (CUAI-26)."""

from __future__ import annotations


def test_list_courses_returns_200(client):
    response = client.get("/api/courses")
    assert response.status_code == 200


def test_list_courses_response_shape(client):
    response = client.get("/api/courses")
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "offset" in data
    assert "limit" in data


def test_list_courses_empty_db_returns_empty_list(client):
    """With no data seeded, items is an empty list and total is 0."""
    response = client.get("/api/courses")
    data = response.json()
    assert isinstance(data["items"], list)
    assert data["total"] >= 0


def test_list_courses_pagination_offset(client):
    response = client.get("/api/courses?offset=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 10
    assert data["offset"] == 0
    assert data["limit"] == 10


def test_list_courses_dept_filter(client):
    response = client.get("/api/courses?dept=CSCI")
    assert response.status_code == 200
    data = response.json()
    for course in data["items"]:
        assert course["dept"] == "CSCI"


def test_list_courses_status_filter(client):
    response = client.get("/api/courses?status=Open")
    assert response.status_code == 200
    data = response.json()
    # Each returned course must have at least one Open section
    for course in data["items"]:
        statuses = [s["status"] for s in course.get("sections", [])]
        assert "Open" in statuses


def test_list_courses_text_search(client):
    response = client.get("/api/courses?q=computer")
    assert response.status_code == 200
    assert response.json()["items"] is not None


def test_list_courses_invalid_limit_rejected(client):
    response = client.get("/api/courses?limit=9999")
    assert response.status_code == 422
