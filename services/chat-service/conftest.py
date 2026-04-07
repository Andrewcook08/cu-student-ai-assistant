"""Service-level pytest conftest.

Adds this service's directory to sys.path so `from chat_service.main import app`
and similar imports inside tests/conftest.py resolve correctly when pytest is
invoked from the repo root. The services aren't installed as packages by uv
(no `[build-system]` in their pyproject.toml — they're virtual workspace members
that just contribute deps), so the package directories need to be added to
sys.path explicitly.

Each service uses a uniquely-named top-level package (`chat_service` and
`course_search_api`) so both can coexist in `sys.modules` and `uv run pytest`
at the repo root collects every service's tests in a single invocation. See
docs/development-workflow.md § How CI Discovers Tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).parent
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))
