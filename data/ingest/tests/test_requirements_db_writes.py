from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

SAMPLE_PROGRAMS = [
    {
        "program_name": "Computer Science - Bachelor of Arts (BA)",
        "name_clean": "Computer Science",
        "degree_type": "Bachelor of Arts (BA)",
        "total_credits": "120",
        "requirement_count": 3,
    },
]

SAMPLE_REQUIREMENTS = [
    {
        "program_name": "Computer Science - Bachelor of Arts (BA)",
        "position": 0,
        "requirement_type": "required",
        "raw_id": "CSCI 1300",
        "name": "Computer Science 1: Starting Computing",
        "course_codes": ["CSCI 1300"],
        "credits_text": "",
        "or_predecessor_position": None,
    },
    {
        "program_name": "Computer Science - Bachelor of Arts (BA)",
        "position": 1,
        "requirement_type": "or_alternative",
        "raw_id": "orCSCI 1310",
        "name": "Computer Science 1: Starting Computing for Engineers",
        "course_codes": ["CSCI 1310"],
        "credits_text": "",
        "or_predecessor_position": 0,
    },
    {
        "program_name": "Computer Science - Bachelor of Arts (BA)",
        "position": 2,
        "requirement_type": "elective",
        "raw_id": "Nine hours of upper-division electives",
        "name": "Nine hours of upper-division electives",
        "course_codes": [],
        "credits_text": "",
        "or_predecessor_position": None,
    },
]


@pytest.fixture()
def _mock_shared_modules():
    """Inject mock shared.* and neo4j modules so lazy imports resolve without .env."""
    mock_session = MagicMock()
    mock_session.execute.return_value.all.return_value = [
        ("Computer Science - Bachelor of Arts (BA)", 1)
    ]

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
        patch("sqlalchemy.delete", MagicMock()),
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
        from data.ingest.ingest_requirements import write_postgres

        write_postgres(SAMPLE_PROGRAMS, SAMPLE_REQUIREMENTS)

        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.usefixtures("_mock_shared_modules")
    def test_executes_upserts_and_deletes(self, _mock_shared_modules) -> None:
        _mocks, mock_session = _mock_shared_modules
        from data.ingest.ingest_requirements import write_postgres

        write_postgres(SAMPLE_PROGRAMS, SAMPLE_REQUIREMENTS)

        # At least 4 execute calls: program upsert, name lookup, requirement delete,
        # requirement insert
        assert mock_session.execute.call_count >= 4

    @pytest.mark.usefixtures("_mock_shared_modules")
    def test_empty_input_still_commits(self, _mock_shared_modules) -> None:
        _mocks, mock_session = _mock_shared_modules
        from data.ingest.ingest_requirements import write_postgres

        write_postgres([], [])

        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()


class TestWriteNeo4j:
    @pytest.mark.usefixtures("_mock_shared_modules", "_mock_neo4j")
    def test_creates_and_closes_driver(self, _mock_shared_modules, _mock_neo4j) -> None:
        _mock_neo4j_mod, mock_driver, _mock_neo4j_session = _mock_neo4j
        from data.ingest.ingest_requirements import write_neo4j

        write_neo4j(SAMPLE_PROGRAMS, SAMPLE_REQUIREMENTS)

        _mock_neo4j_mod.GraphDatabase.driver.assert_called_once()
        mock_driver.close.assert_called_once()

    @pytest.mark.usefixtures("_mock_shared_modules", "_mock_neo4j")
    def test_executes_merges_with_or_alternatives(
        self, _mock_shared_modules, _mock_neo4j
    ) -> None:
        _mock_neo4j_mod, _mock_driver, mock_neo4j_session = _mock_neo4j
        from data.ingest.ingest_requirements import write_neo4j

        write_neo4j(SAMPLE_PROGRAMS, SAMPLE_REQUIREMENTS)

        # 4 execute_write calls: programs, requirements+HAS_REQUIREMENT,
        # SATISFIED_BY, OR_ALTERNATIVE
        assert mock_neo4j_session.execute_write.call_count == 4

    @pytest.mark.usefixtures("_mock_shared_modules", "_mock_neo4j")
    def test_empty_input_no_execute_write(
        self, _mock_shared_modules, _mock_neo4j
    ) -> None:
        _mock_neo4j_mod, _mock_driver, mock_neo4j_session = _mock_neo4j
        from data.ingest.ingest_requirements import write_neo4j

        write_neo4j([], [])

        mock_neo4j_session.execute_write.assert_not_called()
