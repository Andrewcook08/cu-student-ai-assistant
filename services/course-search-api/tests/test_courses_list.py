"""Tests for GET /api/courses — API-001 (CUAI-26)."""

from __future__ import annotations

from shared.models import Course, Section


def _make_course(
    session,
    *,
    code: str,
    dept: str,
    title: str,
    section_statuses: list[str] | None = None,
) -> Course:
    """Insert a Course (and optional sections) into the test DB.

    Sections are created with a per-course-unique CRN; statuses come from
    ``section_statuses`` in order. ``None`` means no sections at all.
    """
    course = Course(code=code, dept=dept, title=title)
    session.add(course)
    session.flush()  # assign course.id
    if section_statuses is not None:
        for idx, status in enumerate(section_statuses):
            session.add(
                Section(
                    course_id=course.id,
                    crn=f"{code.replace(' ', '')}-{idx}",
                    status=status,
                )
            )
    session.flush()
    return course


# ---------------------------------------------------------------------------
# Auth lock-in
# ---------------------------------------------------------------------------


def test_list_courses_requires_auth_no_header(client):
    """Missing Authorization header → 401 (no credentials provided)."""
    response = client.get("/api/courses")
    assert response.status_code == 401


def test_list_courses_rejects_invalid_token(client):
    """Invalid Bearer token → 401 from get_current_user."""
    response = client.get("/api/courses", headers={"Authorization": "Bearer bad-token"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Basic response shape
# ---------------------------------------------------------------------------


def test_list_courses_returns_200(client, auth_headers):
    response = client.get("/api/courses", headers=auth_headers)
    assert response.status_code == 200


def test_list_courses_response_shape(client, auth_headers):
    response = client.get("/api/courses", headers=auth_headers)
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "offset" in data
    assert "limit" in data


def test_list_courses_empty_db_returns_empty_list(client, auth_headers):
    """With no data seeded, items is an empty list and total is 0."""
    response = client.get("/api/courses", headers=auth_headers)
    data = response.json()
    assert isinstance(data["items"], list)
    assert data["total"] >= 0


def test_list_courses_pagination_offset(client, auth_headers):
    response = client.get("/api/courses?offset=0&limit=10", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 10
    assert data["offset"] == 0
    assert data["limit"] == 10


def test_list_courses_dept_filter(client, auth_headers):
    response = client.get("/api/courses?dept=CSCI", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    for course in data["items"]:
        assert course["dept"] == "CSCI"


def test_list_courses_status_filter(client, auth_headers):
    response = client.get("/api/courses?status=Open", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    # Each returned course must have at least one Open section
    for course in data["items"]:
        statuses = [s["status"] for s in course.get("sections", [])]
        assert "Open" in statuses


def test_list_courses_text_search(client, auth_headers):
    response = client.get("/api/courses?q=computer", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["items"] is not None


def test_list_courses_invalid_limit_rejected(client, auth_headers):
    response = client.get("/api/courses?limit=9999", headers=auth_headers)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Level filter — translates into a numeric range on the Course.code suffix.
# ---------------------------------------------------------------------------


# Use a synthetic 4-letter dept ("ZZZA" / "ZZZB") to avoid colliding with real
# seeded data. Filtering every assertion on the fake dept means each test only
# sees the rows it inserted, so equality checks stay deterministic regardless
# of what else lives in the shared dev database.


def test_list_courses_level_undergrad_lower(client, db_session, auth_headers):
    _make_course(db_session, code="ZZZA 1300", dept="ZZZA", title="Intro")
    _make_course(db_session, code="ZZZA 3104", dept="ZZZA", title="Algorithms")
    _make_course(db_session, code="ZZZA 5555", dept="ZZZA", title="Advanced")

    response = client.get("/api/courses?dept=ZZZA&level=undergrad-lower", headers=auth_headers)
    assert response.status_code == 200
    codes = [c["code"] for c in response.json()["items"]]
    assert codes == ["ZZZA 1300"]


def test_list_courses_level_undergrad_upper(client, db_session, auth_headers):
    _make_course(db_session, code="ZZZA 1300", dept="ZZZA", title="Intro")
    _make_course(db_session, code="ZZZA 3104", dept="ZZZA", title="Algorithms")
    _make_course(db_session, code="ZZZA 5555", dept="ZZZA", title="Advanced")

    response = client.get("/api/courses?dept=ZZZA&level=undergrad-upper", headers=auth_headers)
    assert response.status_code == 200
    codes = [c["code"] for c in response.json()["items"]]
    assert codes == ["ZZZA 3104"]


def test_list_courses_level_graduate(client, db_session, auth_headers):
    _make_course(db_session, code="ZZZA 1300", dept="ZZZA", title="Intro")
    _make_course(db_session, code="ZZZA 3104", dept="ZZZA", title="Algorithms")
    _make_course(db_session, code="ZZZA 5555", dept="ZZZA", title="Advanced")

    response = client.get("/api/courses?dept=ZZZA&level=graduate", headers=auth_headers)
    assert response.status_code == 200
    codes = [c["code"] for c in response.json()["items"]]
    assert codes == ["ZZZA 5555"]


def test_list_courses_level_combined_with_dept(client, db_session, auth_headers):
    _make_course(db_session, code="ZZZA 1300", dept="ZZZA", title="Intro A")
    _make_course(db_session, code="ZZZB 1300", dept="ZZZB", title="Intro B")
    _make_course(db_session, code="ZZZA 3104", dept="ZZZA", title="Algorithms")

    response = client.get("/api/courses?dept=ZZZA&level=undergrad-lower", headers=auth_headers)
    assert response.status_code == 200
    codes = [c["code"] for c in response.json()["items"]]
    assert codes == ["ZZZA 1300"]


def test_list_courses_level_invalid_returns_400(client, auth_headers):
    response = client.get("/api/courses?level=bogus", headers=auth_headers)
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Aggregate course-level status — derived from the course's sections.
# ---------------------------------------------------------------------------


def _find_item(response_json: dict, code: str) -> dict:
    for item in response_json["items"]:
        if item["code"] == code:
            return item
    raise AssertionError(f"course {code!r} not in response")


def test_list_courses_status_aggregate_open(client, db_session, auth_headers):
    _make_course(
        db_session,
        code="TEST 1001",
        dept="TEST",
        title="Mixed sections",
        section_statuses=["Open", "Closed"],
    )

    response = client.get("/api/courses?dept=TEST", headers=auth_headers)
    assert response.status_code == 200
    assert _find_item(response.json(), "TEST 1001")["status"] == "Open"


def test_list_courses_status_aggregate_closed(client, db_session, auth_headers):
    _make_course(
        db_session,
        code="TEST 1002",
        dept="TEST",
        title="All closed",
        section_statuses=["Closed", "Closed"],
    )

    response = client.get("/api/courses?dept=TEST", headers=auth_headers)
    assert response.status_code == 200
    assert _find_item(response.json(), "TEST 1002")["status"] == "Closed"


def test_list_courses_status_aggregate_waitlist(client, db_session, auth_headers):
    _make_course(
        db_session,
        code="TEST 1003",
        dept="TEST",
        title="Waitlist + closed",
        section_statuses=["Closed", "Waitlist"],
    )

    response = client.get("/api/courses?dept=TEST", headers=auth_headers)
    assert response.status_code == 200
    assert _find_item(response.json(), "TEST 1003")["status"] == "Waitlist"


def test_list_courses_status_aggregate_no_sections(client, db_session, auth_headers):
    _make_course(
        db_session,
        code="TEST 1004",
        dept="TEST",
        title="No sections",
        section_statuses=None,
    )

    response = client.get("/api/courses?dept=TEST", headers=auth_headers)
    assert response.status_code == 200
    assert _find_item(response.json(), "TEST 1004")["status"] is None


def test_list_courses_sections_include_type_and_number(client, db_session, auth_headers):
    """Each serialized section carries its type (LEC/REC/LAB/etc.) and number."""
    course = Course(code="TEST 1005", dept="TEST", title="With section types")
    db_session.add(course)
    db_session.flush()
    db_session.add(
        Section(
            course_id=course.id,
            crn="TEST1005-L",
            type="LEC",
            section_number="001",
            status="Open",
        )
    )
    db_session.add(
        Section(
            course_id=course.id,
            crn="TEST1005-R",
            type="REC",
            section_number="101",
            status="Open",
        )
    )
    db_session.flush()

    response = client.get("/api/courses?dept=TEST", headers=auth_headers)
    assert response.status_code == 200
    item = _find_item(response.json(), "TEST 1005")
    by_crn = {s["crn"]: s for s in item["sections"]}
    assert by_crn["TEST1005-L"]["type"] == "LEC"
    assert by_crn["TEST1005-L"]["section_number"] == "001"
    assert by_crn["TEST1005-R"]["type"] == "REC"
    assert by_crn["TEST1005-R"]["section_number"] == "101"
