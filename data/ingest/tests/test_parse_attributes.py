from __future__ import annotations

from pathlib import Path

import pytest

from data.ingest.ingest_courses import parse_attributes, parse_classes

DATA_PATH = Path(__file__).resolve().parents[2] / "cu_classes.json"


def test_single_line() -> None:
    result = parse_attributes("CMDI Core: Historical Views-CMDI")
    assert result == [("CMDI Core", "Historical Views-CMDI")]


def test_multi_line() -> None:
    raw = (
        "Business General Education: Natural Science\n"
        "CMDI Core: Natural World\n"
        "Arts & Sciences: Distribution-Natural Sciences"
    )
    result = parse_attributes(raw)
    assert len(result) == 3
    assert result[0] == ("Business General Education", "Natural Science")
    assert result[1] == ("CMDI Core", "Natural World")
    assert result[2] == ("Arts & Sciences", "Distribution-Natural Sciences")


def test_empty_string() -> None:
    assert parse_attributes("") == []


def test_no_colon_skipped() -> None:
    result = parse_attributes("Some text without delimiter\nValid College: Category")
    assert result == [("Valid College", "Category")]


def test_whitespace_stripped() -> None:
    result = parse_attributes("  College Name : Category Name  ")
    assert result == [("College Name", "Category Name")]


@pytest.fixture(scope="session")
def courses() -> list[dict]:
    return parse_classes(DATA_PATH)[0]


def test_courses_with_attributes_count(courses: list[dict]) -> None:
    """About 1,358 courses have non-empty attributes."""
    count = sum(1 for c in courses if c["attributes"].strip())
    assert 1200 <= count <= 1300


def test_engineering_humanities_attributes(courses: list[dict]) -> None:
    """Validate the acceptance criteria query equivalent."""
    matches = []
    for c in courses:
        for college, category in parse_attributes(c["attributes"]):
            if "Engineering" in college and "Humanities" in category:
                matches.append(c["code"])
                break
    assert len(matches) > 0
