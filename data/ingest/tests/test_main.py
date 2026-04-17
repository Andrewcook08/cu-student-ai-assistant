from __future__ import annotations

import subprocess
import sys


def test_full_mode_refuses_without_confirm_flag() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "data.ingest", "run", "--mode=full"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "--i-understand-this-wipes-prod" in result.stderr


def test_mode_is_required() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "data.ingest", "run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--mode" in result.stderr


def test_invalid_mode_rejected() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "data.ingest", "run", "--mode=destroy"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "invalid choice" in result.stderr
