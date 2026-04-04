from __future__ import annotations

from pathlib import Path

import pytest

from data.ingest.ingest_courses import parse_classes

DATA_PATH = Path(__file__).resolve().parents[2] / "cu_classes.json"


@pytest.fixture(scope="session")
def parsed() -> tuple[list[dict], list[dict]]:
    return parse_classes(DATA_PATH)


@pytest.fixture(scope="session")
def courses(parsed: tuple[list[dict], list[dict]]) -> list[dict]:
    return parsed[0]


@pytest.fixture(scope="session")
def sections(parsed: tuple[list[dict], list[dict]]) -> list[dict]:
    return parsed[1]


def test_parse_classes_course_count(courses: list[dict]) -> None:
    # 3735 raw entries, deduplicated to 3410 unique course codes
    assert len(courses) == 3410


def test_parse_classes_section_count(sections: list[dict]) -> None:
    assert len(sections) == 9470


def test_parse_classes_department_count(courses: list[dict]) -> None:
    assert len({c["dept"] for c in courses}) == 152


def test_crn_cleaning(sections: list[dict]) -> None:
    assert all(s["crn"].isdigit() for s in sections)


def test_dept_extraction(courses: list[dict]) -> None:
    assert all(c["dept"] == c["code"].split()[0] for c in courses)


def test_credits_preserved_as_text(courses: list[dict]) -> None:
    assert all(isinstance(c["credits"], str) for c in courses)


def test_no_duplicate_courses(courses: list[dict]) -> None:
    codes = [c["code"] for c in courses]
    assert len(codes) == len(set(codes))


def test_section_fields_present(sections: list[dict]) -> None:
    required = {
        "course_code", "crn", "section_number", "type", "meets",
        "instructor", "status", "campus", "dates",
    }
    assert all(required <= s.keys() for s in sections)


def test_idempotent_parse() -> None:
    courses1, sections1 = parse_classes(DATA_PATH)
    courses2, sections2 = parse_classes(DATA_PATH)
    assert courses1 == courses2
    assert sections1 == sections2


def test_topic_titles_preserved(courses: list[dict]) -> None:
    by_code = {c["code"]: c for c in courses}

    # CSCI 7000 appears 17 times but has 16 unique titles (one repeated)
    csci7000 = by_code["CSCI 7000"]
    assert isinstance(csci7000["topic_titles"], str)
    assert len(csci7000["topic_titles"].split("|")) == 16

    # WRTG 3020 has 39 entries but 24 unique titles
    wrtg3020 = by_code["WRTG 3020"]
    assert isinstance(wrtg3020["topic_titles"], str)
    assert len(wrtg3020["topic_titles"].split("|")) == 24

    # Non-topics course has an empty topic_titles string
    csci1300 = by_code["CSCI 1300"]
    assert csci1300["topic_titles"] == ""
