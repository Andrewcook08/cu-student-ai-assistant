# CU Student AI Assistant

AI-powered academic advising assistant for CU Boulder students. Helps plan degree paths, check prerequisites, search courses, and build semester schedules.

## Architecture

- **Two backend services** + Ollama GPU workers + Vue frontend
- **Course Search API** (`services/course-search-api/`) — stateless FastAPI REST over PostgreSQL
- **Chat Service** (`services/chat-service/`) — stateful FastAPI with LangGraph, tool calling, WebSocket
- **Shared package** (`shared/`) — JWT auth, SQLAlchemy models, Pydantic schemas, config
- **Data ingestion** (`data/`) — JSON → PostgreSQL + Neo4j + embeddings
- **Frontend** (`frontend/`) — Vue 3 + TypeScript + Vite + Tailwind + Pinia
- **Infrastructure** (`infra/`) — Terraform for GCP (Cloud Run, Compute Engine, MIG)

Read `docs/architecture.md` for the full design. Read `docs/decisions.md` for ADRs.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy, LangChain, LangGraph |
| Frontend | Vue 3, TypeScript, Vite, Tailwind CSS, Pinia |
| Databases | PostgreSQL 16, Neo4j 5 (graph + vectors), Redis 7 |
| LLM | Ollama (model set via OLLAMA_MODEL env var) |
| Embeddings | nomic-embed-text (768 dims) via Ollama |
| IaC | Terraform (GCP: Cloud Run, Compute Engine, MIG) |

## Project Structure

```
cu-student-ai-assistant/
├── pyproject.toml              # Root uv workspace config
├── uv.lock                     # Single lockfile (auto-generated)
├── docker-compose.yml          # Local dev: all 7 services
├── .env.example                # Template for env vars
├── shared/                     # Shared Python package
│   └── shared/                 # config, models, auth, schemas, database
├── services/
│   ├── course-search-api/      # REST API service
│   └── chat-service/           # Chat + AI service
├── data/                       # Ingestion scripts + raw JSON
├── frontend/                   # Vue SPA
├── infra/                      # Terraform
└── docs/                       # Architecture, decisions, guides
```

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
docker compose exec ollama ollama pull llama3.1:8b        # Pull LLM model
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
- Branch naming: `feat/STORY-ID-short-description` (e.g., `feat/API-001-course-listing`)
- Commit messages: imperative mood, reference story ID
- CI must pass before merge (ruff, mypy, pytest)
- Never commit `.env`, `terraform.tfvars`, or `data/raw/*.json`

## Environment Variables

All config is via environment variables, read by `shared/config.py`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/cu_assistant` | PostgreSQL connection |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection |
| `NEO4J_USER` | `neo4j` | Neo4j auth |
| `NEO4J_PASSWORD` | `development` | Neo4j auth |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API |
| `OLLAMA_MODEL` | `llama3.1:8b` | LLM model name |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `JWT_SECRET` | `change-me-in-production` | JWT signing secret |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Allowed CORS origins |

## Key Documentation

- `docs/architecture.md` — Full system design, schemas, API spec, security model
- `docs/decisions.md` — 23 Architecture Decision Records (ADRs)
- `docs/implementation-guide.md` — Step-by-step build instructions with code
- `docs/jira-epics-and-stories.md` — 60 stories across 12 epics with dependencies
- `docs/local-development.md` — Docker Compose setup, dev workflow, troubleshooting
- `docs/development-workflow.md` — Branching, PR, testing, Claude Code setup
