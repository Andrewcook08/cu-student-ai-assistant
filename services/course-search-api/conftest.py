"""Service-level pytest conftest.

Adds this service's directory to sys.path so `from course_search_api.main import app`
and similar imports inside tests/conftest.py resolve correctly when pytest is
invoked from the repo root. The services aren't installed as packages by uv
(no `[build-system]` in their pyproject.toml — they're virtual workspace members
that just contribute deps), so the package directories need to be added to
sys.path explicitly.

Each service uses a uniquely-named top-level package (`chat_service` and
`course_search_api`) so both can coexist in `sys.modules` and `uv run pytest`
at the repo root collects every service's tests in a single invocation. See
docs/development-workflow.md § How CI Discovers Tests.

This file also sets test-specific env var defaults BEFORE any application code
is imported. pydantic-settings gives env vars higher priority than .env files,
so these setdefault calls are overridden by any real env var (e.g. DATABASE_URL
set in CI), but they beat the .env file that points at Docker-internal hostnames.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).parent
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))

# Default test database: Docker postgres remapped to host port 5433.
# In CI, override by setting DATABASE_URL in the workflow env block.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/cu_assistant",
)
# Remaining required settings — tests don't exercise neo4j / redis / ollama.
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "test")
os.environ.setdefault("OLLAMA_EMBED_MODEL", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
