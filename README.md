# CU Student AI Assistant

An AI-powered course scheduling and degree-planning assistant for CU Boulder students. Built for the Big Data Architecture class — a production-grade system that helps students explore courses, plan their degree path, and build personalized semester schedules through natural-language chat.

## What it does

CU Boulder has no personalized tool for degree planning — just static catalog pages and overloaded advisors. This assistant fills the gap:

1. **Understands** what a student has taken and what they need
2. **Reasons** over degree requirements, prerequisites, and scheduling constraints
3. **Recommends** courses and semester schedules grounded in the real catalog
4. **Remembers** decisions across sessions

The chat is grounded in a real ingest of the CU course catalog — 3,410 courses, 9,470 sections, 203 degree programs, and the full prerequisite graph.

## Architecture

Two backend services behind a Vue frontend, all on GCP Cloud Run, with the data tier on a single Compute Engine VM.

```
Frontend (Vue 3 + Vite)
   │
   ├── REST ──► Course Search API (FastAPI)  ──► PostgreSQL
   │
   └── WebSocket ──► Chat Service (FastAPI + LangGraph)
                          │
                          ├──► Anthropic API (Claude Sonnet)
                          ├──► PostgreSQL  (courses, users, decisions)
                          ├──► Neo4j       (prereq graph + vector index)
                          ├──► Redis       (sessions, rate limits)
                          └──► Ollama      (nomic-embed-text, 768-dim)
```

| Service | Role |
|---|---|
| **frontend** | Vue 3 + TypeScript + Tailwind. Course search page + chat widget. |
| **course-search-api** | Stateless REST over Postgres. Auth (JWT), course/program lookups, student decision history. |
| **chat-service** | LangGraph `StateGraph` orchestrating intent classification → Graph RAG context → Claude tool-calling → output validation. WebSocket streaming. |
| **data-ingest** | Cloud Run Job that loads the CU catalog into Postgres + Neo4j and generates embeddings. |
| **ollama-embed** | Prebaked Cloud Run service serving `nomic-embed-text` for query-time embeddings. |

Full design docs are in [`docs/architecture.md`](docs/architecture.md). Architectural decisions are recorded in [`docs/decisions.md`](docs/decisions.md).

## Tech stack

- **Backend**: Python 3.12, FastAPI, LangChain + LangGraph, Anthropic SDK
- **Frontend**: Vue 3, TypeScript, Vite, Tailwind, shadcn-vue
- **Data**: PostgreSQL 16, Neo4j (with native vector indexes), Redis
- **LLM**: Claude Sonnet via the Anthropic API
- **Embeddings**: Ollama (`nomic-embed-text`, 768-dim, cosine)
- **Infra**: GCP (Cloud Run + Compute Engine + Artifact Registry + Secret Manager), Terraform, GitHub Actions
- **Tooling**: uv workspaces, ruff, mypy (strict), pytest

## Repo layout

```
.
├── frontend/                Vue app
├── services/
│   ├── course-search-api/   FastAPI REST service
│   └── chat-service/        FastAPI + LangGraph chat service
├── shared/                  Shared Python config, models, auth, db helpers
├── data/                    Course catalog + ingest pipeline
├── infra/                   Terraform + ./infra.sh wrapper for GCP
├── scripts/                 Local dev helpers (dev.sh, check.sh, seed_db.sh)
├── docs/                    Architecture, ADRs, runbooks, workflow
└── docker-compose.yml       Local dev stack (Postgres, Neo4j, Redis, Ollama)
```

## Local development

```bash
# 1. Install Python deps (single workspace lockfile)
uv sync

# 2. Bring up data services + Ollama
docker compose up -d

# 3. Seed the databases
./scripts/seed_db.sh

# 4. Start backend + frontend
./scripts/dev.sh
```

Then open `http://localhost:5173`. Detailed setup notes, env vars, and troubleshooting live in [`docs/local-development.md`](docs/local-development.md).

### Quality gates

```bash
./scripts/check.sh          # ruff + mypy + pytest across the whole workspace
```

CI runs the same checks on every PR.

## Deployment

The full stack is **fully ephemeral** — `./infra.sh up` provisions everything from scratch in ~20 minutes, `./infra.sh down` reaches $0 in residual cost.

```bash
cd infra/
./infra.sh up               # Terraform apply + secret population + VM bootstrap
gh workflow run deploy.yml  # Build images, push to AR, update Cloud Run revisions
./infra.sh ingest           # Load the course catalog (~5 min)
./infra.sh down             # Tear it all down
```

See [`infra/README.md`](infra/README.md) for the runbook, the responsibility split between Terraform / shell / operator / deploy pipeline, and ingest-pipeline modes.

## Documentation

| File | What it covers |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | System design, service boundaries, scaling, data model, security |
| [`docs/decisions.md`](docs/decisions.md) | ADRs (51 and counting) — every non-obvious technical decision and why |
| [`docs/local-development.md`](docs/local-development.md) | Local dev setup, env vars, common issues |
| [`docs/development-workflow.md`](docs/development-workflow.md) | Branch / PR / review conventions |
| [`docs/implementation-guide.md`](docs/implementation-guide.md) | How features are wired end-to-end |
| [`docs/example-conversation.md`](docs/example-conversation.md) | Annotated transcript of a real chat session |
| [`infra/README.md`](infra/README.md) | Infra runbook — spin-up, teardown, ingest, drift |

## Team

Three-person team for CSCI Big Data Architecture (CU Boulder, Spring 2026):

- **Andrew** — data ingest, AI/chat service, infra
- **Rohan** — frontend + course-search API
- **Scott** — shared infrastructure, deploy pipeline, cross-cutting concerns

## Status

This is a class project — built to demonstrate production-grade architecture, not run as a live service. The Cloud Run stack is ephemeral and torn down between demos to keep cost at zero.
