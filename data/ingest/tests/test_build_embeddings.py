from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from data.ingest.build_embeddings import (
    build_all_embeddings,
    build_embedding_text,
    get_embedding,
)

# ── build_embedding_text ─────────────────────────────────────────────


def test_embedding_text_all_fields() -> None:
    record = {
        "code": "CSCI 1300",
        "title": "Computer Science 1",
        "topic_titles": "",
        "description": "Intro to programming",
        "attributes": ["Engineering: Humanities"],
    }
    result = build_embedding_text(record)
    assert result == "CSCI 1300 Computer Science 1  Intro to programming Engineering: Humanities"


def test_embedding_text_with_topics() -> None:
    record = {
        "code": "CSCI 7000",
        "title": "Current Topics in CS",
        "topic_titles": "ML|NLP|Robotics",
        "description": "Special topics course",
        "attributes": [],
    }
    result = build_embedding_text(record)
    assert "ML|NLP|Robotics" in result


def test_embedding_text_missing_optional_fields() -> None:
    record = {
        "code": "GRAD 9999",
        "title": "Thesis Research",
        "topic_titles": None,
        "description": None,
        "attributes": None,
    }
    result = build_embedding_text(record)
    assert result == "GRAD 9999 Thesis Research"


def test_embedding_text_multiple_attributes() -> None:
    record = {
        "code": "PHYS 1110",
        "title": "General Physics 1",
        "topic_titles": "",
        "description": "Mechanics and waves",
        "attributes": [
            "Arts & Sciences: Natural Science",
            "GT Pathways: Natural & Physical Sciences",
        ],
    }
    result = build_embedding_text(record)
    assert "Arts & Sciences: Natural Science" in result
    assert "GT Pathways: Natural & Physical Sciences" in result


# ── get_embedding ────────────────────────────────────────────────────


def test_get_embedding_returns_vector() -> None:
    fake_vector = [0.1] * 768
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [fake_vector]}
    mock_resp.raise_for_status = MagicMock()

    client = MagicMock(spec=httpx.Client)
    client.post.return_value = mock_resp

    result = get_embedding("test text", client)
    assert result == fake_vector
    assert len(result) == 768


def test_get_embedding_raises_on_http_error() -> None:
    client = MagicMock(spec=httpx.Client)
    client.post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )

    with pytest.raises(httpx.HTTPStatusError):
        get_embedding("test text", client)


# ── build_all_embeddings (integration-level with mocks) ─────────────


@patch("data.ingest.build_embeddings.GraphDatabase")
@patch("data.ingest.build_embeddings.httpx.Client")
def test_build_all_skips_when_no_courses(mock_client_cls, mock_gdb, capsys) -> None:
    mock_session = MagicMock()
    mock_session.run.return_value.data.return_value = []
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
    mock_gdb.driver.return_value = mock_driver

    build_all_embeddings()

    output = capsys.readouterr().out
    assert "nothing to do" in output


@patch("data.ingest.build_embeddings.GraphDatabase")
@patch("data.ingest.build_embeddings.httpx.Client")
def test_build_all_processes_courses(mock_client_cls, mock_gdb) -> None:
    fake_vector = [0.5] * 768

    # Set up Neo4j mock — first session for index, second for query, third+ for writes.
    mock_session = MagicMock()
    mock_session.run.return_value.data.return_value = [
        {
            "code": "CSCI 1300",
            "title": "CS 1",
            "topic_titles": "",
            "description": "Intro",
            "attributes": [],
        },
    ]
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
    mock_gdb.driver.return_value = mock_driver

    # Set up Ollama mock.
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"embeddings": [fake_vector]}
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    build_all_embeddings()

    # Verify embedding was written back.
    write_calls = [
        c for c in mock_session.run.call_args_list
        if c.args and "SET c.embedding" in str(c.args[0])
    ]
    assert len(write_calls) == 1


@patch("data.ingest.build_embeddings.time.sleep")
@patch("data.ingest.build_embeddings.GraphDatabase")
@patch("data.ingest.build_embeddings.httpx.Client")
def test_build_all_retries_on_failure(mock_client_cls, mock_gdb, mock_sleep) -> None:
    fake_vector = [0.5] * 768

    mock_session = MagicMock()
    mock_session.run.return_value.data.return_value = [
        {
            "code": "CSCI 2270",
            "title": "Data Structures",
            "topic_titles": "",
            "description": "DSA",
            "attributes": [],
        },
    ]
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
    mock_gdb.driver.return_value = mock_driver

    # Fail twice, succeed on third attempt.
    mock_client = MagicMock()
    fail_resp = MagicMock()
    fail_resp.raise_for_status.side_effect = httpx.ConnectError("connection refused")
    ok_resp = MagicMock()
    ok_resp.json.return_value = {"embeddings": [fake_vector]}
    mock_client.post.side_effect = [fail_resp, fail_resp, ok_resp]
    mock_client_cls.return_value = mock_client

    build_all_embeddings()

    # Should have retried (slept twice).
    assert mock_sleep.call_count == 2

    # Embedding should still be written.
    write_calls = [
        c for c in mock_session.run.call_args_list
        if c.args and "SET c.embedding" in str(c.args[0])
    ]
    assert len(write_calls) == 1
