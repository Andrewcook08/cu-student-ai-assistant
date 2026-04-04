from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

SAMPLE_COURSES = [
    {
        "code": "CSCI 1300",
        "dept": "CSCI",
        "title": "Computer Science 1",
        "credits": "4",
        "description": "Intro to CS",
        "prerequisites_raw": "",
        "attributes": (
            "Engineering & Applied Science General Education"
            ": Humanities & Social Science"
        ),
        "topic_titles": "",
        "instruction_mode": "In Person",
        "campus": "Boulder Main Campus",
        "grading_mode": "Letter Grade",
        "session": "Boulder Main Campus Semester",
        "dates": "2026-01-08 through 2026-04-24",
    },
]

SAMPLE_SECTIONS = [
    {
        "course_code": "CSCI 1300",
        "crn": "12345",
        "section_number": "001",
        "type": "LEC",
        "meets": "MW 11a-12:15p",
        "instructor": "Smith",
        "status": "Open",
        "campus": "Main",
        "dates": "01-08 to 04-24",
    },
]


@pytest.fixture()
def _mock_shared_modules():
    """Inject mock shared.* and neo4j modules so lazy imports resolve without .env."""
    mock_session = MagicMock()
    mock_session.execute.return_value.all.return_value = [("CSCI 1300", 1)]

    mock_insert_fn = MagicMock()
    mock_stmt = MagicMock()
    mock_insert_fn.return_value.values.return_value = mock_stmt
    mock_stmt.on_conflict_do_update.return_value = mock_stmt

    mocks = {
        "shared": MagicMock(),
        "shared.database": MagicMock(
            SessionLocal=MagicMock(return_value=mock_session),
            engine=MagicMock(),
        ),
        "shared.models": MagicMock(),
        "shared.config": MagicMock(
            settings=MagicMock(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="test",
            )
        ),
    }
    with (
        patch.dict(sys.modules, mocks),
        patch("sqlalchemy.dialects.postgresql.insert", mock_insert_fn),
        patch("sqlalchemy.select", MagicMock()),
    ):
        yield mocks, mock_session


@pytest.fixture()
def _mock_neo4j():
    """Inject mock neo4j module."""
    mock_driver = MagicMock()
    mock_neo4j_session = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_neo4j_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

    mock_neo4j = MagicMock()
    mock_neo4j.GraphDatabase.driver.return_value = mock_driver

    with patch.dict(sys.modules, {"neo4j": mock_neo4j}):
        yield mock_neo4j, mock_driver, mock_neo4j_session


class TestWritePostgres:
    @pytest.mark.usefixtures("_mock_shared_modules")
    def test_commits_and_closes_session(self, _mock_shared_modules) -> None:
        _mocks, mock_session = _mock_shared_modules
        from data.ingest.ingest_courses import write_postgres

        write_postgres(SAMPLE_COURSES, SAMPLE_SECTIONS)

        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.usefixtures("_mock_shared_modules")
    def test_executes_upserts(self, _mock_shared_modules) -> None:
        _mocks, mock_session = _mock_shared_modules
        from data.ingest.ingest_courses import write_postgres

        write_postgres(SAMPLE_COURSES, SAMPLE_SECTIONS)

        # At least 3 execute calls: courses upsert, code lookup, sections upsert
        # Plus possibly attributes upsert
        assert mock_session.execute.call_count >= 3

    @pytest.mark.usefixtures("_mock_shared_modules")
    def test_empty_input_still_commits(self, _mock_shared_modules) -> None:
        _mocks, mock_session = _mock_shared_modules
        from data.ingest.ingest_courses import write_postgres

        write_postgres([], [])

        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()


class TestWriteNeo4j:
    @pytest.mark.usefixtures("_mock_shared_modules", "_mock_neo4j")
    def test_creates_and_closes_driver(self, _mock_shared_modules, _mock_neo4j) -> None:
        _mock_neo4j_mod, mock_driver, _mock_neo4j_session = _mock_neo4j
        from data.ingest.ingest_courses import write_neo4j

        write_neo4j(SAMPLE_COURSES, SAMPLE_SECTIONS)

        _mock_neo4j_mod.GraphDatabase.driver.assert_called_once()
        mock_driver.close.assert_called_once()

    @pytest.mark.usefixtures("_mock_shared_modules", "_mock_neo4j")
    def test_executes_merges(self, _mock_shared_modules, _mock_neo4j) -> None:
        _mock_neo4j_mod, _mock_driver, mock_neo4j_session = _mock_neo4j
        from data.ingest.ingest_courses import write_neo4j

        write_neo4j(SAMPLE_COURSES, SAMPLE_SECTIONS)

        # At least 4 execute_write calls: departments, courses, sections, attributes
        assert mock_neo4j_session.execute_write.call_count >= 3
