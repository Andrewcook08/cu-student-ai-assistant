# Local Development Guide

> Run the entire system on your machine before spending GCP credits. Databases run in Docker. Ollama runs in Docker for embeddings only (nomic-embed-text, ~274MB — fast even on CPU). LLM inference uses the Anthropic API and only requires an API key — no GPU or model download needed.

---

## Table of Contents
- [Prerequisites](#prerequisites)
- [Day-to-day: use `scripts/dev.sh`](#day-to-day-use-scriptsdevsh)
- [First-Time Setup](#first-time-setup)
- [Running the Stack](#running-the-stack)
- [Data Ingestion](#data-ingestion)
- [Development Workflow](#development-workflow)
- [Service Details](#service-details)
- [Testing](#testing)
- [Common Commands](#common-commands)
- [Troubleshooting](#troubleshooting)
- [Local vs. GCP Differences](#local-vs-gcp-differences)

---

## Prerequisites

Install these before starting:

| Tool | Version | Install | Purpose |
|------|---------|---------|---------|
| **Docker Desktop** | ≥ 4.x | [docker.com](https://docs.docker.com/get-docker/) | Runs all services in containers |
| **uv** | ≥ 0.5 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Python package management |
| **Node.js** | ≥ 20 LTS | [nodejs.org](https://nodejs.org/) or `brew install node` | Frontend development |
| **Git** | ≥ 2.x | Already installed on macOS/Linux | Version control |

**Hardware recommendations:**
- **RAM**: 8GB minimum (the embed model is tiny; Neo4j is the main consumer)
- **Disk**: ~10GB free (Docker images + database data; no large model download)

---

## Day-to-day: use `scripts/dev.sh`

`scripts/dev.sh` is the canonical dev environment manager and is how the team runs the stack day-to-day. It wraps `docker compose`, waits for container healthchecks (120s timeout), verifies that the Ollama embedding model (`nomic-embed-text`) is present, and drives the full data ingestion pipeline. Prefer it over raw `docker compose` commands.

| Command | Description |
|---------|-------------|
| `scripts/dev.sh up [--seed]` | Start containers and wait until healthy. With `--seed`, also runs data ingestion. |
| `scripts/dev.sh down` | Stop containers, preserve data volumes. |
| `scripts/dev.sh reset` | Wipe volumes, rebuild containers, and re-seed from scratch. |
| `scripts/dev.sh seed` | Run the 4-step data ingestion pipeline (containers must already be running). |
| `scripts/dev.sh status` | Show container status, health, and exposed ports. |

Typical first run after cloning:

```bash
scripts/dev.sh up --seed
```

Typical daily loop:

```bash
scripts/dev.sh up         # start
scripts/dev.sh status     # sanity check
scripts/dev.sh down       # stop when done
```

The raw `docker compose` commands below still work and are useful as an escape hatch for debugging — see [Running the Stack](#running-the-stack).

---

## First-Time Setup

### 1. Clone and install Python dependencies

```bash
git clone <repo-url> cu-student-ai-assistant
cd cu-student-ai-assistant
uv sync
```

This installs all workspace packages (shared, course-search-api, chat-service, data-ingest) and dev tools (ruff, pytest, mypy) in a single virtual environment.

### 2. Create your local environment file

```bash
cp .env.example .env
```

Edit `.env` with local values. For local Docker development, the defaults should work:

```env
# Database connections (Docker Compose internal networking)
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/cu_assistant
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=development
REDIS_URL=redis://redis:6379/0

# LLM (Anthropic API)
ANTHROPIC_API_KEY=        # Get from https://console.anthropic.com/
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# Embeddings (Ollama — runs in Docker, used only for vector search)
OLLAMA_URL=http://ollama:11434
OLLAMA_EMBED_MODEL=nomic-embed-text

# Auth
JWT_SECRET_KEY=local-development-secret-change-in-production

# CORS (frontend origin — must match Vite dev server or Cloud Run URL)
CORS_ORIGINS=http://localhost:5173
```

### 3. Start all services

Preferred (uses the dev script — waits for healthchecks, verifies models):

```bash
scripts/dev.sh up
```

Manual alternative:

```bash
docker compose up -d
```

Either starts 7 containers:

| Container | Port | URL |
|-----------|------|-----|
| `postgres` | 5432 | `postgresql+psycopg://postgres:postgres@localhost:5432/cu_assistant` |
| `neo4j` | 7474 (browser), 7687 (bolt) | http://localhost:7474 |
| `redis` | 6379 | `redis://localhost:6379` |
| `ollama` | 11434 | http://localhost:11434 (embeddings only) |
| `course-search-api` | 8000 | http://localhost:8000/api/health |
| `chat-service` | 8001 | http://localhost:8001/api/chat/health |
| `frontend` | 5173 | http://localhost:5173 |

### 4. Embeddings model + Anthropic API key

**Embeddings (Ollama):** The embedding model (`nomic-embed-text`) runs in the Ollama Docker container. It is pulled automatically when you run `scripts/dev.sh seed` — no manual provisioning step needed. The model is small (~274MB) and fast on CPU, so no Apple Silicon native Ollama setup is required.

**Anthropic API key (for LLM inference):** The chat service calls the Anthropic API instead of a local LLM. To get your key:

1. Create an account at [console.anthropic.com](https://console.anthropic.com/)
2. Go to **API Keys** and generate a new key
3. Add it to your `.env` (or `.env.local` when running outside Docker):

```env
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

No GPU, no model download, no Ollama.app — just the API key.

### 5. Run data ingestion

Preferred:

```bash
scripts/dev.sh seed
```

Manual alternative:

```bash
uv run --package data-ingest python -m data.ingest.run_all
```

Either parses the JSON datasets and loads them into both PostgreSQL and Neo4j. See [Data Ingestion](#data-ingestion) for details.

### 6. Verify everything works

```bash
# Check service health
curl http://localhost:8000/api/health
curl http://localhost:8001/api/chat/health

# Check databases
docker compose exec postgres psql -U postgres -d cu_assistant -c "SELECT count(*) FROM courses;"

# Check Neo4j (open browser)
open http://localhost:7474
# Login: neo4j / development
# Run: MATCH (c:Course) RETURN count(c)

# Check Ollama (embedding service)
curl http://localhost:11434/api/tags
```

---

## Running the Stack

### Start everything
```bash
docker compose up -d
```

### Stop everything (preserves data)
```bash
docker compose down
```

### Stop everything and delete all data (fresh start)
```bash
docker compose down -v
```

### View logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f chat-service
docker compose logs -f ollama
```

### Restart a single service (after code changes)
```bash
docker compose restart course-search-api
docker compose restart chat-service
```

### Rebuild after Dockerfile or dependency changes
```bash
docker compose up -d --build course-search-api chat-service frontend
```

---

## Data Ingestion

Ingestion loads the 2 JSON datasets into both PostgreSQL (for structured queries) and Neo4j (for graph + vector search).

### Prerequisites
- All Docker services must be running (`scripts/dev.sh up` or `docker compose up -d`)
- JSON datasets must be in `data/raw/` (`cu_classes.json`, `cu_degree_requirements.json`)

### Run all ingestion steps

```bash
scripts/dev.sh seed
```

Or run the underlying command directly:

```bash
uv run --package data-ingest python -m data.ingest.run_all
```

This runs in order:
1. **ingest_courses.py** — Parse `cu_classes.json` → PostgreSQL `courses`/`sections`/`course_attributes` tables + Neo4j `Course`/`Section`/`Department`/`Attribute` nodes (deduplicates topics courses by code, extracts pipe-delimited topic_titles, normalizes newline-delimited gen-ed attributes into college/category pairs)
2. **parse_prerequisites.py** — Parse natural language prerequisite strings → Neo4j `HAS_PREREQUISITE` edges (regex for common patterns, raw text preserved for LLM fallback)
3. **ingest_requirements.py** — Parse `cu_degree_requirements.json` → PostgreSQL `programs`/`requirements` tables + Neo4j `Program`/`Requirement` nodes with relationships (handles or-groups, choose-N, section headers)
4. **build_embeddings.py** — Generate embeddings via Ollama (`nomic-embed-text`) → store on Neo4j `Course` nodes + create vector index

### Run a single step
```bash
uv run --package data-ingest python -m data.ingest.ingest_courses
uv run --package data-ingest python -m data.ingest.build_embeddings
```

### Re-ingest (idempotent)
All ingestion scripts are idempotent — running them again will upsert (update existing, insert new) rather than duplicate data.

---

## Development Workflow

### Backend development (Python)

For faster iteration, you can run the backend services **outside Docker** while keeping the databases in Docker:

```bash
# Start only the data services (ollama is for embeddings)
docker compose up -d postgres neo4j redis ollama

# Run course-search-api locally (hot reload)
uv run --package course-search-api uvicorn course_search_api.main:app --reload --port 8000

# Run chat-service locally (hot reload) in another terminal
# Ensure ANTHROPIC_API_KEY is set in .env or .env.local
uv run --package chat-service uvicorn chat_service.main:app --reload --port 8001
```

When running locally (outside Docker), use `localhost` connection strings instead of Docker service names:

```env
# .env.local (for running outside Docker)
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/cu_assistant
NEO4J_URI=bolt://localhost:7687
REDIS_URL=redis://localhost:6379/0
OLLAMA_URL=http://localhost:11434  # embeddings only
ANTHROPIC_API_KEY=sk-ant-...       # LLM inference
```

### Frontend development (Vue)

For hot-reload during frontend development:

```bash
cd frontend
npm install          # first time only
npm run dev          # starts Vite dev server on http://localhost:5173
```

Vite is configured to proxy API calls:
- `/api/*` → `http://localhost:8000` (course-search-api)
- `/api/chat*` and `/ws/*` → `http://localhost:8001` (chat-service)

### Both together

Typical development session:
```bash
# Terminal 1: Data services (Docker — ollama is for embeddings)
docker compose up -d postgres neo4j redis ollama

# Terminal 2: Course Search API (hot reload)
uv run --package course-search-api uvicorn course_search_api.main:app --reload --port 8000

# Terminal 3: Chat Service (hot reload)
uv run --package chat-service uvicorn chat_service.main:app --reload --port 8001

# Terminal 4: Frontend (hot reload)
cd frontend && npm run dev
```

This gives you hot reload on all application code while databases run in Docker.

---

## Service Details

### docker-compose.yml service map

> **Source of truth**: [`docker-compose.yml`](../docker-compose.yml) at the repo root. The table below is a summary — update the real file, not this doc, when making changes.

| Service | Image | Host port → container | Depends on | Persisted volume |
|---|---|---|---|---|
| `postgres` | `postgres:16` | `5432:5432` | — | `postgres_data` |
| `neo4j` | `neo4j:5` (with APOC) | `7474:7474`, `7687:7687` | — | `neo4j_data` |
| `redis` | `redis:7-alpine` | `6379:6379` | — | `redis_data` |
| `ollama` | `ollama/ollama:latest` | `${OLLAMA_HOST_PORT:-11434}:11434` | — | `ollama_data` (embeddings only) |
| `course-search-api` | built from `services/course-search-api/Dockerfile` | `8000:8000` | `postgres` (healthy) | — |
| `chat-service` | built from `services/chat-service/Dockerfile` | `8001:8001` | `postgres`, `neo4j`, `redis`, `ollama` (all healthy) | — |
| `frontend` | built from `frontend/Dockerfile` (nginx) | `5173:80` | `course-search-api`, `chat-service` | — |

**Healthchecks**: all four data services (`postgres`, `neo4j`, `redis`, `ollama`) have healthchecks; application services use `depends_on: condition: service_healthy` so they only start once their dependencies are ready. Neo4j uses a 30s `start_period` because it's slow to boot.

**Credentials (local only)**: postgres `postgres/postgres`, neo4j `neo4j/development`, DB name `cu_assistant`. These are dev-only — production values come from Terraform secrets (Phase 4). When the production override (SEC-008) lands, these defaults will be rejected at boot by the SEC-006 validator, and the stack will refuse to start without real secrets in the environment.

**GPU**: not required. The Ollama container runs the embed model (nomic-embed-text) on CPU. LLM inference is handled by the Anthropic API.

### Port map

| Port | Service | Protocol |
|------|---------|----------|
| 5173 | Frontend (Vue) | HTTP |
| 8000 | Course Search API | HTTP |
| 8001 | Chat Service | HTTP + WebSocket |
| 5432 | PostgreSQL | TCP |
| 7474 | Neo4j Browser | HTTP |
| 7687 | Neo4j Bolt | TCP |
| 6379 | Redis | TCP |
| 11434 | Ollama (embeddings only) | HTTP |

### Production override (SEC-008)

The local dev compose file intentionally exposes every datastore on the host so developers can connect with `psql`, Neo4j Browser, `redis-cli`, etc. For production and prod-simulation, `docker-compose.prod.yml` layers on top of the base file to remove these host bindings. Services still reach each other by service name on the internal compose bridge network — only the host-side ports go away.

The override introduces three changes:

- **Cleared `ports:` mappings** on `postgres`, `neo4j`, `redis`, and `ollama` — no host binding, so datastores are unreachable from outside the compose network.
- **Required secret syntax** (`${NEO4J_PASSWORD:?required}`, `${POSTGRES_PASSWORD:?required}`, `${REDIS_PASSWORD:?required}`, `${JWT_SECRET_KEY:?required}`) — the stack refuses to start when any secret is unset.
- **`ENVIRONMENT=production`** on the app services — trips the SEC-006 fail-fast secret validator at boot.

**Running with the prod override:**

```bash
# Export secrets (or use a secrets manager / .env injection)
export POSTGRES_PASSWORD="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export NEO4J_PASSWORD="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export REDIS_PASSWORD="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"

# Validate the merged config
docker compose -f docker-compose.yml -f docker-compose.prod.yml config

# Start the stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Verify port isolation** (after `up`):

```bash
# Should fail — no host binding
nc -zv localhost 5432

# Should succeed — internal service-name reach
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec course-search-api pg_isready -h postgres
```

See [ADR-33 in decisions.md](decisions.md#adr-33-api--infrastructure-security-hardening) for the rationale.

---

## Testing

### Run all tests
```bash
uv run pytest
```

### Run tests for a specific service
```bash
uv run pytest services/course-search-api/tests/
uv run pytest services/chat-service/tests/
uv run pytest data/ingest/tests/
```

### Run a specific test file
```bash
uv run pytest services/chat-service/tests/test_security.py -v
uv run pytest data/ingest/tests/test_build_embeddings.py -v
```

### Integration tests

The default `uv run pytest` skips integration tests via the project-wide `-m 'not integration'` addopts in the root `pyproject.toml`. To run them, opt in with `-m integration` and make sure the relevant infra is up first.

```bash
# Start the infra the integration suite needs
docker compose up -d redis

# Run all integration tests
uv run pytest -m integration

# Run just one integration suite
uv run pytest -m integration services/chat-service/tests/test_redis_service_integration.py
```

New integration test files must declare `pytestmark = pytest.mark.integration` at the module level (or `@pytest.mark.integration` per test). The marker is registered in the root `pyproject.toml` `[tool.pytest.ini_options].markers` table — add new infra-dependent markers there if a new category is needed.

### Linting and formatting
```bash
# Check for issues
uv run ruff check .

# Auto-fix issues
uv run ruff check . --fix

# Check formatting
uv run ruff format --check .

# Auto-format
uv run ruff format .

# Type checking
uv run mypy .
```

### Run the same checks CI runs
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

---

## Common Commands

| Task | Command |
|------|---------|
| Start all services | `scripts/dev.sh up` (or `docker compose up -d`) |
| Stop all services | `scripts/dev.sh down` (or `docker compose down`) |
| Fresh start (delete data) | `scripts/dev.sh reset` (or `docker compose down -v`) |
| Show container status | `scripts/dev.sh status` |
| View logs | `docker compose logs -f <service>` |
| Rebuild a service | `docker compose up -d --build <service>` |
| Run data ingestion | `scripts/dev.sh seed` |
| Run tests | `uv run pytest` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type check | `uv run mypy .` |
| List Ollama models | `docker compose exec ollama ollama list` |
| Open Neo4j browser | `open http://localhost:7474` |
| API docs (Search API) | `open http://localhost:8000/docs` |
| API docs (Chat Service) | `open http://localhost:8001/docs` |
| Postgres shell | `docker compose exec postgres psql -U postgres -d cu_assistant` |

---

## Troubleshooting

### Port already in use
```bash
# Find what's using the port (e.g., 5432)
lsof -i :5432

# Kill it or change the port in docker-compose.yml
```

### Neo4j won't start (memory)
Neo4j needs ~1GB of heap memory. If Docker is constrained:
- Docker Desktop → Settings → Resources → increase memory to at least 24GB

### Embedding model not found (nomic-embed-text)

If `scripts/dev.sh seed` reports the embed model is missing, pull it manually:

```bash
docker compose exec ollama ollama pull nomic-embed-text
```

### Anthropic API errors

If the chat service returns errors about the LLM, check that `ANTHROPIC_API_KEY` is set:

```bash
# Verify the key is present in your environment
grep ANTHROPIC_API_KEY .env

# If running outside Docker, also check .env.local
```

Generate a key at [console.anthropic.com](https://console.anthropic.com/) if you don't have one.

### Database data is stale / want to start fresh
```bash
scripts/dev.sh reset   # wipes volumes, rebuilds containers, re-seeds
```

Or manually:
```bash
docker compose down -v   # removes all volumes (deletes all data)
docker compose up -d
uv run --package data-ingest python -m data.ingest.run_all
```

### Hot reload not working for backend
Make sure you're running uvicorn outside Docker with `--reload`:
```bash
uv run --package course-search-api uvicorn course_search_api.main:app --reload --port 8000
```
If running inside Docker, you need to mount the source code as a volume (the Dockerfile copies code at build time, so changes require a rebuild).

---

## Local vs. GCP Differences

Understanding these differences ensures local testing is valid before deploying:

| Aspect | Local | GCP |
|--------|-------|-----|
| **App services** | Docker containers or `uvicorn --reload` | Cloud Run (auto-scaling, scale-to-zero) |
| **Databases** | Docker containers on your machine | Docker Compose on a Compute Engine VM |
| **Ollama** | Docker (embeddings only, CPU) | Docker on data VM (embeddings only) |
| **Networking** | `localhost` / Docker internal network | Private VPC subnet (no public IPs) + Serverless VPC Connector |
| **Secrets** | `.env` file | Terraform-managed Cloud Run env vars |
| **Data persistence** | Docker volumes (local disk) | Persistent disk on Compute Engine VM |
| **Docker images** | Built locally | Built in CI, pushed to Artifact Registry |

### What changes between local and GCP

Only **connection strings and environment variables** change. The application code is identical. This is by design — Docker Compose locally mirrors the GCP setup:

- Local: `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/cu_assistant`
- GCP: `DATABASE_URL=postgresql+psycopg://user:pass@10.0.0.x:5432/cu_assistant` (internal VPC IP)

No code changes are needed to deploy. The `config.py` in `shared/` reads from environment variables, which are set by `.env` locally and by Terraform on GCP.

### Pre-deployment checklist

Before deploying to GCP, verify locally:

- [ ] `scripts/dev.sh up` — all 7 containers start and reach healthy state
- [ ] Data ingestion completes — courses visible in PostgreSQL and Neo4j
- [ ] `GET /api/courses?dept=CSCI` returns results from Course Search API
- [ ] `GET /api/health` and `GET /api/chat/health` both return 200
- [ ] Chat sends a message and gets an LLM response (slow on CPU is OK)
- [ ] Chat follow-up references prior context (memory works)
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy .` passes
