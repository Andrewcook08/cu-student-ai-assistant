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
uv run --package course-search-api uvicorn app.main:app --reload --port 8000
uv run --package chat-service uvicorn app.main:app --reload --port 8001

# Frontend
cd frontend && npm run dev
```

### Data ingestion
```bash
docker compose exec ollama ollama pull gpt-oss:20b         # Pull LLM model
docker compose exec ollama ollama pull nomic-embed-text    # Pull embedding model
uv run --package data-ingest python -m data.ingest.run_all # Run all ingestion
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
- Composables in `src/composables/` (useChat, useCourses, useAuth)
- API clients in `src/services/` (courseApi, chatApi, studentApi)
- Types in `src/types/index.ts`
- CU branding: gold (#CFB87C), black (#000000)

### Testing
- pytest + pytest-asyncio for backend
- Test files next to source: `services/*/tests/`
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
