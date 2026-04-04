from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from data.ingest.ingest_courses import parse_classes
from data.ingest.parse_prerequisites import parse_prerequisites

DATA_PATH = Path(__file__).resolve().parents[2] / "cu_classes.json"


@pytest.fixture(scope="session")
def courses() -> list[dict]:
    courses, _ = parse_classes(DATA_PATH)
    return courses


@pytest.fixture(scope="session")
def edges(courses: list[dict]) -> list[dict]:
    return parse_prerequisites(courses)


@pytest.fixture(scope="session")
def edges_by_source(edges: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for e in edges:
        result.setdefault(e["source_code"], []).append(e)
    return result


# ── Acceptance criteria ───────────────────────────────────────────────────────


def test_total_edges_above_2000(edges: list[dict]) -> None:
    assert len(edges) > 2000


def test_all_edges_have_raw_text(edges: list[dict]) -> None:
    assert all(e["raw_text"] for e in edges)


def test_matched_edges_have_min_grade(edges: list[dict]) -> None:
    """Edges from strings that mention a grade should have min_grade set."""
    for e in edges:
        if "minimum" in e["raw_text"].lower() or "min " in e["raw_text"].lower():
            assert e["min_grade"], f"Missing min_grade for: {e['raw_text'][:80]}"


def test_typo_resilience(courses: list[dict]) -> None:
    """Typo strings like 'prerequiste' and 'prerequsite' parse without crashing."""
    typo_courses = [
        c for c in courses
        if c.get("prerequisites_raw")
        and ("prerequiste" in c["prerequisites_raw"] or "prerequsite" in c["prerequisites_raw"])
    ]
    assert len(typo_courses) > 0, "Expected typo courses in data"
    # Should not raise
    edges = parse_prerequisites(typo_courses)
    assert len(edges) > 0, "Typo courses should still produce edges"


def test_parse_rate(courses: list[dict], edges: list[dict]) -> None:
    """At least 80% of courses with prerequisites are handled (edges or restriction)."""
    with_prereqs = [c for c in courses if c.get("prerequisites_raw")]
    sources_with_edges = {e["source_code"] for e in edges}
    restriction_only = [
        c for c in with_prereqs
        if c["prerequisites_raw"].startswith("Restricted")
        and c["code"] not in sources_with_edges
    ]
    handled = len(sources_with_edges) + len(restriction_only)
    rate = handled / len(with_prereqs)
    assert rate >= 0.80, f"Parse rate {rate:.1%} is below 80%"


# ── Pattern-specific tests ────────────────────────────────────────────────────


def test_single_prereq(edges_by_source: dict[str, list[dict]]) -> None:
    """ACCT 3220 requires BASE 2104 (single prerequisite)."""
    acct_edges = edges_by_source.get("ACCT 3220", [])
    targets = {e["target_code"] for e in acct_edges}
    assert "BASE 2104" in targets
    assert acct_edges[0]["type"] == "prerequisite"
    assert acct_edges[0]["min_grade"] == "D-"


def test_or_pattern(edges_by_source: dict[str, list[dict]]) -> None:
    """ACCT 5550 requires ACCT 4620 or ACCT 5620 (OR alternatives)."""
    edges = edges_by_source.get("ACCT 5550", [])
    targets = {e["target_code"] for e in edges}
    assert "ACCT 4620" in targets
    assert "ACCT 5620" in targets


def test_and_pattern(edges_by_source: dict[str, list[dict]]) -> None:
    """APRD 3001 requires APRD 2005 and APRD 2006 (AND requirements)."""
    edges = edges_by_source.get("APRD 3001", [])
    targets = {e["target_code"] for e in edges}
    assert "APRD 2005" in targets
    assert "APRD 2006" in targets


def test_corequisite_type(edges_by_source: dict[str, list[dict]]) -> None:
    """ACCT 5550 is a corequisite (type should be 'corequisite')."""
    edges = edges_by_source.get("ACCT 5550", [])
    assert all(e["type"] == "corequisite" for e in edges)


def test_restriction_no_edges(courses: list[dict], edges: list[dict]) -> None:
    """Restriction-only courses produce no edges."""
    sources_with_edges = {e["source_code"] for e in edges}
    restriction_only = [
        c for c in courses
        if c.get("prerequisites_raw", "").startswith("Restricted to ")
        and c["code"] not in sources_with_edges
    ]
    # There should be many restriction-only courses that have no edges
    assert len(restriction_only) > 1000


def test_abbreviated_code_expansion(edges_by_source: dict[str, list[dict]]) -> None:
    """ACCT 4250 has 'ACCT 3220 or 3225' — 3225 should expand to ACCT 3225."""
    edges = edges_by_source.get("ACCT 4250", [])
    targets = {e["target_code"] for e in edges}
    assert "ACCT 3225" in targets
    assert "ACCT 3220" in targets


def test_idempotent_parse(courses: list[dict]) -> None:
    edges1 = parse_prerequisites(courses)
    edges2 = parse_prerequisites(courses)
    assert edges1 == edges2


def test_edge_fields_present(edges: list[dict]) -> None:
    required = {"source_code", "target_code", "type", "min_grade", "raw_text"}
    assert all(required <= e.keys() for e in edges)


def test_edge_types_valid(edges: list[dict]) -> None:
    valid_types = {"prerequisite", "corequisite"}
    assert all(e["type"] in valid_types for e in edges)


# ── Neo4j write tests ─────────────────────────────────────────────────────────

SAMPLE_EDGES = [
    {
        "source_code": "CSCI 2270",
        "target_code": "CSCI 1300",
        "type": "prerequisite",
        "min_grade": "C-",
        "raw_text": "Requires prerequisite of CSCI 1300 (minimum grade C-).",
    },
    {
        "source_code": "CSCI 3104",
        "target_code": "CSCI 2270",
        "type": "prerequisite",
        "min_grade": "C-",
        "raw_text": "Requires prerequisite of CSCI 2270 (minimum grade C-).",
    },
]


@pytest.fixture()
def _mock_prereq_neo4j():
    mock_driver = MagicMock()
    mock_neo4j_session = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_neo4j_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

    mock_neo4j = MagicMock()
    mock_neo4j.GraphDatabase.driver.return_value = mock_driver

    mock_settings = MagicMock(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="test",
    )

    with patch.dict(sys.modules, {
        "neo4j": mock_neo4j,
        "shared": MagicMock(),
        "shared.config": MagicMock(settings=mock_settings),
    }):
        yield mock_neo4j, mock_driver, mock_neo4j_session


class TestWriteNeo4jPrerequisites:
    def test_creates_and_closes_driver(self, _mock_prereq_neo4j) -> None:
        mock_neo4j, mock_driver, mock_neo4j_session = _mock_prereq_neo4j
        from data.ingest.parse_prerequisites import write_neo4j_prerequisites

        write_neo4j_prerequisites(SAMPLE_EDGES)

        mock_neo4j.GraphDatabase.driver.assert_called_once()
        mock_driver.close.assert_called_once()

    def test_executes_write(self, _mock_prereq_neo4j) -> None:
        mock_neo4j, mock_driver, mock_neo4j_session = _mock_prereq_neo4j
        from data.ingest.parse_prerequisites import write_neo4j_prerequisites

        write_neo4j_prerequisites(SAMPLE_EDGES)

        mock_neo4j_session.execute_write.assert_called_once()

    def test_empty_edges_no_crash(self, _mock_prereq_neo4j) -> None:
        mock_neo4j, mock_driver, mock_neo4j_session = _mock_prereq_neo4j
        from data.ingest.parse_prerequisites import write_neo4j_prerequisites

        write_neo4j_prerequisites([])

        mock_driver.close.assert_called_once()
