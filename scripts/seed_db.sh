#!/usr/bin/env bash
set -euo pipefail
exec uv run --package data-ingest python -m data.ingest.run_all "$@"
