# Local Development Guide

> Run the entire system on your machine before spending GCP credits. Databases run in Docker. On Apple Silicon Macs, run Ollama natively (via Ollama.app) for Metal GPU acceleration — Docker on Mac cannot access the GPU.

---

## Table of Contents
- [Prerequisites](#prerequisites)
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
- **RAM**: 16GB minimum, 32GB recommended (Neo4j and Ollama are memory-hungry)
- **Disk**: ~20GB free (Docker images + database data + Ollama model)
- **GPU**: Optional but recommended. On **Apple Silicon Macs**, run Ollama natively via [Ollama.app](https://ollama.com/download) for Metal GPU acceleration (~5-10s per response). Docker on Mac runs CPU-only (~60-90s per response) because Docker's Linux VM cannot access Metal. On **Linux with NVIDIA GPU**, Docker can use GPU passthrough (`--gpus all`).

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
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/cu_assistant
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=development
REDIS_URL=redis://redis:6379/0

# Ollama (running in Docker)
OLLAMA_BASE_URL=http://ollama:11434

# Auth
JWT_SECRET=local-development-secret-change-in-production

# Ollama model (pulled on first startup)
OLLAMA_MODEL=gpt-oss:20b
OLLAMA_EMBED_MODEL=nomic-embed-text

# CORS (frontend origin — must match Vite dev server or Cloud Run URL)
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

### 3. Start all services

```bash
docker compose up -d
```

This starts 7 containers:

| Container | Port | URL |
|-----------|------|-----|
| `postgres` | 5432 | `postgresql://postgres:postgres@localhost:5432/cu_assistant` |
| `neo4j` | 7474 (browser), 7687 (bolt) | http://localhost:7474 |
| `redis` | 6379 | `redis://localhost:6379` |
| `ollama` | 11434 | http://localhost:11434 |
| `course-search-api` | 8000 | http://localhost:8000/api/health |
| `chat-service` | 8001 | http://localhost:8001/api/chat/health |
| `frontend` | 5173 | http://localhost:5173 |

### 4. Pull the Ollama model (first time only, ~13GB download)

**Apple Silicon Mac (recommended):** Run Ollama natively for Metal GPU acceleration.

```bash
# Install Ollama.app from https://ollama.com/download (or brew install ollama)
# Launch Ollama.app (NOT `ollama serve` — the app enables Metal GPU)
ollama pull gpt-oss:20b
ollama pull nomic-embed-text
```

Then update your `.env` to point at native Ollama instead of Docker:
```
OLLAMA_BASE_URL=http://localhost:11434
```

And start Docker **without** the Ollama container:
```bash
docker compose up -d postgres neo4j redis
```

**Linux / other platforms:** Use the Docker container.

```bash
docker compose exec ollama ollama pull gpt-oss:20b
docker compose exec ollama ollama pull nomic-embed-text
```

Models are cached (in a Docker volume or `~/.ollama/`) and persist across restarts.

### 5. Run data ingestion

```bash
uv run --package data-ingest python -m data.ingest.run_all
```

This parses the JSON datasets and loads them into both PostgreSQL and Neo4j. See [Data Ingestion](#data-ingestion) for details.

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

# Check Ollama
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
- All Docker services must be running (`docker compose up -d`)
- JSON datasets must be in `data/raw/` (`cu_classes.json`, `cu_degree_requirements.json`)

### Run all ingestion steps
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
# Start only the data services
docker compose up -d postgres neo4j redis ollama

# Run course-search-api locally (hot reload)
uv run --package course-search-api uvicorn app.main:app --reload --port 8000

# Run chat-service locally (hot reload) in another terminal
uv run --package chat-service uvicorn app.main:app --reload --port 8001
```

When running locally (outside Docker), use `localhost` connection strings instead of Docker service names:

```env
# .env.local (for running outside Docker)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cu_assistant
NEO4J_URI=bolt://localhost:7687
REDIS_URL=redis://localhost:6379/0
OLLAMA_BASE_URL=http://localhost:11434
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
# Terminal 1: Data services (Docker)
docker compose up -d postgres neo4j redis ollama

# Terminal 2: Course Search API (hot reload)
uv run --package course-search-api uvicorn app.main:app --reload --port 8000

# Terminal 3: Chat Service (hot reload)
uv run --package chat-service uvicorn app.main:app --reload --port 8001

# Terminal 4: Frontend (hot reload)
cd frontend && npm run dev
```

This gives you hot reload on all application code while databases run in Docker.

---

## Service Details

### docker-compose.yml service map

```yaml
services:
  # ── Data Services ──────────────────────────────────────────
  postgres:
    image: postgres:16
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: cu_assistant
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5

  neo4j:
    image: neo4j:5
    ports: ["7474:7474", "7687:7687"]
    environment:
      NEO4J_AUTH: neo4j/development
      NEO4J_PLUGINS: '["apoc"]'
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "development", "RETURN 1"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s  # Neo4j is slow to start

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  ollama:
    image: ollama/ollama:latest
    ports: ["11434:11434"]
    volumes:
      - ollama_data:/root/.ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 10s
      timeout: 5s
      retries: 5
    # GPU support (uncomment if you have NVIDIA GPU):
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]

  # ── Application Services ───────────────────────────────────
  course-search-api:
    build:
      context: .
      dockerfile: services/course-search-api/Dockerfile
    ports: ["8000:8000"]
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy

  chat-service:
    build:
      context: .
      dockerfile: services/chat-service/Dockerfile
    ports: ["8001:8001"]
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      neo4j:
        condition: service_healthy
      redis:
        condition: service_healthy
      ollama:
        condition: service_healthy

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports: ["5173:80"]
    depends_on: [course-search-api, chat-service]

volumes:
  postgres_data:
  neo4j_data:
  redis_data:
  ollama_data:
```

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
| 11434 | Ollama | HTTP |

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
| Start all services | `docker compose up -d` |
| Stop all services | `docker compose down` |
| Fresh start (delete data) | `docker compose down -v` |
| View logs | `docker compose logs -f <service>` |
| Rebuild a service | `docker compose up -d --build <service>` |
| Run data ingestion | `uv run --package data-ingest python -m data.ingest.run_all` |
| Run tests | `uv run pytest` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
| Type check | `uv run mypy .` |
| Pull Ollama model | `docker compose exec ollama ollama pull gpt-oss:20b` |
| Open Neo4j browser | `open http://localhost:7474` |
| API docs (Search API) | `open http://localhost:8000/docs` |
| API docs (Chat Service) | `open http://localhost:8001/docs` |
| Postgres shell | `docker compose exec postgres psql -U postgres -d cu_assistant` |

---

## Troubleshooting

### Ollama is slow on CPU
If you're on an Apple Silicon Mac and seeing ~60-90s per response, you're running Ollama in Docker (CPU-only). Switch to native Ollama via **Ollama.app** for Metal GPU acceleration (~5-10s per response). See [Step 4](#4-pull-the-ollama-model-first-time-only-13gb-download) for setup.

**Important:** Use **Ollama.app** (the macOS app), not `ollama serve` from the CLI. The CLI server does not enable Metal GPU. Verify with `ollama ps` — it should show `100% GPU`, not `100% CPU`.

**Tip**: For faster local iteration on non-AI code (frontend, REST API, data ingestion), you don't need Ollama running. Only start it when testing the chat feature.

### Port already in use
```bash
# Find what's using the port (e.g., 5432)
lsof -i :5432

# Kill it or change the port in docker-compose.yml
```

### Neo4j won't start (memory)
Neo4j needs ~1GB of heap memory. If Docker is constrained:
- Docker Desktop → Settings → Resources → increase memory to at least 24GB

### Ollama model not found
```bash
# Check which models are downloaded
docker compose exec ollama ollama list

# Pull the model
docker compose exec ollama ollama pull gpt-oss:20b
```

### Database data is stale / want to start fresh
```bash
docker compose down -v   # removes all volumes (deletes all data)
docker compose up -d
# Re-run ingestion:
uv run --package data-ingest python -m data.ingest.run_all
```

### Hot reload not working for backend
Make sure you're running uvicorn outside Docker with `--reload`:
```bash
uv run --package course-search-api uvicorn app.main:app --reload --port 8000
```
If running inside Docker, you need to mount the source code as a volume (the Dockerfile copies code at build time, so changes require a rebuild).

---

## Local vs. GCP Differences

Understanding these differences ensures local testing is valid before deploying:

| Aspect | Local | GCP |
|--------|-------|-----|
| **App services** | Docker containers or `uvicorn --reload` | Cloud Run (auto-scaling, scale-to-zero) |
| **Databases** | Docker containers on your machine | Docker Compose on a Compute Engine VM |
| **Ollama** | Native (Metal GPU on Apple Silicon) or Docker (CPU-only on Mac, GPU on Linux) | L4 GPU on Compute Engine, auto-scaled via Managed Instance Group (fast) |
| **Networking** | `localhost` / Docker internal network | Private VPC subnet (no public IPs) + Serverless VPC Connector |
| **Secrets** | `.env` file | Terraform-managed Cloud Run env vars |
| **Data persistence** | Docker volumes (local disk) | Persistent disk on Compute Engine VM |
| **Docker images** | Built locally | Built in CI, pushed to Artifact Registry |

### What changes between local and GCP

Only **connection strings and environment variables** change. The application code is identical. This is by design — Docker Compose locally mirrors the GCP setup:

- Local: `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cu_assistant`
- GCP: `DATABASE_URL=postgresql://user:pass@10.0.0.x:5432/cu_assistant` (internal VPC IP)

No code changes are needed to deploy. The `config.py` in `shared/` reads from environment variables, which are set by `.env` locally and by Terraform on GCP.

### Pre-deployment checklist

Before deploying to GCP, verify locally:

- [ ] `docker compose up -d` — all 7 containers start without errors
- [ ] Data ingestion completes — courses visible in PostgreSQL and Neo4j
- [ ] `GET /api/courses?dept=CSCI` returns results from Course Search API
- [ ] `GET /api/health` and `GET /api/chat/health` both return 200
- [ ] Chat sends a message and gets an LLM response (slow on CPU is OK)
- [ ] Chat follow-up references prior context (memory works)
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy .` passes
