# CU Student AI Assistant

An AI-powered course scheduling and degree-planning tool for CU Boulder students. Class project for CSCI Big Data Architecture, CU Boulder.

## Overview

The application provides two ways to interact with the CU course catalog:

1. A course search interface with filters for department, level, credit hours, and keyword.
2. A chat interface backed by a large language model that answers questions about courses, degree requirements, prerequisites, and schedule planning.

Chat responses are grounded in a structured copy of the CU course catalog: 3,410 courses, 9,470 sections, 203 degree programs, and the full prerequisite graph. The model returns only courses that exist in the loaded catalog.

## Architecture

```
Frontend (Vue 3 + Vite)
   │
   ├── REST ──► Course Search API (FastAPI)  ──► PostgreSQL
   │
   └── WebSocket ──► Chat Service (FastAPI + LangGraph)
                          │
                          ├──► Anthropic API (Claude Sonnet)
                          ├──► PostgreSQL  (courses, users, decisions)
                          ├──► Neo4j       (prerequisite graph + vector index)
                          ├──► Redis       (sessions, rate limits)
                          └──► Ollama      (nomic-embed-text, 768-dim)
```

### Services

| Service | Responsibility |
|---|---|
| `frontend` | Vue 3 + TypeScript + Tailwind. Course search page and chat widget. |
| `course-search-api` | Stateless REST API over PostgreSQL. Handles authentication (JWT), course/program lookups, and student decision history. |
| `chat-service` | LangGraph `StateGraph` with intent classification, Graph RAG context building, Claude tool-calling, and output validation. Exposes a WebSocket for streaming responses. |
| `data-ingest` | Cloud Run Job that loads the CU catalog into PostgreSQL and Neo4j and generates embeddings. |
| `ollama-embed` | Cloud Run service serving the `nomic-embed-text` embedding model for query-time semantic search. |

### Tech stack

- **Backend**: Python 3.12, FastAPI, LangChain, LangGraph, Anthropic SDK
- **Frontend**: Vue 3, TypeScript, Vite, Tailwind CSS, shadcn-vue
- **Data**: PostgreSQL 16, Neo4j (with native vector indexes), Redis
- **LLM**: Claude Sonnet via the Anthropic API
- **Embeddings**: Ollama (`nomic-embed-text`, 768-dim, cosine similarity)
- **Infrastructure**: GCP (Cloud Run, Compute Engine, Artifact Registry, Secret Manager), Terraform, GitHub Actions
- **Tooling**: uv workspaces, ruff, mypy (strict), pytest

## Repository structure

```
.
├── frontend/                Vue application
├── services/
│   ├── course-search-api/   FastAPI REST service
│   └── chat-service/        FastAPI + LangGraph chat service
├── shared/                  Shared Python config, models, auth, db helpers
├── data/                    Course catalog and ingest pipeline
├── infra/                   Terraform configuration and ./infra.sh wrapper
├── scripts/                 Local development scripts
├── docs/                    Architecture, ADRs, runbooks, workflow
└── docker-compose.yml       Local development stack
```

## Local development

```bash
uv sync                      # Install Python dependencies
docker compose up -d         # Bring up PostgreSQL, Neo4j, Redis, Ollama
./scripts/seed_db.sh         # Seed the databases
./scripts/dev.sh             # Start backend services and frontend
```

The application is then available at `http://localhost:5173`. See [`docs/local-development.md`](docs/local-development.md) for environment variables and troubleshooting.

### Quality checks

```bash
./scripts/check.sh           # ruff + mypy + pytest across the workspace
```

CI runs the same checks on every pull request.

## Deployment

Infrastructure is managed by Terraform with a shell wrapper for common operations:

```bash
cd infra/
./infra.sh up                # Provision GCP resources
gh workflow run deploy.yml   # Build images, push to Artifact Registry, update Cloud Run
./infra.sh ingest            # Load the course catalog
./infra.sh down              # Tear down all resources
```

Full runbook: [`infra/README.md`](infra/README.md).

## Documentation

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | System design, service boundaries, scaling, data model, security |
| [`docs/decisions.md`](docs/decisions.md) | Architectural decision records |
| [`docs/local-development.md`](docs/local-development.md) | Local environment setup |
| [`docs/development-workflow.md`](docs/development-workflow.md) | Branch, PR, and review conventions |
| [`docs/implementation-guide.md`](docs/implementation-guide.md) | End-to-end implementation reference |
| [`docs/example-conversation.md`](docs/example-conversation.md) | Sample chat transcript |
| [`infra/README.md`](infra/README.md) | Infrastructure runbook |

## Team

- Andrew Cook — data ingestion, AI/chat service, infrastructure
- Rohan — frontend, course search API
- Scott — shared infrastructure, deploy pipeline, cross-cutting concerns
