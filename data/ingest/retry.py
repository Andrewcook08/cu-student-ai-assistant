from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> T:
    """Call fn(), retrying on any exception with exponential backoff.

    Delays: 1s, 2s, 4s, 8s … capped at max_delay.
    Raises the last exception if all attempts are exhausted.
    """
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt == attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            if on_retry:
                on_retry(attempt, exc)
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]
