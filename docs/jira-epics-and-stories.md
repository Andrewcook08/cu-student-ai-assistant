# Jira Epics and Stories

> Import these into Jira to track implementation progress. Epics map to major system areas. Stories are sized in story points (1=trivial, 2=small, 3=medium, 5=large, 8=complex). Dependencies are explicit — don't start a story until its blockers are done.
>
> **Naming convention**: `[SERVICE]-NNN` where SERVICE is INFRA, API, CHAT, FE, DATA, DEPLOY.
>
> **Labels**: `phase-1`, `phase-2`, `phase-3`, `phase-4`, `critical-path`, `blocked`, `security`

---

## Table of Contents
- [Epic 1: Infrastructure & Repo Setup](#epic-1-infrastructure--repo-setup)
- [Epic 2: Data Ingestion Pipeline](#epic-2-data-ingestion-pipeline)
- [Epic 3: Course Search API](#epic-3-course-search-api)
- [Epic 4: Chat Engine (AI + LangGraph)](#epic-4-chat-engine-ai--langgraph)
- [Epic 5: Frontend — Course Search](#epic-5-frontend--course-search)
- [Epic 6: Frontend — Chat Widget](#epic-6-frontend--chat-widget)
- [Epic 7: Authentication](#epic-7-authentication)
- [Epic 8: Conversation Memory](#epic-8-conversation-memory)
- [Epic 9: Security Hardening](#epic-9-security-hardening)
- [Epic 10: GCP Deployment](#epic-10-gcp-deployment)
- [Epic 11: CI/CD](#epic-11-cicd)
- [Epic 12: Demo Prep](#epic-12-demo-prep)
- [Story Dependency Graph](#story-dependency-graph)
- [Sprint Plan](#sprint-plan)

---

## Epic 1: Infrastructure & Repo Setup

> Owner: Person A | Phase: 1 | Priority: Highest (unblocks everything)

### INFRA-001: Initialize uv workspace and root pyproject.toml
- **Points**: 2
- **Phase**: 1 (Day 1)
- **Blocked by**: Nothing
- **Assignee**: Person A
- **Description**: Create root `pyproject.toml` with workspace members (shared, course-search-api, chat-service, data-ingest). Configure dev dependencies (ruff, pytest, mypy, httpx). Create `.python-version`, `.gitignore`.
- **Acceptance criteria**:
  - [ ] `uv sync` succeeds from repo root
  - [ ] `uv run ruff check .` passes
  - [ ] `.gitignore` covers Python, Node, Docker, Terraform, IDE, OS files

### INFRA-002: Create shared Python package
- **Points**: 5
- **Phase**: 1 (Day 1)
- **Blocked by**: INFRA-001
- **Assignee**: Person A
- **Labels**: `critical-path`
- **Description**: Create `shared/` package with `config.py` (pydantic-settings), `database.py` (SQLAlchemy engine + session), `models.py` (all ORM models), `auth.py` (JWT create/decode, password hash/verify), `schemas.py` (shared Pydantic models: CourseCard, Action, ChatRequest, ChatResponse, ErrorResponse).
- **Acceptance criteria**:
  - [ ] `shared/shared/config.py` reads all env vars from `.env`
  - [ ] `shared/shared/models.py` has all 8 tables: courses, sections, programs, requirements, users, completed_courses, student_decisions, tool_audit_log
  - [ ] `shared/shared/auth.py` can create and decode JWTs, hash and verify passwords
  - [ ] `shared/shared/schemas.py` has CourseCard, Action, ChatRequest, ChatResponse, ErrorResponse
  - [ ] `from shared.config import settings` works from any workspace member

### INFRA-003: Create Docker Compose with healthchecks
- **Points**: 3
- **Phase**: 1 (Day 1)
- **Blocked by**: INFRA-001
- **Assignee**: Person A
- **Labels**: `critical-path`
- **Description**: Create `docker-compose.yml` with 7 services (postgres, neo4j, redis, ollama, course-search-api, chat-service, frontend). All data services have healthchecks. App services use `depends_on: condition: service_healthy`. Create `.env.example` with all required env vars.
- **Acceptance criteria**:
  - [ ] `cp .env.example .env && docker compose up -d` starts all containers
  - [ ] `docker compose ps` shows all data services as "healthy"
  - [ ] PostgreSQL accepts connections on port 5432
  - [ ] Neo4j browser accessible at http://localhost:7474
  - [ ] Redis responds to PING on port 6379
  - [ ] Ollama API accessible at http://localhost:11434

### INFRA-004: Scaffold Course Search API service
- **Points**: 2
- **Phase**: 1 (Day 1-2)
- **Blocked by**: INFRA-002
- **Assignee**: Person A
- **Description**: Create `services/course-search-api/` with `pyproject.toml`, Dockerfile, `app/main.py` (FastAPI app with CORS, lifespan, health endpoint), `dependencies.py`, empty route files, empty test files.
- **Acceptance criteria**:
  - [ ] `uv run --package course-search-api uvicorn app.main:app --port 8000` starts
  - [ ] `GET /api/health` returns `{"status": "ok"}`
  - [ ] Docker image builds and runs

### INFRA-005: Scaffold Chat Service
- **Points**: 2
- **Phase**: 1 (Day 1-2)
- **Blocked by**: INFRA-002
- **Assignee**: Person A
- **Description**: Create `services/chat-service/` with `pyproject.toml` (includes langchain, langgraph, neo4j, redis, httpx), Dockerfile, `app/main.py` (FastAPI with CORS, lifespan, health endpoint), empty core/ and services/ directories, empty test files.
- **Acceptance criteria**:
  - [ ] `uv run --package chat-service uvicorn app.main:app --port 8001` starts
  - [ ] `GET /api/chat/health` returns `{"status": "ok"}`
  - [ ] Docker image builds and runs

### INFRA-006: Scaffold data-ingest package
- **Points**: 1
- **Phase**: 1 (Day 1)
- **Blocked by**: INFRA-001
- **Assignee**: Person A
- **Description**: Create `data/` workspace member with `pyproject.toml`, `ingest/__init__.py`, `raw/.gitkeep`. Ensure JSON data files are gitignored but `.gitkeep` is tracked.
- **Acceptance criteria**:
  - [ ] `data/` is a recognized uv workspace member
  - [ ] `data/raw/` exists with `.gitkeep`
  - [ ] JSON files in `data/raw/` are gitignored

### INFRA-007: Full-stack Docker verification
- **Points**: 1
- **Phase**: 1 (Day 2)
- **Blocked by**: INFRA-003, INFRA-004, INFRA-005
- **Assignee**: Person A
- **Labels**: `critical-path`
- **Description**: Verify `docker compose up -d --build` starts all 7 containers. Both APIs return health checks. Frontend serves content. Push to main branch.
- **Acceptance criteria**:
  - [ ] All 7 containers running with `docker compose ps`
  - [ ] `curl http://localhost:8000/api/health` → 200
  - [ ] `curl http://localhost:8001/api/chat/health` → 200
  - [ ] `curl http://localhost:5173` → HTML content
  - [ ] Pushed to `main` — all team members can clone and run

---

## Epic 2: Data Ingestion Pipeline

> Owner: Person C | Phase: 1 | Priority: Highest (unblocks API + Chat)

### DATA-001: Parse cu_classes.json into course + section records
- **Points**: 5
- **Phase**: 1 (Day 1-3)
- **Blocked by**: INFRA-002 (for SQLAlchemy models)
- **Assignee**: Person C
- **Labels**: `critical-path`
- **Description**: Write `data/ingest/ingest_courses.py`. Parse the nested JSON structure (department → course → sections). Extract dept code from course code. Strip "This section is closed" prefix from CRN. Handle credits as text. Write to PostgreSQL (courses + sections tables) and Neo4j (Course + Section + Department nodes). Must be idempotent (upsert).
- **Acceptance criteria**:
  - [ ] PostgreSQL `courses` table has 3,735 rows
  - [ ] PostgreSQL `sections` table has ~13,223 rows
  - [ ] Neo4j has 3,735 Course nodes, 152 Department nodes
  - [ ] Re-running does not create duplicates
  - [ ] CRN values are clean numeric strings

### DATA-002: Parse cu_degree_requirements.json into program + requirement records
- **Points**: 5
- **Phase**: 1 (Day 2-4)
- **Blocked by**: INFRA-002
- **Assignee**: Person C
- **Labels**: `critical-path`
- **Description**: Write `data/ingest/ingest_requirements.py`. Parse the flat list per program. Detect: `or`-prefix entries, choose-N groups, `&`-bundles, `/`-cross-listed, section headers, free-text requirements, total credit hours. Classify each entry's `requirement_type`. Write to PostgreSQL (programs + requirements tables) and Neo4j (Program + Requirement nodes with HAS_REQUIREMENT, SATISFIED_BY, OR_ALTERNATIVE relationships).
- **Acceptance criteria**:
  - [ ] PostgreSQL `programs` table has 203 rows
  - [ ] PostgreSQL `requirements` table has correct count per program
  - [ ] Neo4j has 203 Program nodes with HAS_REQUIREMENT edges
  - [ ] OR alternatives are linked with OR_ALTERNATIVE relationships
  - [ ] Choose-N groups are correctly identified
  - [ ] Re-running does not create duplicates

### DATA-003: Prerequisite regex parser
- **Points**: 5
- **Phase**: 1 (Day 2-4)
- **Blocked by**: DATA-001 (needs courses in DB)
- **Assignee**: Person C
- **Description**: Write `data/ingest/parse_prerequisites.py`. Regex patterns for: single prereq, OR alternatives, AND requirements, corequisites, restrictions. For each match, create HAS_PREREQUISITE edges in Neo4j with type, min_grade, and raw_text. For non-matching strings, preserve raw_text only (LLM fallback).
- **Acceptance criteria**:
  - [ ] Handles all 5 common patterns (single, OR, AND, corequisite, restriction)
  - [ ] Neo4j has > 2,000 HAS_PREREQUISITE edges
  - [ ] Every edge has `raw_text` preserved
  - [ ] Matched edges have `min_grade` populated
  - [ ] Known typos in data ("prerequsite") don't crash the parser
  - [ ] ~80% parse rate (2,200+ of 2,830 courses with prerequisites)

### DATA-004: Build course embeddings via Ollama
- **Points**: 3
- **Phase**: 1 (Day 4-5)
- **Blocked by**: DATA-001, INFRA-003 (Ollama container running)
- **Assignee**: Person C
- **Description**: Write `data/ingest/build_embeddings.py`. For each course, generate an embedding from `"{code} {title} {description}"` via Ollama's nomic-embed-text model. Store on Neo4j Course nodes. Create vector index (`course-embeddings`, 768 dims, cosine).
- **Acceptance criteria**:
  - [ ] All 3,735 Course nodes have non-null `embedding` property
  - [ ] Vector index `course-embeddings` exists in Neo4j
  - [ ] `CALL db.index.vector.queryNodes('course-embeddings', 5, $embedding)` returns results
  - [ ] Vector index uses 768 dimensions with cosine similarity
  - [ ] Script is idempotent (skips courses that already have embeddings)

### DATA-005: run_all.py orchestrator + validation
- **Points**: 2
- **Phase**: 1 (Day 5)
- **Blocked by**: DATA-001, DATA-002, DATA-003, DATA-004
- **Assignee**: Person C
- **Description**: Write `data/ingest/run_all.py` that runs all 4 ingestion steps in order with progress logging. Also write `scripts/seed_db.sh` shell wrapper. Run full ingestion and validate all expected counts.
- **Acceptance criteria**:
  - [ ] `uv run --package data-ingest python -m data.ingest.run_all` completes without errors
  - [ ] All validation queries from the implementation guide pass
  - [ ] Total runtime < 15 minutes (embeddings are the bottleneck)

### DATA-006: Validate LLM tool calling with chosen model
- **Points**: 3
- **Phase**: 1 (Day 4-5)
- **Blocked by**: INFRA-003 (Ollama running)
- **Assignee**: Person B
- **Labels**: `critical-path`
- **Description**: Write `scripts/test_tool_calling.py`. Define 6 tool schemas matching the architecture. Write 20+ representative student questions with expected tool names. Test the chosen Ollama model. Report pass rate. If < 80%, test alternative models and document recommendation.
- **Acceptance criteria**:
  - [ ] Test script runs against Ollama and produces pass/fail per question
  - [ ] Overall pass rate ≥ 80%
  - [ ] If fail: recommendation for alternative model documented
  - [ ] Model choice decision recorded (resolves open question #2)

---

## Epic 3: Course Search API

> Owner: Person A | Phase: 2 | Priority: High

### API-001: GET /api/courses — filtered course listing
- **Points**: 3
- **Phase**: 2 (Day 6-7)
- **Blocked by**: DATA-001 (courses in PostgreSQL)
- **Assignee**: Person A
- **Description**: Implement course listing with filters: dept, instruction_mode, status, credits, text search (q). Offset/limit pagination (default 50). Returns `{items, total, offset, limit}`.
- **Acceptance criteria**:
  - [ ] `GET /api/courses?dept=CSCI` returns only CSCI courses
  - [ ] `GET /api/courses?q=machine+learning` returns relevant courses
  - [ ] `GET /api/courses?limit=10&offset=20` paginates correctly
  - [ ] Multiple filters can be combined
  - [ ] Response includes `total` count for pagination UI
  - [ ] Response time < 100ms

### API-002: GET /api/courses/{code} — course detail with sections
- **Points**: 2
- **Phase**: 2 (Day 7)
- **Blocked by**: DATA-001
- **Assignee**: Person A
- **Description**: Return a single course with all its sections, prerequisite text, and attributes. Include section meeting times, instructor, status.
- **Acceptance criteria**:
  - [ ] `GET /api/courses/CSCI 1300` returns course + all sections
  - [ ] Sections include crn, meets, instructor, status
  - [ ] 404 for non-existent course codes
  - [ ] Prerequisites_raw is included

### API-003: GET /api/courses/search — semantic search via Neo4j vectors
- **Points**: 3
- **Phase**: 2 (Day 7-8)
- **Blocked by**: DATA-004 (embeddings + vector index)
- **Assignee**: Person A
- **Description**: Accept a text query, generate embedding via Ollama, search Neo4j vector index, return ranked results with similarity scores.
- **Acceptance criteria**:
  - [ ] `GET /api/courses/search?q=data+science` returns relevant courses
  - [ ] Results include similarity score
  - [ ] Results are sorted by relevance (highest score first)
  - [ ] Response time < 500ms (embedding generation is the bottleneck)

### API-004: GET /api/programs and GET /api/programs/{id}/requirements
- **Points**: 2
- **Phase**: 2 (Day 8)
- **Blocked by**: DATA-002
- **Assignee**: Person A
- **Description**: List all programs (for dropdowns). Get requirements for a specific program, structured by requirement_type.
- **Acceptance criteria**:
  - [ ] `GET /api/programs` returns 203 programs with id, name, type
  - [ ] `GET /api/programs/1/requirements` returns structured requirements
  - [ ] Requirements are ordered by sort_order
  - [ ] OR alternatives are grouped with their parent requirement

### API-005: Student profile endpoints
- **Points**: 3
- **Phase**: 2-3 (Day 8-9)
- **Blocked by**: INFRA-002 (User model)
- **Assignee**: Person A
- **Description**: `GET /api/students/me` (returns profile, completed courses with grades, decisions). `PUT /api/students/me/completed-courses` (update completed course list with optional grades). All endpoints require JWT auth. Use test JWTs from `shared/auth.py` for development and testing; real login/register flow comes in Phase 3 (AUTH-001/002).
- **Acceptance criteria**:
  - [ ] Endpoints require valid JWT (401 without)
  - [ ] `GET /api/students/me` returns program, completed courses (with grades), decisions
  - [ ] `PUT /api/students/me/completed-courses` accepts `[{course_code, grade}]`
  - [ ] User can only see/modify their own data

### API-006: Course Search API tests
- **Points**: 3
- **Phase**: 2 (Day 9)
- **Blocked by**: API-001, API-002, API-004
- **Assignee**: Person A
- **Description**: Write pytest tests for all endpoints. Use a test database (SQLite or separate PostgreSQL). Test: filtering, pagination, 404s, auth required, auth forbidden.
- **Acceptance criteria**:
  - [ ] `uv run pytest services/course-search-api/tests/ -v` passes
  - [ ] Tests cover: happy path, edge cases, auth enforcement
  - [ ] Test fixtures seed minimal course data

---

## Epic 4: Chat Engine (AI + LangGraph)

> Owner: Person C | Phase: 2 | Priority: High

### CHAT-000: LangGraph spike (timeboxed research)
- **Points**: 2
- **Phase**: 1 (Day 5-6)
- **Blocked by**: INFRA-005
- **Assignee**: Person C
- **Description**: Timeboxed spike to de-risk the 8-point CHAT-008. Research LangGraph StateGraph, ReAct pattern, and tool binding. Build a minimal working prototype: single tool (e.g., echo tool), no real data, hardcoded Ollama connection. Document patterns and gotchas for the team.
- **Acceptance criteria**:
  - [ ] Minimal LangGraph StateGraph with one tool runs end-to-end
  - [ ] Tool binding and tool-calling loop demonstrated
  - [ ] Key patterns documented (state management, tool loop, error handling)
  - [ ] Timeboxed to 1 day — findings shared regardless of completion

### CHAT-001: Stub WebSocket endpoint (echo)
- **Points**: 2
- **Phase**: 2 (Day 6-7)
- **Blocked by**: INFRA-005
- **Assignee**: Person C
- **Labels**: `critical-path`
- **Description**: Create `routes/chat.py` with WebSocket endpoint at `/ws/chat/{session_id}`. Validate JWT from query param. Accept messages, send typing indicator, echo back. This unblocks Person B's frontend work.
- **Acceptance criteria**:
  - [ ] WebSocket connects with valid JWT
  - [ ] WebSocket rejects invalid JWT (close code 4001)
  - [ ] Server sends `{"type": "typing"}` then `{"type": "chat_response", "reply": "Echo: ..."}`
  - [ ] Person B can connect from Vue frontend

### CHAT-002: Neo4j service layer (graph queries)
- **Points**: 5
- **Phase**: 2 (Day 7-9)
- **Blocked by**: DATA-001, DATA-002, DATA-003 (data in Neo4j)
- **Assignee**: Person C
- **Description**: Create `services/neo4j_service.py` with async Neo4j driver. Implement: `vector_search()`, `get_prerequisite_chain()`, `get_degree_requirements()`. Use parameterized Cypher queries.
- **Acceptance criteria**:
  - [ ] `vector_search(embedding)` returns top-10 courses with scores
  - [ ] `get_prerequisite_chain("CSCI 3104")` returns the full chain
  - [ ] `get_degree_requirements("Computer Science")` returns structured requirements
  - [ ] All queries use parameterized inputs (no Cypher injection)

### CHAT-003: Ollama service + embedding generation
- **Points**: 2
- **Phase**: 2 (Day 7-8)
- **Blocked by**: INFRA-003 (Ollama running)
- **Assignee**: Person A
- **Description**: Create `services/ollama_service.py`. Async HTTP client (`httpx.AsyncClient`) to Ollama API. Functions: `get_embedding(text)`, `chat_completion(messages, tools)`. 120s timeout with graceful error handling.
- **Acceptance criteria**:
  - [ ] `get_embedding("data science")` returns 768-dim vector
  - [ ] `chat_completion(messages, tools)` returns model response with tool calls
  - [ ] Timeout at 120s returns user-friendly error message
  - [ ] Connection errors are handled gracefully

### CHAT-004: Redis service (sessions + inference queue)
- **Points**: 3
- **Phase**: 2 (Day 8-9)
- **Blocked by**: INFRA-003 (Redis running)
- **Assignee**: Person C
- **Description**: Create `services/redis_service.py`. Async Redis client. Implement: session storage, conversation message caching (RPUSH/LRANGE), inference queue (LPUSH/BRPOP), result pub/sub channel. 120s timeout on queue wait with 30s progress update.
- **Acceptance criteria**:
  - [ ] Messages stored and retrieved by session_id
  - [ ] Session TTL of 2 hours
  - [ ] Inference request enqueued and result received via pub/sub
  - [ ] 30s progress update sent if still waiting
  - [ ] 120s timeout returns graceful error

### CHAT-005: Tool definitions (@tool functions)
- **Points**: 3
- **Phase**: 2 (Day 9-10)
- **Blocked by**: CHAT-002, CHAT-003
- **Assignee**: Person C
- **Description**: Create `core/tools.py`. Define 6 tools with `@tool` decorator: search_courses, check_prerequisites, get_degree_requirements, get_student_profile, find_schedule_conflicts, save_decision. Each tool has a clear docstring for the LLM and calls the appropriate service layer.
- **Acceptance criteria**:
  - [ ] All 6 tools defined with typed parameters and descriptive docstrings
  - [ ] Each tool calls the correct service (Neo4j, PostgreSQL, Ollama)
  - [ ] Tools return structured dicts (not raw database rows)
  - [ ] Tools are importable and can be bound to the LLM

### CHAT-006: Tool executor with auth enforcement
- **Points**: 3
- **Phase**: 2 (Day 10)
- **Blocked by**: CHAT-005
- **Assignee**: Person C
- **Labels**: `security`
- **Description**: Create `core/tool_executor.py`. Wraps all tool calls: always overrides `user_id` with JWT value, validates parameters via Pydantic, rate limits at 10 calls per turn, retries once on malformed JSON, logs to `tool_audit_log`.
- **Acceptance criteria**:
  - [ ] `user_id` in params is ALWAYS replaced with JWT-authenticated value
  - [ ] Invalid parameters raise ValidationError (caught and retried once)
  - [ ] 11th tool call in one turn returns rate limit error
  - [ ] Every tool call is logged to `tool_audit_log` table
  - [ ] Retry re-prompts LLM with the error message

### CHAT-007: Intent classifier
- **Points**: 3
- **Phase**: 2 (Day 10-11)
- **Blocked by**: CHAT-003
- **Assignee**: Person C
- **Description**: Create `core/intent_classifier.py`. Classifies user messages into intents: `course_search`, `prereq_check`, `degree_planning`, `schedule_help`, `general_question`. Uses LLM classification or keyword heuristics. Routes to different retrieval strategies and system prompt variations.
- **Acceptance criteria**:
  - [ ] "What CS electives are there?" → `course_search`
  - [ ] "What are prerequisites for CSCI 3104?" → `prereq_check`
  - [ ] "What do I need for my CS degree?" → `degree_planning`
  - [ ] "Can you check my schedule for conflicts?" → `schedule_help`
  - [ ] "What is your favorite color?" → `general_question`
  - [ ] Classification is fast (< 500ms) — use heuristics or single LLM call

### CHAT-008: LangGraph conversation engine
- **Points**: 8
- **Phase**: 2 (Day 10-12)
- **Blocked by**: CHAT-005, CHAT-006, CHAT-007, CHAT-010
- **Assignee**: Person C
- **Labels**: `critical-path`
- **Description**: Create `core/llm_engine.py`. LangGraph StateGraph with nodes: classify_intent → build_context → call_llm → maybe_call_tools (loop) → validate_output → respond. Bind tools to the LLM. Handle the tool-calling loop (LLM generates tool calls → executor runs them → results fed back → LLM generates final response). Wire into the WebSocket endpoint (replace echo stub).
- **Acceptance criteria**:
  - [ ] User sends "What CS courses are available?" → LLM calls search_courses → returns course list
  - [ ] User sends "What are prereqs for CSCI 3104?" → LLM calls check_prerequisites → returns chain
  - [ ] Multi-tool flow works: LLM calls get_student_profile then get_degree_requirements
  - [ ] Tool call retry on malformed JSON works
  - [ ] Response includes structured_data (CourseCards) when appropriate
  - [ ] End-to-end: WebSocket message → LangGraph → tool calls → LLM response → WebSocket response

### CHAT-009: PostgreSQL service (student data + audit)
- **Points**: 3
- **Phase**: 2 (Day 8)
- **Blocked by**: INFRA-002
- **Assignee**: Person A
- **Description**: Create `services/postgres_service.py`. Functions: `get_student_data(user_id)` — returns profile + completed courses with grades + prior decisions. `save_student_decision(user_id, course_code, decision_type, notes)`. `get_schedule_conflicts(course_codes)` — join sections, parse meeting times, find overlaps.
- **Acceptance criteria**:
  - [ ] `get_student_data` returns program, completed courses (with grades), decisions
  - [ ] `save_student_decision` inserts to student_decisions table
  - [ ] `get_schedule_conflicts` detects overlapping meeting times
  - [ ] All functions use parameterized queries

### CHAT-010: Context builder
- **Points**: 3
- **Phase**: 2 (Day 9-10)
- **Blocked by**: CHAT-002, CHAT-009
- **Assignee**: Person C
- **Description**: Create `core/context_builder.py`. Assembles context for the LLM prompt from: student profile, conversation summary, retrieved graph/vector data, intent classification. Formats using delimiter tags (`<retrieved_context>`, `<user_profile>`, `<conversation_summary>`).
- **Acceptance criteria**:
  - [ ] Context includes student profile when available
  - [ ] Context includes conversation summary when available
  - [ ] Retrieved data is wrapped in `<retrieved_context>` tags
  - [ ] Context fits within model's context window (track token count)

### CHAT-011: Chat Service test suite
- **Points**: 5
- **Phase**: 2-3 (Day 12-13)
- **Blocked by**: CHAT-008
- **Assignee**: Person B
- **Description**: Write pytest tests for the chat service. Test: tool executor auth enforcement (user_id override), tool calling with mock LLM responses, Neo4j service queries, Redis session storage, WebSocket connect/disconnect, intent classification accuracy. Mock Ollama responses so tests run without GPU.
- **Acceptance criteria**:
  - [ ] `uv run pytest services/chat-service/tests/ -v` passes
  - [ ] Tests cover: tool executor user_id override, rate limiting, session persistence, intent classification
  - [ ] Test fixtures mock Ollama responses (no GPU needed in CI)
  - [ ] WebSocket connect with valid JWT and reject with invalid JWT tested
  - [ ] At least 80% coverage on `core/` modules

---

## Epic 5: Frontend — Course Search

> Owner: Person B (UI), Person A (API integration) | Phase: 1-2

### FE-001: Vue + Vite + Tailwind project setup
- **Points**: 2
- **Phase**: 1 (Day 1)
- **Blocked by**: Nothing
- **Assignee**: Person B
- **Description**: Initialize Vue 3 project with TypeScript, Router, Pinia, Tailwind, shadcn-vue. Configure Vite proxy for `/api` and `/ws`. Configure CU branding (gold, black, Proxima Nova font).
- **Acceptance criteria**:
  - [ ] `cd frontend && npm run dev` starts on http://localhost:5173
  - [ ] Tailwind works with `cu-gold` and `cu-black` colors
  - [ ] Vite proxy routes `/api/*` to port 8000 and `/ws/*` to port 8001
  - [ ] TypeScript compiles without errors

### FE-002: Layout shell (header, sidebar, footer)
- **Points**: 3
- **Phase**: 1 (Day 2-3)
- **Blocked by**: FE-001
- **Assignee**: Person B
- **Description**: Build AppHeader (CU branding, login button), AppSidebar/FilterBar (department, level, time, credits filters), AppFooter. Responsive layout.
- **Acceptance criteria**:
  - [ ] Header displays CU logo/branding with gold/black colors
  - [ ] Filter sidebar has working dropdown controls (department, level, etc.)
  - [ ] Layout is responsive (works on desktop and tablet)
  - [ ] Login button visible (non-functional until auth is wired)

### FE-003: Course table + detail panel (mock data)
- **Points**: 3
- **Phase**: 1 (Day 3-4)
- **Blocked by**: FE-002
- **Assignee**: Person B
- **Description**: CourseTable, CourseRow, CourseDetail components. Renders mock course data. Clicking a row expands detail panel with sections, prerequisites, description.
- **Acceptance criteria**:
  - [ ] Table renders 15+ mock courses with code, title, credits, status
  - [ ] Clicking a row expands detail panel below
  - [ ] Detail shows sections (CRN, time, instructor, status)
  - [ ] Filter controls filter the mock data locally

### FE-004: Wire course search to real API
- **Points**: 3
- **Phase**: 2 (Day 9-10)
- **Blocked by**: API-001, API-002, FE-003
- **Assignee**: Person A
- **Description**: Replace mock data with real API calls. Create `courseApi.ts`, `useCourses.ts` composable, `courseStore.ts` Pinia store. Wire filter controls to API query params. Implement pagination.
- **Acceptance criteria**:
  - [ ] Course table loads real data from API on page load
  - [ ] Changing department filter re-fetches from API
  - [ ] Pagination works (next/prev, showing total count)
  - [ ] Loading state shown while fetching
  - [ ] API errors shown as toast notification

### FE-005: TypeScript types
- **Points**: 1
- **Phase**: 1-2 (ongoing)
- **Blocked by**: FE-001
- **Assignee**: Person B
- **Description**: Create `src/types/index.ts` with interfaces: Course, Section, Program, StudentProfile, ChatResponse, CourseCard, Action, WsClientMessage, WsServerMessage, PaginatedResponse.
- **Acceptance criteria**:
  - [ ] All API response shapes have TypeScript interfaces
  - [ ] All WebSocket message types are defined
  - [ ] No `any` types in production code

---

## Epic 6: Frontend — Chat Widget

> Owner: Person B | Phase: 1-2

### FE-006: Chat window shell (expand/collapse)
- **Points**: 2
- **Phase**: 1 (Day 4)
- **Blocked by**: FE-001
- **Assignee**: Person B
- **Description**: ChatWindow component. Floating panel in bottom-right corner. Click to expand/collapse. Scrollable message area. Styled with CU branding.
- **Acceptance criteria**:
  - [ ] Chat icon visible in bottom-right corner
  - [ ] Clicking expands a chat panel
  - [ ] Panel has scrollable message area and input bar
  - [ ] Clicking icon again collapses the panel
  - [ ] Panel doesn't block course table interaction when collapsed

### FE-007: Chat message rendering (markdown + course cards)
- **Points**: 3
- **Phase**: 1 (Day 4-5)
- **Blocked by**: FE-006
- **Assignee**: Person B
- **Description**: ChatMessage component (user vs. AI styling). Markdown rendering via markdown-it. StructuredResponse component renders CourseCard lists. SuggestedActions component renders buttons/dropdowns from Action objects.
- **Acceptance criteria**:
  - [ ] User messages right-aligned, AI messages left-aligned
  - [ ] Markdown bold, italic, lists, code blocks render correctly
  - [ ] CourseCards render as styled cards (code, title, credits, status)
  - [ ] SuggestedActions render as clickable buttons/dropdowns
  - [ ] Selecting an action sends structured context back

### FE-008: WebSocket integration (useChat composable)
- **Points**: 5
- **Phase**: 2 (Day 8-12)
- **Blocked by**: CHAT-001 (stub WebSocket), FE-007
- **Assignee**: Person B
- **Description**: Create `useChat.ts` composable. WebSocket connection with JWT auth. Handle message types: typing, chat_response, error, progress. Auto-reconnect with exponential backoff (1s, 2s, 4s, max 30s). Show "Reconnecting..." during retry. Create `chatStore.ts` for state management.
- **Acceptance criteria**:
  - [ ] WebSocket connects with JWT token
  - [ ] Typing indicator shown while AI is processing
  - [ ] Chat response rendered with markdown + structured data
  - [ ] Error messages shown inline in chat
  - [ ] Auto-reconnect works on disconnect (verify by stopping chat-service, restarting)
  - [ ] "Reconnecting..." message shown during retry
  - [ ] 30s progress message rendered when received

### FE-009: Chat input + send
- **Points**: 2
- **Phase**: 1-2 (Day 5, then wire in Day 9)
- **Blocked by**: FE-006
- **Assignee**: Person B
- **Description**: ChatInput component. Text input + send button. Enter key sends. Input disabled while AI is responding. Character count indicator (max 2000).
- **Acceptance criteria**:
  - [ ] Enter key sends message
  - [ ] Send button sends message
  - [ ] Input disabled + shows "AI is thinking..." while typing indicator is active
  - [ ] Input prevents > 2000 characters
  - [ ] Input clears after sending

---

## Epic 7: Authentication

> Owner: Person A (backend) + Person B (frontend) | Phase: 3

### AUTH-001: Register endpoint
- **Points**: 3
- **Phase**: 3 (Day 13)
- **Blocked by**: INFRA-002 (User model)
- **Assignee**: Person A
- **Description**: `POST /api/auth/register` — accepts email, password, name, program_id. Hashes password with bcrypt. Returns JWT. Validates email uniqueness.
- **Acceptance criteria**:
  - [ ] Successful registration returns JWT + user_id
  - [ ] Duplicate email returns 400
  - [ ] Password is bcrypt hashed (not stored in plaintext)
  - [ ] JWT contains user_id and email

### AUTH-002: Login endpoint
- **Points**: 2
- **Phase**: 3 (Day 13)
- **Blocked by**: AUTH-001
- **Assignee**: Person A
- **Description**: `POST /api/auth/login` — accepts email, password. Verifies against hash. Returns JWT.
- **Acceptance criteria**:
  - [ ] Valid credentials return JWT
  - [ ] Invalid credentials return 401
  - [ ] Non-existent email returns 401 (not 404 — don't leak user existence)

### AUTH-003: Registration UI (modal + program selection + completed courses)
- **Points**: 5
- **Phase**: 3 (Day 13-14)
- **Blocked by**: AUTH-001, API-004 (programs list)
- **Assignee**: Person B
- **Description**: RegisterModal component. Fields: email, password, name, program dropdown (fetched from API), completed courses checklist (filtered by program). On submit: register → store JWT → update auth state.
- **Acceptance criteria**:
  - [ ] Modal opens from header login button
  - [ ] Program dropdown populated from `/api/programs`
  - [ ] Completed courses can be checked off with optional grade entry
  - [ ] Successful registration closes modal and updates header (shows user name)
  - [ ] JWT stored in localStorage

### AUTH-004: Login UI + auth state management
- **Points**: 3
- **Phase**: 3 (Day 14)
- **Blocked by**: AUTH-002
- **Assignee**: Person B
- **Description**: LoginModal component. `useAuth.ts` composable + `authStore.ts` Pinia store. JWT stored in localStorage. Auth header automatically added to API calls. Protected routes redirect to login.
- **Acceptance criteria**:
  - [ ] Login modal with email + password
  - [ ] JWT persists across page reloads (localStorage)
  - [ ] API calls include `Authorization: Bearer <token>` header
  - [ ] Logout clears token and resets state
  - [ ] Chat widget prompts login if not authenticated

---

## Epic 8: Conversation Memory

> Owner: Person C | Phase: 3

### MEM-001: Redis message storage (tier 1)
- **Points**: 3
- **Phase**: 3 (Day 13)
- **Blocked by**: CHAT-004
- **Assignee**: Person C
- **Description**: Create `core/memory.py`. Store last 20 messages per session in Redis (RPUSH). Load on new WebSocket connection. 2-hour TTL per session. Messages include role, content, tool calls, and tool results.
- **Acceptance criteria**:
  - [ ] Messages persist across WebSocket reconnects (same session_id)
  - [ ] Last 20 messages loaded when session resumes
  - [ ] Session expires after 2 hours of inactivity
  - [ ] New session starts fresh

### MEM-002: Running summary (tier 2)
- **Points**: 5
- **Phase**: 3 (Day 14-15)
- **Blocked by**: MEM-001
- **Assignee**: Person C
- **Description**: When message count exceeds 20, trigger LLM summarization. Summary captures: student's major, completed courses, decisions made, preferences, courses being considered. Summary stored in Redis, prepended to every LLM call. After summarization, trim to last 10 messages.
- **Acceptance criteria**:
  - [ ] Summary generated when message count > 20
  - [ ] Summary includes key facts (major, courses, decisions)
  - [ ] Summary prepended to LLM context as `<conversation_summary>`
  - [ ] Message list trimmed to last 10 after summarization
  - [ ] Follow-up questions after summarization correctly reference earlier context

### MEM-003: Cross-session persistence (decision history)
- **Points**: 3
- **Phase**: 3 (Day 15-16)
- **Blocked by**: CHAT-005 (save_decision tool), API-005 (student endpoints)
- **Assignee**: Person C
- **Description**: Wire `save_decision` tool end-to-end. On new session, `get_student_profile` loads prior decisions. LLM references them: "Last time you were interested in CSCI 3104 — still planning on that?"
- **Acceptance criteria**:
  - [ ] Student says "I want to take CSCI 3104" → LLM calls save_decision → stored in PostgreSQL
  - [ ] New session starts → LLM calls get_student_profile → references prior decisions
  - [ ] Decisions viewable via `GET /api/students/me`

---

## Epic 9: Security Hardening

> Owner: Person C | Phase: 3 | Labels: `security`

### SEC-001: System prompt hardening + delimiter tags
- **Points**: 3
- **Phase**: 3 (Day 15)
- **Blocked by**: CHAT-008
- **Assignee**: Person C
- **Labels**: `security`
- **Description**: Write the production system prompt with behavioral boundaries: only academic advising, never reveal internals, never access other users' data. Wrap all context in delimiter tags. Add the "flagged for injection" internal warning pattern.
- **Acceptance criteria**:
  - [ ] System prompt defines behavioral boundaries
  - [ ] Retrieved context wrapped in `<retrieved_context>` tags
  - [ ] User profile wrapped in `<user_profile>` tags
  - [ ] LLM declines non-academic requests ("What's the weather?")
  - [ ] LLM doesn't reveal system prompt when asked

### SEC-002: Input sanitizer
- **Points**: 2
- **Phase**: 3 (Day 16)
- **Blocked by**: CHAT-008
- **Assignee**: Person B
- **Labels**: `security`
- **Description**: Create `core/input_sanitizer.py`. Max 2000 characters. Strip zero-width characters and control characters. Flag known injection patterns ("ignore previous", "system:", "you are now") — don't block, but add internal warning to LLM context.
- **Acceptance criteria**:
  - [ ] Messages > 2000 chars are truncated
  - [ ] Control characters stripped
  - [ ] Injection patterns flagged (not blocked)
  - [ ] Flagged messages get internal warning prepended to LLM context

### SEC-003: Output validator
- **Points**: 2
- **Phase**: 3 (Day 16-17)
- **Blocked by**: CHAT-008
- **Assignee**: Person B
- **Labels**: `security`
- **Description**: Create `core/output_validator.py`. Validate `structured_data` and `suggested_actions` against Pydantic schemas before sending to frontend. Strip if invalid. PII pattern scan (email addresses, student IDs). Scope check (filter non-academic content).
- **Acceptance criteria**:
  - [ ] Invalid structured_data stripped (only text reply sent)
  - [ ] Email-like patterns in output are flagged
  - [ ] Response always matches ChatResponse schema

### SEC-004: Security test suite
- **Points**: 5
- **Phase**: 3 (Day 17-18)
- **Blocked by**: SEC-001, SEC-002, SEC-003, CHAT-006
- **Assignee**: Person C
- **Labels**: `security`
- **Description**: Write `tests/test_security.py`. Test: injection attempts (direct prompt, tool abuse, context tampering), auth enforcement (user_id override), rate limiting, output validation, PII scanning.
- **Acceptance criteria**:
  - [ ] "Ignore your instructions" doesn't change LLM behavior
  - [ ] Tool call with fake user_id gets overridden with JWT user_id
  - [ ] 11th tool call in one turn is blocked
  - [ ] Malformed structured_data is stripped from response
  - [ ] All security tests pass in CI

---

## Epic 10: GCP Deployment

> Owner: Person A | Phase: 4

### DEPLOY-001: Terraform — VPC + networking
- **Points**: 5
- **Phase**: 4 (Day 20)
- **Blocked by**: Nothing (infrastructure only)
- **Assignee**: Person A
- **Description**: Create `infra/network.tf`. VPC, private subnet (10.0.0.0/24), firewall rules (allow-vpc-connector, allow-internal, allow-iap-ssh, default-deny), Serverless VPC Connector. Create `infra/main.tf` (provider, GCS backend), `infra/variables.tf`, `infra/outputs.tf`, `infra/terraform.tfvars.example`.
- **Acceptance criteria**:
  - [ ] `terraform plan` succeeds
  - [ ] VPC created with private subnet
  - [ ] Firewall rules match architecture doc
  - [ ] VPC connector created
  - [ ] No public IPs on any resource

### DEPLOY-002: Terraform — Data VM
- **Points**: 3
- **Phase**: 4 (Day 20-21)
- **Blocked by**: DEPLOY-001
- **Assignee**: Person A
- **Description**: Create `infra/data-vm.tf`. e2-medium Compute Engine VM. Startup script installs Docker Compose, starts PostgreSQL + Neo4j + Redis. Persistent disk for data. Static internal IP (10.0.0.10). Create `infra/scripts/data-vm-startup.sh`.
- **Acceptance criteria**:
  - [ ] VM boots and runs startup script
  - [ ] `gcloud compute ssh data-services --tunnel-through-iap` works
  - [ ] PostgreSQL, Neo4j, Redis accessible from within VPC
  - [ ] Data persists across VM stop/start (persistent disk)

### DEPLOY-003: Terraform — Ollama MIG + auto-scaling
- **Points**: 5
- **Phase**: 4 (Day 21)
- **Blocked by**: DEPLOY-001, DEPLOY-002 (needs Redis for queue)
- **Assignee**: Person A
- **Description**: Create `infra/ollama-mig.tf`. Instance template (spot g2-standard-4, L4 GPU, startup script). MIG with min 0 / max 3. Autoscaler on custom metric (Redis queue depth). Create `infra/monitoring.tf` (custom metric definition). Create `infra/scripts/ollama-worker-startup.sh` and `infra/scripts/queue-depth-exporter.py`.
- **Acceptance criteria**:
  - [ ] Instance template creates with GPU
  - [ ] MIG starts with target_size 0
  - [ ] Manual resize to 1 boots a GPU worker
  - [ ] Worker pulls from Redis queue
  - [ ] queue-depth-exporter publishes metric to Cloud Monitoring
  - [ ] Autoscaler responds to metric changes

### DEPLOY-004: Terraform — Cloud Run services
- **Points**: 3
- **Phase**: 4 (Day 21-22)
- **Blocked by**: DEPLOY-001, DEPLOY-005 (Artifact Registry)
- **Assignee**: Person A
- **Description**: Create `infra/cloud-run.tf`. 3 Cloud Run services (course-search-api, chat-service, frontend). VPC connector attached. Env vars from Terraform. Chat service has min_instances=1. Create `infra/iam.tf` (service accounts).
- **Acceptance criteria**:
  - [ ] All 3 Cloud Run services deploy
  - [ ] Services can reach data VM (PostgreSQL, Neo4j, Redis) via VPC
  - [ ] Chat service has min_instances=1
  - [ ] CORS_ALLOWED_ORIGINS set to frontend Cloud Run URL
  - [ ] Health endpoints return 200

### DEPLOY-005: Artifact Registry
- **Points**: 1
- **Phase**: 4 (Day 20)
- **Blocked by**: DEPLOY-001
- **Assignee**: Person A
- **Description**: Create `infra/artifact-registry.tf`. Docker repository for container images.
- **Acceptance criteria**:
  - [ ] Registry created
  - [ ] Docker images can be pushed to it

### DEPLOY-006: Data ingestion on GCP
- **Points**: 2
- **Phase**: 4 (Day 22)
- **Blocked by**: DEPLOY-002, DATA-005
- **Assignee**: Person A
- **Description**: SSH to data VM via IAP tunnel with port forwarding. Run data ingestion against GCP databases. Pull Ollama models. Verify data counts.
- **Acceptance criteria**:
  - [ ] All courses, programs, requirements in GCP databases
  - [ ] Embeddings generated and vector index created
  - [ ] Ollama model pulled on GPU worker
  - [ ] All validation counts match local

### DEPLOY-007: End-to-end GCP verification
- **Points**: 2
- **Phase**: 4 (Day 22-23)
- **Blocked by**: DEPLOY-004, DEPLOY-006
- **Assignee**: Person A
- **Description**: Test the full flow on GCP. Course search, chat with AI, auth, memory, decisions.
- **Acceptance criteria**:
  - [ ] Frontend loads at Cloud Run URL
  - [ ] Course search returns results
  - [ ] Chat connects via WebSocket (WSS)
  - [ ] AI responds with tool-retrieved data
  - [ ] Response time < 5s on GPU (vs 30s on CPU)

---

## Epic 11: CI/CD

> Owner: Person B | Phase: 4

### CICD-001: GitHub Actions CI pipeline
- **Points**: 2
- **Phase**: 4 (Day 20)
- **Blocked by**: Nothing
- **Assignee**: Person B
- **Description**: Create `.github/workflows/ci.yml`. On PR: uv sync, ruff check, ruff format --check, mypy, pytest.
- **Acceptance criteria**:
  - [ ] CI runs on every PR
  - [ ] Fails if lint, format, type check, or tests fail
  - [ ] Status check shown on PR page

### CICD-002: GitHub Actions deploy pipeline
- **Points**: 3
- **Phase**: 4 (Day 21-22)
- **Blocked by**: DEPLOY-004, DEPLOY-005
- **Assignee**: Person B
- **Description**: Create `.github/workflows/deploy.yml`. On push to main: build Docker images, push to Artifact Registry, deploy new revisions to Cloud Run.
- **Acceptance criteria**:
  - [ ] Pushing to main triggers build + deploy
  - [ ] All 3 images built and pushed
  - [ ] Cloud Run services updated with new revision
  - [ ] Deployment completes in < 10 minutes

---

## Epic 12: Demo Prep

> Owner: Everyone | Phase: 4

### DEMO-001: Prompt engineering refinement
- **Points**: 5
- **Phase**: 4 (Day 22-23)
- **Blocked by**: DEPLOY-007 (system running on GCP)
- **Assignee**: Person C
- **Description**: Test 30+ conversation flows on the live system. Tune system prompt, tool descriptions, and response formatting. Document any model quirks and workarounds.
- **Acceptance criteria**:
  - [ ] 5 core scenarios work reliably (listed in implementation guide)
  - [ ] Tool calling success rate > 90% on test scenarios
  - [ ] Responses are natural and helpful
  - [ ] Model doesn't hallucinate course data

### DEMO-002: Demo script + rehearsal
- **Points**: 3
- **Phase**: 4 (Day 23-24)
- **Blocked by**: DEMO-001
- **Assignee**: Everyone
- **Description**: Write a 10-minute demo script with 3-4 compelling scenarios. Practice the demo. Prepare backup plan (recorded video) in case of live issues.
- **Acceptance criteria**:
  - [ ] Demo script covers: course search, chat advising, prerequisite checking, schedule planning
  - [ ] Each team member knows their part
  - [ ] Demo rehearsed at least twice
  - [ ] Backup video recorded
  - [ ] Pre-warm script ready (resize MIG, send warmup message)

### DEMO-003: Presentation slides
- **Points**: 3
- **Phase**: 4 (Day 23-24)
- **Blocked by**: Nothing
- **Assignee**: Everyone
- **Description**: Prepare presentation covering: problem statement, architecture diagram, tech stack decisions, demo, scaling strategy, security model, lessons learned.
- **Acceptance criteria**:
  - [ ] Slides cover all major architecture decisions
  - [ ] Architecture diagram is clean and readable
  - [ ] Demo is embedded in the presentation flow
  - [ ] Timing fits in allotted presentation window

---

## Story Dependency Graph

```
INFRA-001 ──→ INFRA-002 ──→ INFRA-004 ──→ INFRA-007
    │              │              │
    │              │              └──→ API-001 ──→ API-002 ──→ API-006
    │              │                       │
    │              │              └──→ API-003
    │              │                       │
    │              │              └──→ API-004 ──→ AUTH-003
    │              │
    │              ├──→ INFRA-005 ──→ CHAT-001 ──→ FE-008
    │              │
    │              ├──→ DATA-001 ──→ DATA-003 ──→ DATA-005
    │              │         │
    │              │         └──→ DATA-004 ──→ DATA-005
    │              │
    │              ├──→ DATA-002 ──→ DATA-005
    │              │
    │              └──→ API-005 ──→ MEM-003
    │
    ├──→ INFRA-003 ──→ INFRA-007
    │         │
    │         ├──→ DATA-004
    │         ├──→ DATA-006
    │         ├──→ CHAT-003
    │         └──→ CHAT-004
    │
    └──→ INFRA-006

FE-001 ──→ FE-002 ──→ FE-003 ──→ FE-004
    │              │
    │              └──→ FE-006 ──→ FE-007 ──→ FE-008
    │                                   │
    │                                   └──→ FE-009
    │
    └──→ FE-005

INFRA-005 ──→ CHAT-000 (LangGraph spike)

CHAT-002 + CHAT-003 ──→ CHAT-005 ──→ CHAT-006 ──┐
                              │                   ├──→ CHAT-008 ──→ CHAT-011
                     CHAT-007 ┘                   │
                     CHAT-010 ────────────────────┘
                                                  CHAT-008 ──→ SEC-001 ──→ SEC-004
                                                               SEC-002 ──→ SEC-004
                                                               SEC-003 ──→ SEC-004

CHAT-004 ──→ MEM-001 ──→ MEM-002

AUTH-001 ──→ AUTH-002
AUTH-001 ──→ AUTH-003
AUTH-002 ──→ AUTH-004

DEPLOY-001 ──→ DEPLOY-002 ──→ DEPLOY-003
    │                  │
    │                  └──→ DEPLOY-006 (+ DATA-005) ──→ DEPLOY-007
    │
    ├──→ DEPLOY-005 ──→ DEPLOY-004 ──→ DEPLOY-007
    │
    └──→ DEPLOY-004

DEPLOY-007 ──→ DEMO-001 ──→ DEMO-002
```

---

## Sprint Plan

### Sprint 1: Foundation (Days 1-5, Mar 25-29)
**Goal**: Full stack runs locally, data ingested, model validated.

| Story | Points | Assignee | Day |
|-------|--------|----------|-----|
| INFRA-001 | 2 | Person A | 1 |
| INFRA-002 | 5 | Person A | 1 |
| INFRA-003 | 3 | Person A | 1 |
| INFRA-004 | 2 | Person A | 1-2 |
| INFRA-005 | 2 | Person A | 1-2 |
| INFRA-006 | 1 | Person A | 1 |
| INFRA-007 | 1 | Person A | 2 |
| FE-001 | 2 | Person B | 1 |
| FE-002 | 3 | Person B | 2-3 |
| FE-003 | 3 | Person B | 3-4 |
| FE-005 | 1 | Person B | 2 |
| FE-006 | 2 | Person B | 4 |
| FE-007 | 3 | Person B | 4-5 |
| FE-009 | 2 | Person B | 5 |
| DATA-001 | 5 | Person C | 1-3 |
| DATA-002 | 5 | Person C | 2-4 |
| DATA-003 | 5 | Person C | 2-4 |
| DATA-004 | 3 | Person C | 4-5 |
| DATA-005 | 2 | Person C | 5 |
| DATA-006 | 3 | Person B | 4-5 |
| CHAT-000 | 2 | Person C | 5-6 |
| **Total** | **57** | | |

**Per-person**: A=16, B=19, C=22. CHAT-000 spans into Day 6 (Sprint 2) but is timeboxed to 1 day.

### Sprint 2: Core Features (Days 6-12, Mar 30 - Apr 5)
**Goal**: Course search end-to-end. Chat with tool calling.

| Story | Points | Assignee | Day |
|-------|--------|----------|-----|
| API-001 | 3 | Person A | 6-7 |
| API-002 | 2 | Person A | 7 |
| API-003 | 3 | Person A | 7-8 |
| API-004 | 2 | Person A | 8 |
| API-005 | 3 | Person A | 8-9 |
| API-006 | 3 | Person A | 9 |
| FE-004 | 3 | Person A | 9-10 |
| FE-008 | 5 | Person B | 8-12 |
| CHAT-001 | 2 | Person C | 6-7 |
| CHAT-002 | 5 | Person C | 7-9 |
| CHAT-003 | 2 | Person A | 7-8 |
| CHAT-004 | 3 | Person C | 8-9 |
| CHAT-005 | 3 | Person C | 9-10 |
| CHAT-006 | 3 | Person C | 10 |
| CHAT-007 | 3 | Person C | 10-11 |
| CHAT-008 | 8 | Person C | 10-12 |
| CHAT-009 | 3 | Person A | 8 |
| CHAT-010 | 3 | Person C | 9-10 |
| CHAT-011 | 5 | Person B | 12-13 |
| **Total** | **64** | | |

**Per-person**: A=24, B=10, C=30. Person C has the heaviest load (chat core chain). CHAT-011 may spill into Sprint 3.

### Sprint 3: Integration + Polish (Days 13-19, Apr 6-12)
**Goal**: Full local demo with auth, memory, security.

| Story | Points | Assignee | Day |
|-------|--------|----------|-----|
| AUTH-001 | 3 | Person A | 13 |
| AUTH-002 | 2 | Person A | 13 |
| AUTH-003 | 5 | Person B | 13-14 |
| AUTH-004 | 3 | Person B | 14 |
| MEM-001 | 3 | Person C | 13 |
| MEM-002 | 5 | Person C | 14-15 |
| MEM-003 | 3 | Person C | 15-16 |
| SEC-001 | 3 | Person C | 15 |
| SEC-002 | 2 | Person B | 16 |
| SEC-003 | 2 | Person B | 16-17 |
| SEC-004 | 5 | Person C | 17-18 |
| **Total** | **36** | | |

**Per-person**: A=5, B=12, C=19. Lighter sprint — buffer for bug fixes and integration issues from Sprint 2.

### Sprint 4: Deploy + Demo (Days 20-24, Apr 13-15)
**Goal**: Live on GCP, demo rehearsed.

| Story | Points | Assignee | Day |
|-------|--------|----------|-----|
| DEPLOY-001 | 5 | Person A | 20 |
| DEPLOY-002 | 3 | Person A | 20-21 |
| DEPLOY-003 | 5 | Person A | 21 |
| DEPLOY-004 | 3 | Person A | 21-22 |
| DEPLOY-005 | 1 | Person A | 20 |
| DEPLOY-006 | 2 | Person A | 22 |
| DEPLOY-007 | 2 | Person A | 22-23 |
| CICD-001 | 2 | Person B | 20 |
| CICD-002 | 3 | Person B | 21-22 |
| DEMO-001 | 5 | Person C | 22-23 |
| DEMO-002 | 3 | Everyone | 23-24 |
| DEMO-003 | 3 | Everyone | 23-24 |
| **Total** | **37** | | |

**Per-person**: A=21, B=5, C=11. Person A heavy on Terraform. Person B lighter — can help with branding polish and bug fixes.

---

## Summary

| Metric | Value |
|--------|-------|
| **Total stories** | 63 |
| **Total story points** | 194 |
| **Sprints** | 4 (5 + 7 + 7 + 5 days) |
| **Person A (teammate)** | 66 pts, 25 stories — Infra, API, Auth backend, CHAT-003/009, Deploy |
| **Person B (teammate)** | 46 pts, 16 stories — Frontend, Auth UI, CI/CD, CHAT-011, DATA-006, SEC-002/003 |
| **Person C (Andrew)** | 76 pts, 20 stories — Data ingestion, Chat core, Memory, SEC-001/004, Demo |
| **Shared** | 6 pts, 2 stories — DEMO-002 (3), DEMO-003 (3) |
| **Cross-person blocks** | 4 (all cross-sprint — zero mid-sprint blocking) |
| **Critical path stories** | INFRA-002, INFRA-003, INFRA-007, DATA-001, DATA-006, CHAT-001, CHAT-010, CHAT-008 |
| **Highest risk story** | CHAT-008 (LangGraph engine — 8 points, complex integration; de-risked by CHAT-000 spike) |
| **Security stories** | 5 (SEC-001 through SEC-004 + CHAT-006) |
