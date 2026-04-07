# CU Student AI Assistant — Project Context

**Architecture, tech stack, project structure**: See `docs/architecture.md`. ADRs in `docs/decisions.md`.

## Commands

### Python (uv workspaces)
```bash
uv sync                                    # Install all dependencies
uv run pytest                              # Run all tests
uv run pytest services/course-search-api/  # Run tests for one service
uv run pytest -x -v                        # Stop on first failure, verbose
uv run ruff check .                        # Lint
uv run ruff check . --fix                  # Lint + auto-fix
uv run ruff format .                       # Format
uv run ruff format --check .               # Check formatting
uv run mypy .                              # Type check
```

### Run the full check suite (same as CI)
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

### Docker
Prefer `scripts/dev.sh up --seed` for day-to-day startup (see Data ingestion). Raw `docker compose` below is the escape hatch.
```bash
docker compose up -d                       # Start all 7 services
docker compose up -d postgres neo4j redis ollama  # Data services only
docker compose down                        # Stop (keep data)
docker compose down -v                     # Stop + delete all data
docker compose logs -f chat-service        # Tail logs for one service
docker compose up -d --build course-search-api  # Rebuild one service
```

### Run services locally (hot reload, outside Docker)
```bash
# Backend (use .env.local with localhost connection strings)
uv run --package course-search-api uvicorn course_search_api.main:app --reload --port 8000
uv run --package chat-service uvicorn chat_service.main:app --reload --port 8001

# Frontend
cd frontend && npm run dev
```

### Data ingestion
Ollama models (`gpt-oss:20b`, `nomic-embed-text`) are pre-provisioned on the dev host's disk — no runtime pulls needed. `scripts/dev.sh` is the canonical orchestrator: starts containers, waits for health, seeds data.
```bash
scripts/dev.sh up --seed                   # Start containers + wait for health + seed (primary entry point)
scripts/dev.sh down                        # Stop containers (keep data)
scripts/dev.sh reset                       # Stop + wipe volumes + restart clean
scripts/dev.sh seed                        # Re-run seeding against already-running containers
scripts/dev.sh status                      # Show container + health status

# Manual fallback (if containers are already up and you just want to re-ingest):
uv run --package data-ingest python -m data.ingest.run_all
```

### Verify databases
```bash
docker compose exec postgres psql -U postgres -d cu_assistant -c "SELECT count(*) FROM courses;"
# Open Neo4j browser: http://localhost:7474 (neo4j / development)
```

## Code Conventions

### Python
- Python 3.12, strict mypy, ruff for lint + format
- Line length: 100 characters
- All functions that hit the database or external services must be async
- Use Pydantic models for all API request/response shapes
- Use SQLAlchemy ORM models in `shared/models.py` — this is the single source of truth for the schema
- Use `Depends()` for FastAPI dependency injection (db sessions, auth)
- Parameterized queries only — never string-format SQL or Cypher

### Auth
- JWT auth via `shared/auth.py` — both services validate the same tokens
- Course Search API issues tokens (login/register endpoints)
- Chat Service validates tokens (WebSocket query param)
- **CRITICAL**: Tool executor ALWAYS overrides `user_id` with the JWT value. Never trust the LLM.

### Neo4j
- Use `MERGE` for idempotent writes
- Parameterized Cypher queries only (no f-strings)
- Async driver (`neo4j.AsyncGraphDatabase`)

### Frontend
- Vue 3 Composition API with `<script setup lang="ts">`
- Pinia for state management
- Composables in `src/composables/` — currently `useCourses.ts`. Planned: `useChat.ts` (Epic 4), `useAuth.ts` (Epic 7).
- API clients in `src/services/` — currently `courseApi.ts`. Planned: `chatApi.ts` (Epic 4), `studentApi.ts` (Epic 7).
- Pinia stores in `src/stores/` — `authStore.ts` (token plumbing only; login flow lands with AUTH-003/004), `courseStore.ts`. Planned: `chatStore.ts` (Epic 4).
- Types in `src/types/index.ts`
- **Course Search page is anchored to `frontend/cu-classes.html`** — a frozen 1170-line static HTML reference (ADR-31). Never modify it. All Course Search components port markup from specific line ranges in this file. See architecture.md § Frontend for the source-region → component mapping.
- CU brand tokens (extracted from `cu-classes.html`'s `<style>` block): `cu-gold` `#CFB87C`, `cu-gold-hover` `#c4a94f`, `cu-black` `#000000`, `cu-text` `#333`, `cu-muted` `#555`, `cu-section-head` `#eee`, `cu-panel` `#f5f5f5`, `cu-pane` `#fafafa`, `cu-border` `#ddd`, `cu-link` `#0277BD`

### Testing
- pytest + pytest-asyncio for backend
- Test files next to source: `services/*/tests/`, `data/ingest/tests/`
- Fixtures in `conftest.py` per service
- Test what matters: tools, auth, prerequisite parser, API endpoints, security
- Don't test: ORM models, Pydantic schemas, config loading, frontend components

### Git
- Branch from `main`, PR back to `main`
- Branch naming: `feat/CUAI-XX-short-description` (e.g., `feat/CUAI-39-course-listing`)
- The `CUAI-XX` Jira key in the branch name drives automated status transitions (see `docs/development-workflow.md#jira-automation`)
- Commit messages: imperative mood, reference Jira key (e.g., `CUAI-39: Add course listing endpoint`)
- Squash merge PRs to keep `main` history clean
- CI must pass before merge (ruff, mypy, pytest)
- Never commit `.env`, `terraform.tfvars`, or `data/raw/*.json`

**Environment variables**: See `.env.example` and `shared/config.py`.
