"""Tests for GET /api/programs and GET /api/programs/{id}/requirements — API-004 (CUAI-29)."""

from __future__ import annotations


def test_list_programs_returns_200(client):
    response = client.get("/api/programs")
    assert response.status_code == 200


def test_list_programs_returns_list(client):
    response = client.get("/api/programs")
    data = response.json()
    assert isinstance(data, list)


def test_list_programs_item_shape(client):
    response = client.get("/api/programs")
    data = response.json()
    if not data:
        return  # No data seeded — skip shape check
    prog = data[0]
    assert "id" in prog
    assert "name" in prog


def test_program_requirements_404_for_nonexistent(client):
    response = client.get("/api/programs/999999/requirements")
    assert response.status_code == 404


def test_program_requirements_response_shape(client):
    # Find a real program first
    programs = client.get("/api/programs").json()
    if not programs:
        return  # No data seeded

    prog_id = programs[0]["id"]
    response = client.get(f"/api/programs/{prog_id}/requirements")
    assert response.status_code == 200
    data = response.json()
    assert "program" in data
    assert "requirements" in data
    assert isinstance(data["requirements"], list)
