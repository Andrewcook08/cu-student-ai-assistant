from __future__ import annotations

from unittest.mock import patch

import pytest

from data.ingest.retry import with_retry


@patch("data.ingest.retry.time.sleep")
def test_succeeds_on_first_attempt(mock_sleep) -> None:
    assert with_retry(lambda: 42) == 42
    mock_sleep.assert_not_called()


@patch("data.ingest.retry.time.sleep")
def test_retries_then_succeeds(mock_sleep) -> None:
    calls = iter([ValueError("boom"), ValueError("boom"), 99])

    def flaky():
        v = next(calls)
        if isinstance(v, Exception):
            raise v
        return v

    assert with_retry(flaky) == 99
    assert mock_sleep.call_count == 2


@patch("data.ingest.retry.time.sleep")
def test_raises_after_all_attempts_exhausted(mock_sleep) -> None:
    with pytest.raises(ValueError, match="always"):
        with_retry(lambda: (_ for _ in ()).throw(ValueError("always")), attempts=3)
    assert mock_sleep.call_count == 2


@patch("data.ingest.retry.time.sleep")
def test_backoff_delays_are_exponential(mock_sleep) -> None:
    attempt_count = {"n": 0}

    def fail_four_times():
        attempt_count["n"] += 1
        if attempt_count["n"] < 5:
            raise ValueError("not yet")
        return "ok"

    assert with_retry(fail_four_times, base_delay=1.0, max_delay=30.0) == "ok"
    delays = [c.args[0] for c in mock_sleep.call_args_list]
    assert delays == [1.0, 2.0, 4.0, 8.0]


@patch("data.ingest.retry.time.sleep")
def test_backoff_capped_at_max_delay(mock_sleep) -> None:
    attempt_count = {"n": 0}

    def fail_four_times():
        attempt_count["n"] += 1
        if attempt_count["n"] < 5:
            raise ValueError("not yet")
        return "ok"

    assert with_retry(fail_four_times, base_delay=8.0, max_delay=20.0) == "ok"
    delays = [c.args[0] for c in mock_sleep.call_args_list]
    assert delays == [8.0, 16.0, 20.0, 20.0]


@patch("data.ingest.retry.time.sleep")
def test_on_retry_callback_invoked(mock_sleep) -> None:
    retries: list[tuple[int, str]] = []
    calls = iter([ValueError("x"), 1])

    def flaky():
        v = next(calls)
        if isinstance(v, Exception):
            raise v
        return v

    with_retry(flaky, on_retry=lambda a, e: retries.append((a, str(e))))
    assert retries == [(1, "x")]


@patch("data.ingest.retry.time.sleep")
def test_on_retry_not_called_on_final_attempt(mock_sleep) -> None:
    retries: list[int] = []
    with pytest.raises(ValueError):
        with_retry(
            lambda: (_ for _ in ()).throw(ValueError("fail")),
            attempts=3,
            on_retry=lambda a, e: retries.append(a),
        )
    assert retries == [1, 2]
