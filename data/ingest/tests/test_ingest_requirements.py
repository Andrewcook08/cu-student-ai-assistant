from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from data.ingest.ingest_requirements import parse_course_codes, parse_requirements

DATA_PATH = Path(__file__).resolve().parents[2] / "cu_degree_requirements.json"


@pytest.fixture(scope="session")
def parsed() -> tuple[list[dict], list[dict]]:
    return parse_requirements(DATA_PATH)


@pytest.fixture(scope="session")
def programs(parsed: tuple[list[dict], list[dict]]) -> list[dict]:
    return parsed[0]


@pytest.fixture(scope="session")
def requirements(parsed: tuple[list[dict], list[dict]]) -> list[dict]:
    return parsed[1]


def test_program_count(programs: list[dict]) -> None:
    assert len(programs) == 203


def test_requirement_count(requirements: list[dict]) -> None:
    assert len(requirements) == 6005


def test_degree_type_parsing(programs: list[dict]) -> None:
    counts = Counter(p["degree_type"] for p in programs)
    assert counts["Minor"] == 78
    assert counts["Bachelor of Arts (BA)"] == 54
    assert counts["Certificate"] == 42


def test_program_fields_present(programs: list[dict]) -> None:
    required = {
        "program_name",
        "name_clean",
        "degree_type",
        "total_credits",
        "requirement_count",
    }
    assert all(required <= p.keys() for p in programs)


def test_requirement_fields_present(requirements: list[dict]) -> None:
    required = {
        "program_name",
        "position",
        "requirement_type",
        "raw_id",
        "name",
        "course_codes",
        "credits_text",
        "or_predecessor_position",
    }
    assert all(required <= r.keys() for r in requirements)


def test_no_duplicate_programs(programs: list[dict]) -> None:
    names = [p["program_name"] for p in programs]
    assert len(names) == len(set(names))


def test_or_alternative_has_predecessor(requirements: list[dict]) -> None:
    bad = [
        r
        for r in requirements
        if r["requirement_type"] == "or_alternative" and r["or_predecessor_position"] is None
    ]
    assert len(bad) == 0


def test_or_chain_links(requirements: list[dict]) -> None:
    program_name = "Actuarial Studies and Quantitative Finance - Certificate"
    reqs = [r for r in requirements if r["program_name"] == program_name]
    by_pos = {r["position"]: r for r in reqs}
    assert by_pos[1]["or_predecessor_position"] == 0
    assert by_pos[3]["or_predecessor_position"] == 2


def test_type_classification_counts(requirements: list[dict]) -> None:
    counts = Counter(r["requirement_type"] for r in requirements)
    assert counts["required"] == 4071
    assert counts["or_alternative"] == 609
    assert counts["elective"] == 556
    assert counts["choose_n"] == 283
    assert counts["cross_listed"] == 192
    assert counts["total_credits"] == 174
    assert counts["corequisite_bundle"] == 120


def test_course_codes_extraction() -> None:
    assert parse_course_codes("MATH/STAT 4520") == ["MATH 4520", "STAT 4520"]
    assert parse_course_codes("BCOR 2203&BCOR 2204") == ["BCOR 2203", "BCOR 2204"]
    assert parse_course_codes("orAPPM 1350") == ["APPM 1350"]
    assert parse_course_codes("Choose two of the following three courses:") == []
    assert parse_course_codes("Total Credit Hours") == []


def test_total_credits_extracted(programs: list[dict]) -> None:
    actuarial = next(
        (
            p
            for p in programs
            if p["program_name"] == "Actuarial Studies and Quantitative Finance - Certificate"
        ),
        None,
    )
    assert actuarial is not None
    assert actuarial["total_credits"] == "40-43"


def test_idempotent_parse() -> None:
    programs1, requirements1 = parse_requirements(DATA_PATH)
    programs2, requirements2 = parse_requirements(DATA_PATH)
    assert programs1 == programs2
    assert requirements1 == requirements2
