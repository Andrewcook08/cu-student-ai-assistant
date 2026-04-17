from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import contextmanager
from typing import Any


class _JsonFormatter(logging.Formatter):
    def __init__(self, run_id: str) -> None:
        super().__init__()
        self._run_id = run_id

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "run_id": self._run_id,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for field in ("step", "course_code", "duration_ms"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def make_logger(run_id: str) -> logging.Logger:
    logger = logging.getLogger(f"ingest.{run_id}")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter(run_id))
        logger.addHandler(handler)
    logger.propagate = False
    return logger


@contextmanager
def timed_step(logger: logging.Logger, step: str):
    """Context manager that logs step start/end with duration_ms."""
    logger.info("started", extra={"step": step})
    t0 = time.monotonic()
    try:
        yield
    finally:
        ms = int((time.monotonic() - t0) * 1000)
        logger.info("completed", extra={"step": step, "duration_ms": ms})
