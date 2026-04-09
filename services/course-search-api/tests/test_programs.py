"""Tests for GET /api/programs and GET /api/programs/{id}/requirements — API-004 (CUAI-29)."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Auth lock-in
# ---------------------------------------------------------------------------


def test_list_programs_requires_auth_no_header(client):
    """Missing Authorization header → 403 from HTTPBearer."""
    response = client.get("/api/programs")
    assert response.status_code == 403


def test_list_programs_rejects_invalid_token(client):
    """Invalid Bearer token → 401 from get_current_user."""
    response = client.get("/api/programs", headers={"Authorization": "Bearer bad-token"})
    assert response.status_code == 401


def test_program_requirements_requires_auth_no_header(client):
    """Missing Authorization header → 403 from HTTPBearer."""
    response = client.get("/api/programs/1/requirements")
    assert response.status_code == 403


def test_program_requirements_rejects_invalid_token(client):
    """Invalid Bearer token → 401 from get_current_user."""
    response = client.get(
        "/api/programs/1/requirements", headers={"Authorization": "Bearer bad-token"}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Route behaviour
# ---------------------------------------------------------------------------


def test_list_programs_returns_200(client, auth_headers):
    response = client.get("/api/programs", headers=auth_headers)
    assert response.status_code == 200


def test_list_programs_returns_list(client, auth_headers):
    response = client.get("/api/programs", headers=auth_headers)
    data = response.json()
    assert isinstance(data, list)


def test_list_programs_item_shape(client, auth_headers):
    response = client.get("/api/programs", headers=auth_headers)
    data = response.json()
    if not data:
        return  # No data seeded — skip shape check
    prog = data[0]
    assert "id" in prog
    assert "name" in prog


def test_program_requirements_404_for_nonexistent(client, auth_headers):
    response = client.get("/api/programs/999999/requirements", headers=auth_headers)
    assert response.status_code == 404


def test_program_requirements_response_shape(client, auth_headers):
    # Find a real program first
    programs = client.get("/api/programs", headers=auth_headers).json()
    if not programs:
        return  # No data seeded

    prog_id = programs[0]["id"]
    response = client.get(f"/api/programs/{prog_id}/requirements", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "program" in data
    assert "requirements" in data
    assert isinstance(data["requirements"], list)
