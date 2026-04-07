#!/usr/bin/env bash
# Run full lint + type check suite.
# Usage: bash scripts/check.sh
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> ruff check"
uv run ruff check .

echo "==> mypy: shared"
uv run mypy .

echo "==> mypy: course-search-api"
MYPYPATH="$REPO_ROOT/shared" uv run mypy \
  --config-file services/course-search-api/pyproject.toml \
  services/course-search-api/course_search_api services/course-search-api/tests

echo "==> mypy: chat-service"
MYPYPATH="$REPO_ROOT/shared" uv run mypy \
  --config-file services/chat-service/pyproject.toml \
  services/chat-service/chat_service services/chat-service/tests

echo "All checks passed."
