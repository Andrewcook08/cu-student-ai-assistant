# Jira Epics and Stories

> Import these into Jira to track implementation progress. Epics map to major system areas. Stories are sized in story points (1=trivial, 2=small, 3=medium, 5=large, 8=complex). Dependencies are explicit — don't start a story until its blockers are done.
>
> **Naming convention**: `[SERVICE]-NNN` where SERVICE is INFRA, DATA, API, CHAT, FE, AUTH, MEM, SEC, DEPLOY, CICD, DEMO.
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

> Owner: Person A (Scott) | Phase: 1 | Priority: Highest (unblocks everything)
>
> **Note**: Andrew is picking up INFRA-001 (repo skeleton + Docker) to bootstrap the team. Scott owns INFRA-002 and INFRA-003 (the real code).

### INFRA-001: Repo skeleton + Docker Compose
- **Points**: 3
- **Phase**: 1 (Day 1)
- **Blocked by**: Nothing
- **Assignee**: Person C (Andrew — bootstrapping for the team)
- **Labels**: `critical-path`
- **Status**: ✅ Done (Sprint 1)
- **Description**: Create the full repo skeleton with no business logic. Root `pyproject.toml` with workspace members, `.python-version`, `.gitignore`. All directory structures for shared/, services/course-search-api/, services/chat-service/, data/, frontend/. Each workspace member gets a `pyproject.toml` and empty `__init__.py` files. Minimal `main.py` per service (FastAPI + health endpoint only — no shared imports). Dockerfiles for each service. `docker-compose.yml` with 7 services and healthchecks. `.env.example`. `data/raw/.gitkeep`.
- **Acceptance criteria**:
  - [x] `uv sync` succeeds from repo root
  - [x] `uv run ruff check .` passes
  - [x] `.gitignore` covers Python, Node, Docker, Terraform, IDE, OS files
  - [x] `cp .env.example .env && docker compose up -d --build` starts all 7 containers
  - [x] `docker compose ps` shows all data services as "healthy"
  - [x] `curl http://localhost:8000/api/health` → 200
  - [x] `curl http://localhost:8001/api/chat/health` → 200
  - [x] PostgreSQL, Neo4j, Redis, Ollama all accessible
  - [x] `data/raw/` exists with `.gitkeep`, JSON files gitignored
  - [x] Pushed to `main` — all team members can clone and run

### INFRA-002: Create shared Python package
- **Points**: 5
- **Phase**: 1 (Day 2-3)
- **Blocked by**: INFRA-001
- **Assignee**: Person A (Scott)
- **Labels**: `critical-path`
- **Status**: ✅ Done (Sprint 1)
- **Description**: Fill in the `shared/` package with real code: `config.py` (pydantic-settings), `database.py` (SQLAlchemy engine + session + get_db), `models.py` (all ORM models), `auth.py` (JWT create/decode, password hash/verify), `schemas.py` (shared Pydantic models: CourseCard, Action, ChatRequest, ChatResponse, ErrorResponse).
- **Acceptance criteria**:
  - [x] `shared/shared/config.py` reads all env vars from `.env`
  - [x] `shared/shared/models.py` has all 9 tables: courses, sections, course_attributes, programs, requirements, users, completed_courses, student_decisions, tool_audit_log
  - [x] `shared/shared/auth.py` can create and decode JWTs, hash and verify passwords
  - [x] `shared/shared/schemas.py` has CourseCard, Action, ChatRequest, ChatResponse, ErrorResponse
  - [x] `from shared.config import settings` works from any workspace member

### INFRA-003: Wire services to shared package
- **Points**: 3
- **Phase**: 1 (Day 3-4)
- **Blocked by**: INFRA-001, INFRA-002
- **Assignee**: Person A (Scott)
- **Labels**: `critical-path`
- **Status**: ✅ Done (Sprint 1)
- **Description**: Update service `main.py` files to import from shared: add CORS middleware with settings, lifespan events (create tables, connect to services). Create `dependencies.py` (get_db, get_current_user). Create empty route files and empty test files. Verify full stack works with real shared imports.
- **Acceptance criteria**:
  - [x] Both services import from shared (config, database, models)
  - [x] CORS middleware configured with `settings.cors_origins_list`
  - [x] Course Search API lifespan creates tables via `Base.metadata.create_all`
  - [x] `dependencies.py` has `get_db` and `get_current_user`
  - [x] Empty route files exist: `routes/courses.py`, `routes/programs.py`, `routes/auth.py`, `routes/students.py`, `routes/chat.py`
  - [x] Empty test directories with `conftest.py`
  - [x] `docker compose up -d --build` still works with real imports
  - [x] `uv run ruff check . && uv run mypy .` passes

---

## Epic 2: Data Ingestion Pipeline

> Owner: Person C | Phase: 1 | Priority: Highest (unblocks API + Chat)

### DATA-001: Parse cu_classes.json into course + section records
- **Points**: 5
- **Phase**: 1 (Day 1-3)
- **Blocked by**: INFRA-002 (for SQLAlchemy models)
- **Assignee**: Person C
- **Labels**: `critical-path`
- **Status**: ✅ Done (Sprint 1)
- **Description**: Write `data/ingest/ingest_courses.py`. Parse the JSON structure (department code → array of course objects). Extract dept code from course code. Strip "This section is closed" prefix from CRN. Handle credits as text. Deduplicate courses by code (topics courses appear multiple times with different titles) and extract pipe-delimited topic_titles. Normalize newline-delimited attributes into `course_attributes` table (split each line on `: ` into college/category pairs). Write to PostgreSQL (`courses`, `sections`, `course_attributes` tables) and Neo4j (`Course`, `Section`, `Department`, `Attribute` nodes with `HAS_ATTRIBUTE` edges). Must be idempotent (upsert).
- **Acceptance criteria**:
  - [x] PostgreSQL `courses` table count matches architecture.md § Datasets (deduplicated by course code)
  - [x] PostgreSQL `sections` table count matches architecture.md § Datasets
  - [x] PostgreSQL `course_attributes` table populated per architecture.md § Datasets
  - [x] Neo4j node counts match architecture.md § Datasets (`Course`, `Department`, `Attribute` nodes with `HAS_ATTRIBUTE` edges)
  - [x] Re-running does not create duplicates
  - [x] CRN values are clean numeric strings
  - [x] topic_titles populated for courses with multiple topic variants

### DATA-002: Parse cu_degree_requirements.json into program + requirement records
- **Points**: 5
- **Phase**: 1 (Day 2-4)
- **Blocked by**: INFRA-002
- **Assignee**: Person C
- **Labels**: `critical-path`
- **Status**: ✅ Done (Sprint 1)
- **Description**: Write `data/ingest/ingest_requirements.py`. Parse the flat list per program. Detect: `or`-prefix entries, choose-N groups, `&`-bundles, `/`-cross-listed, section headers, free-text requirements, total credit hours. Classify each entry's `requirement_type`. Write to PostgreSQL (programs + requirements tables) and Neo4j (Program + Requirement nodes with HAS_REQUIREMENT, SATISFIED_BY, OR_ALTERNATIVE relationships).
- **Acceptance criteria**:
  - [x] PostgreSQL `programs` table count matches architecture.md § Datasets
  - [x] PostgreSQL `requirements` table has correct count per program
  - [x] Neo4j Program node count matches architecture.md § Datasets, with HAS_REQUIREMENT edges
  - [x] OR alternatives are linked with OR_ALTERNATIVE relationships
  - [x] Choose-N groups are correctly identified
  - [x] Re-running does not create duplicates

### DATA-003: Prerequisite regex parser
- **Points**: 5
- **Phase**: 1 (Day 2-4)
- **Blocked by**: DATA-001 (needs courses in DB)
- **Assignee**: Person C
- **Status**: ✅ Done (Sprint 1)
- **Description**: Write `data/ingest/parse_prerequisites.py`. Regex patterns for: single prereq, OR alternatives, AND requirements, corequisites, restrictions. For each match, create HAS_PREREQUISITE edges in Neo4j with type, min_grade, and raw_text. For non-matching strings, preserve raw_text only (LLM fallback).
- **Acceptance criteria**:
  - [x] Handles all 5 common patterns (single, OR, AND, corequisite, restriction)
  - [x] Neo4j HAS_PREREQUISITE count >80% of courses with prerequisites
  - [x] Every edge has `raw_text` preserved
  - [x] Matched edges have `min_grade` populated
  - [x] Known typos in data ("prerequsite") don't crash the parser
  - [x] Parse rate ≥80% of courses with prerequisite data

### DATA-004: Build course embeddings via Ollama
- **Points**: 3
- **Phase**: 1 (Day 4-5)
- **Blocked by**: DATA-001, INFRA-001 (Ollama from Docker Compose)
- **Assignee**: Person C
- **Status**: ✅ Done (Sprint 1)
- **Description**: Write `data/ingest/build_embeddings.py`. For each course, generate an embedding from `"{code} {title} {topic_titles} {description} {attributes}"` via Ollama's nomic-embed-text model (attributes joined from `HAS_ATTRIBUTE` edges). Including attributes ensures gen-ed queries like "Engineering humanities requirement" surface relevant courses via vector search. Store on Neo4j Course nodes. Create vector index (`course-embeddings`, 768 dims, cosine).
- **Acceptance criteria**:
  - [x] All 3,410 Course nodes have non-null `embedding` property
  - [x] Vector index `course-embeddings` exists in Neo4j
  - [x] `CALL db.index.vector.queryNodes('course-embeddings', 5, $embedding)` returns results
  - [x] Vector index uses 768 dimensions with cosine similarity
  - [x] Script is idempotent (skips courses that already have embeddings)
  - [x] `uv run pytest data/ingest/tests/test_build_embeddings.py -v` passes (unit tests for text builder, Ollama client, retry logic)

### DATA-005: run_all.py orchestrator + validation
- **Points**: 2
- **Phase**: 1 (Day 5)
- **Blocked by**: DATA-001, DATA-002, DATA-003, DATA-004
- **Assignee**: Person C
- **Status**: ✅ Done (Sprint 1)
- **Description**: Write `data/ingest/run_all.py` that runs all 4 ingestion steps in order with progress logging. Also write `scripts/seed_db.sh` shell wrapper. Run full ingestion and validate all expected counts.
- **Acceptance criteria**:
  - [x] `uv run --package data-ingest python -m data.ingest.run_all` completes without errors
  - [x] All validation queries from the implementation guide pass
  - [x] Total runtime < 15 minutes (embeddings are the bottleneck)

### DATA-006: Validate LLM tool calling with chosen model
- **Points**: 3
- **Phase**: 1 (Day 4-5)
- **Blocked by**: INFRA-001 (Ollama from Docker Compose)
- **Assignee**: Person B
- **Labels**: `critical-path`
- **Status**: ✅ Done (Sprint 1)
- **Description**: Write `scripts/test_tool_calling.py`. Define 7 tool schemas matching the architecture. Write 20+ representative student questions with expected tool names. Test tool calling against the Anthropic API (Claude Sonnet). Report pass rate. If < 80%, test alternative models and document recommendation.
- **Acceptance criteria**:
  - [x] Test script runs against the Anthropic API and produces pass/fail per question
  - [x] Overall pass rate ≥ 80%
  - [x] If fail: recommendation for alternative model documented
  - [x] Model choice decision recorded (resolves open question #2)

---

## Epic 3: Course Search API

> Owner: Person B | Phase: 2 | Priority: High

### API-001: GET /api/courses — filtered course listing
- **Points**: 4
- **Phase**: 2 (Day 6-7)
- **Blocked by**: DATA-001 (courses in PostgreSQL)
- **Assignee**: Person B
- **Status**: ✅ Done (Sprint 1)
- **Description**: Implement course listing with filters: dept, level, instruction_mode, status, credits, text search (q). Offset/limit pagination (default 50). Returns `{items, total, offset, limit}`.
- **Acceptance criteria**:
  - [x] `GET /api/courses?dept=CSCI` returns only CSCI courses
  - [x] `GET /api/courses?q=machine+learning` returns relevant courses
  - [x] `GET /api/courses?limit=10&offset=20` paginates correctly
  - [x] `GET /api/courses?level=undergrad-upper` returns only 3xxx-4xxx courses
  - [x] Multiple filters can be combined
  - [x] Response includes `total` count for pagination UI
  - [x] Response time < 100ms
  - [x] pytest tests in `services/course-search-api/tests/test_courses_list.py` cover: dept filter, level filter, q text search, offset+limit pagination, multiple-filter combination, empty result set. `uv run pytest services/course-search-api/tests/test_courses_list.py -v` passes.

### API-002: GET /api/courses/{code} — course detail with sections
- **Points**: 3
- **Phase**: 2 (Day 7)
- **Blocked by**: DATA-001
- **Assignee**: Person B
- **Status**: ✅ Done (Sprint 1)
- **Description**: Return a single course with all its sections, prerequisite text, and attributes. Include section meeting times, instructor, status.
- **Acceptance criteria**:
  - [x] `GET /api/courses/CSCI 1300` returns course + all sections
  - [x] Sections include crn, meets, instructor, status
  - [x] 404 for non-existent course codes
  - [x] Prerequisites_raw is included
  - [x] pytest tests in `services/course-search-api/tests/test_courses_detail.py` cover: course exists (200 with sections), 404 on unknown code, `prerequisites_raw` included in response. Tests pass.

### API-003: GET /api/courses/search — semantic search via Neo4j vectors
- **Points**: 3
- **Phase**: 2 (Day 7-8)
- **Blocked by**: DATA-004 (embeddings + vector index)
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: Accept a text query, generate embedding via Ollama, search Neo4j vector index, return ranked results with similarity scores.
- **Acceptance criteria**:
  - [ ] `GET /api/courses/search?q=data+science` returns relevant courses
  - [ ] Results include similarity score
  - [ ] Results are sorted by relevance (highest score first)
  - [ ] Response time < 500ms (embedding generation is the bottleneck)

### API-004: GET /api/programs and GET /api/programs/{id}/requirements
- **Points**: 3
- **Phase**: 2 (Day 8)
- **Blocked by**: DATA-002
- **Assignee**: Person B
- **Status**: ✅ Done (Sprint 1)
- **Description**: List all programs (for dropdowns). Get requirements for a specific program, structured by requirement_type.
- **Acceptance criteria**:
  - [x] `GET /api/programs` returns program count matches architecture.md § Datasets, with id, name, type
  - [x] `GET /api/programs/1/requirements` returns structured requirements
  - [x] Requirements are ordered by sort_order
  - [x] OR alternatives are grouped with their parent requirement
  - [x] pytest tests in `services/course-search-api/tests/test_programs.py` cover: list programs, get requirements ordered by sort_order, 404 for unknown program id. Tests pass.

### API-005: GET /api/students/me (student profile read)
- **Points**: 4
- **Phase**: 2-3 (Day 8-9)
- **Blocked by**: INFRA-002 (User model)
- **Assignee**: Person B
- **Status**: ✅ Done (Sprint 1) — GET only. PUT /api/students/me/completed-courses split into sibling story API-005b.
- **Description**: `GET /api/students/me` returns the authenticated student's profile, completed courses with grades, and decisions. Requires JWT auth. Use test JWTs from `shared/auth.py` for development and testing; real login/register flow comes in Phase 3 (AUTH-001/002).
- **Acceptance criteria**:
  - [x] Endpoints require valid JWT (401 without)
  - [x] `GET /api/students/me` returns program, completed courses (with grades), decisions
  - [x] User can only see their own data
  - [x] pytest tests in `services/course-search-api/tests/test_students.py` cover: GET /me with valid JWT (200), GET /me without JWT (401), GET /me accessing another user's data (403). Tests pass.

### API-005b: PUT /api/students/me/completed-courses
- **Points**: 2
- **Phase**: 2 (Sprint 2)
- **Blocked by**: INFRA-002 (User model), API-005 (GET /me shipped Sprint 1)
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: `PUT /api/students/me/completed-courses` lets an authenticated student update their self-reported completed course list with optional grades. Split out of API-005 so the GET work could close cleanly at the end of Sprint 1. Tracked as CUAI-78.
- **Acceptance criteria**:
  - [ ] Endpoint requires valid JWT (401 without)
  - [ ] Accepts `[{course_code, grade}]` payload
  - [ ] Persists completed courses for the authenticated user only (no cross-user writes)
  - [ ] Returns the updated profile or a 204 on success
  - [ ] pytest tests in `services/course-search-api/tests/test_students.py` cover: PUT with valid JWT, PUT without JWT (401), payload validation, cross-user write rejected. Tests pass.

> **Note**: API-006 (CUAI-31) was marked Done in Sprint 1 as a no-op — its standalone test coverage had already been folded into API-001, API-002, API-004, and API-005 per the "tests ship with code" policy (see `docs/development-workflow.md` § Testing Strategy).

---

## Epic 4: Chat Engine (AI + LangGraph)

> Owner: Person C | Phase: 2 | Priority: High

### CHAT-000: LangGraph spike (timeboxed research)
- **Points**: 2
- **Phase**: 1 (Day 5-6)
- **Blocked by**: INFRA-003
- **Assignee**: Person C
- **Status**: 📋 Planned
- **Description**: Timeboxed spike to de-risk the 8-point CHAT-008. Research LangGraph StateGraph, ReAct pattern, and tool binding. Build a minimal working prototype: single tool (e.g., echo tool), no real data, hardcoded Ollama connection. Document patterns and gotchas for the team.
- **Acceptance criteria**:
  - [ ] Minimal LangGraph StateGraph with one tool runs end-to-end
  - [ ] Tool binding and tool-calling loop demonstrated
  - [ ] Key patterns documented (state management, tool loop, error handling)
  - [ ] Timeboxed to 1 day — findings shared regardless of completion

### CHAT-001: Stub WebSocket endpoint (echo)
- **Points**: 2
- **Phase**: 2 (Day 6-7)
- **Blocked by**: INFRA-003
- **Assignee**: Person C
- **Labels**: `critical-path`
- **Status**: ✅ Implemented (PR pending)
- **Description**: Create `routes/chat.py` with WebSocket endpoint at `/ws/chat/{session_id}`. Validate JWT from query param. Accept messages, send typing indicator, echo back. This unblocks Person B's frontend work.
- **Acceptance criteria**:
  - [x] WebSocket connects with valid JWT
  - [x] WebSocket rejects invalid JWT (close code 4001)
  - [x] Server sends `{"type": "typing"}` then `{"type": "chat_response", "reply": "Echo: ..."}`
  - [ ] Person B can connect from Vue frontend

### CHAT-002: Neo4j service layer (graph queries)
- **Points**: 5
- **Phase**: 2 (Day 7-9)
- **Blocked by**: DATA-001, DATA-002, DATA-003 (data in Neo4j)
- **Assignee**: Person C
- **Status**: 📋 Planned
- **Description**: Create `services/neo4j_service.py` with async Neo4j driver. Implement: `vector_search()`, `get_prerequisite_chain()`, `get_degree_requirements()`. Use parameterized Cypher queries.
- **Acceptance criteria**:
  - [ ] `vector_search(embedding)` returns top-10 courses with scores
  - [ ] `get_prerequisite_chain("CSCI 3104")` returns the full chain
  - [ ] `get_degree_requirements("Computer Science")` returns structured requirements
  - [ ] All queries use parameterized inputs (no Cypher injection)
  - [ ] *(security ADR-33)* All Cypher queries use parameterized bindings — never f-string interpolation of user input. Enforce via code review and a test that asserts query strings do not contain `{` inside `MATCH`/`WHERE` clauses.
  - [ ] *(security ADR-33)* Queries are read-only by default; any write query is behind an explicit `write=True` flag on the helper.

### CHAT-003: LLM service + embedding generation
- **Points**: 2
- **Phase**: 2 (Day 7-8)
- **Blocked by**: INFRA-001 (Ollama from Docker Compose for embeddings)
- **Assignee**: Person C
- **Status**: 📋 Planned
- **Description**: `services/ollama_service.py` handles embeddings via Ollama (nomic-embed-text, 768-dim). A new `services/llm_service.py` (or updated `ollama_service.py`) handles chat completion via the Anthropic SDK — `chat_completion()` calls `anthropic.AsyncAnthropic().messages.create()` instead of Ollama `/api/chat`. Functions: `get_embedding(text)` (still Ollama), `chat_completion(messages, tools)` (Anthropic SDK). Anthropic API has its own timeout handling via SDK configuration.
- **Acceptance criteria**:
  - [ ] `get_embedding("data science")` returns 768-dim vector
  - [ ] `chat_completion(messages, tools)` returns model response with tool calls via Anthropic API
  - [ ] Connection errors are handled gracefully

### CHAT-004: Redis service (sessions + inference queue)
- **Points**: 3
- **Phase**: 2 (Day 8-9)
- **Blocked by**: INFRA-001 (Redis from Docker Compose)
- **Assignee**: Person C
- **Status**: ✅ Implemented (PR pending)
- **Description**: Create `services/redis_service.py`. Async Redis client. Implement: session storage, conversation message caching (RPUSH/LRANGE), inference queue (LPUSH/BRPOP), result pub/sub channel. 120s timeout on queue wait with 30s progress update.
- **Acceptance criteria**:
  - [x] Messages stored and retrieved by session_id
  - [x] Session TTL of 2 hours
  - [x] Inference request enqueued and result received via pub/sub
  - [x] 30s progress update sent if still waiting
  - [x] 120s timeout returns graceful error
  - [x] *(security ADR-33)* Production Redis requires `requirepass`, parameterized via `REDIS_PASSWORD` env var; added to `docker-compose.prod.yml` as part of the SEC-008 hand-off. *(chat service reads `redis_password` from `shared.config` via `build_redis_client`; SEC-008 still owns the prod compose override that supplies the env var)*
  - [x] *(security ADR-33)* Session keys are scoped by `user_id`, not just `session_id`, so enumerating session IDs cannot leak another user's session.

### CHAT-005: Tool definitions (@tool functions)
- **Points**: 3
- **Phase**: 2 (Day 9-10)
- **Blocked by**: CHAT-002, CHAT-003
- **Assignee**: Person C
- **Status**: 📋 Planned
- **Description**: Create `core/tools.py`. Define 7 tools with `@tool` decorator: search_courses, lookup_course, check_prerequisites, get_degree_requirements, get_student_profile, find_schedule_conflicts, save_decision. Each tool has a clear docstring for the LLM and calls the appropriate service layer. The search_courses/lookup_course split (fuzzy search by name → exact lookup by code) was validated by the CUAI-32 LangGraph spike.
- **Acceptance criteria**:
  - [ ] All 7 tools defined with typed parameters and descriptive docstrings
  - [ ] Each tool calls the correct service (Neo4j, PostgreSQL, Ollama for embeddings)
  - [ ] Tools return structured dicts (not raw database rows)
  - [ ] Tools are importable and can be bound to the LLM

### CHAT-006: Tool executor with auth enforcement
- **Points**: 3
- **Phase**: 2 (Day 10)
- **Blocked by**: CHAT-005
- **Assignee**: Person C
- **Labels**: `security`
- **Status**: 📋 Planned
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
- **Status**: ✅ Implemented (shipped PR #79, commit 50f9bb5)
- **Description**: Create `core/intent_classifier.py` with a hybrid heuristic-first + optional LLM fallback design. The heuristic regex/keyword pass resolves first (deterministic, no Ollama dependency, catches all five AC examples). If it returns `GENERAL_QUESTION` and an `ollama_client` is supplied, a single `ollama_service.chat_completion` call fires as a fallback using Ollama's structured-output mode — a JSON-schema enum built from the `Intent` StrEnum is passed as `format`, so the model is logit-masked to exactly the five labels. Temperature pinned to 0 via the new `options` kwarg for deterministic argmax. `classify_intent()` is async and never raises — every failure collapses to `GENERAL_QUESTION`. See [ADR-34](decisions.md#adr-34-hybrid-intent-classifier-with-structured-output-llm-fallback-cuai-39--chat-007).
- **Acceptance criteria**:
  - [x] "What CS electives are there?" → `course_search`
  - [x] "What are prerequisites for CSCI 3104?" → `prereq_check`
  - [x] "What do I need for my CS degree?" → `degree_planning`
  - [x] "Can you check my schedule for conflicts?" → `schedule_help`
  - [x] "What is your favorite color?" → `general_question`
  - [x] Classification is fast (< 500ms) — use heuristics or single LLM call
  - [x] LLM fallback uses Anthropic API with JSON prompt instructions so the model cannot emit anything outside the five labels
  - [x] `classify_intent()` never raises — timeouts, malformed JSON, and unknown labels all collapse to `GENERAL_QUESTION`

### CHAT-008: LangGraph conversation engine
- **Points**: 8
- **Phase**: 2 (Day 10-12)
- **Blocked by**: CHAT-005, CHAT-006, CHAT-007, CHAT-010
- **Assignee**: Person C
- **Labels**: `critical-path`
- **Status**: ✅ Done (Sprint 2)
- **Implementation**: LangGraph StateGraph with 5 nodes (classify_intent, build_context, call_llm, tool_node, respond). ChatAnthropic with `temperature=0`. Retry-without-tools fallback, parallel tool execution, 180s graph timeout, atomic Redis persist, CourseCard extraction.
- **Files**: `core/llm_engine.py` (new), `routes/chat.py` (modified), `main.py` (modified)
- **Tests**: 50 unit tests + 7 WebSocket tests, 309 total passing
- **Description**: Create `core/llm_engine.py`. LangGraph StateGraph with nodes: classify_intent → build_context → call_llm → maybe_call_tools (loop) → validate_output → respond. Bind tools to the LLM. Handle the tool-calling loop (LLM generates tool calls → executor runs them → results fed back → LLM generates final response). Wire into the WebSocket endpoint (replace echo stub).
- **Acceptance criteria**:
  - [x] User sends "What CS courses are available?" → LLM calls search_courses → returns course list
  - [x] User sends "Tell me about Data Structures" → LLM calls search_courses → then lookup_course with resolved code
  - [x] User sends "What are prereqs for CSCI 3104?" → LLM calls check_prerequisites → returns chain
  - [x] Multi-tool flow works: LLM calls get_student_profile then get_degree_requirements
  - [x] Tool call retry on malformed JSON works
  - [x] Response includes structured_data (CourseCards) when appropriate
  - [x] End-to-end: WebSocket message → LangGraph → tool calls → LLM response → WebSocket response

### CHAT-009: PostgreSQL service (student data + audit)
- **Points**: 3
- **Phase**: 2 (Day 8)
- **Blocked by**: INFRA-002
- **Assignee**: Person C
- **Status**: 📋 Planned
- **Description**: Create `services/postgres_service.py`. Functions: `get_student_data(user_id)` — returns profile + completed courses with grades + prior decisions. `save_student_decision(user_id, course_code, decision_type, notes)`. `get_schedule_conflicts(course_codes)` — join sections, parse meeting times, find overlaps.
- **Acceptance criteria**:
  - [ ] `get_student_data` returns program, completed courses (with grades), decisions
  - [ ] `save_student_decision` inserts to student_decisions table
  - [ ] `get_schedule_conflicts` detects overlapping meeting times
  - [ ] All functions use parameterized queries
  - [ ] *(security ADR-33)* `tool_audit_log` rows always carry the JWT-derived `user_id`, never a client-supplied value (reinforces ADR-14).
  - [ ] *(security ADR-33)* Audit log table has a documented retention policy (even if enforcement is future work).
  - [ ] *(security ADR-33)* No raw SQL strings concatenating user input — SQLAlchemy ORM or parameterized `text()` only.

### CHAT-010: Context builder
- **Points**: 3
- **Phase**: 2 (Day 9-10)
- **Blocked by**: CHAT-002, CHAT-009
- **Assignee**: Person C
- **Status**: ✅ Done (Sprint 2)
- **Description**: Create `core/context_builder.py`. Assembles context for the LLM prompt from: student profile, conversation summary, retrieved graph/vector data, intent classification. Formats using delimiter tags (`<retrieved_context>`, `<user_profile>`, `<conversation_summary>`).
- **Acceptance criteria**:
  - [x] Context includes student profile when available
  - [x] Context includes conversation summary when available
  - [x] Retrieved data is wrapped in `<retrieved_context>` tags
  - [x] Context fits within model's context window (track token count)
  - [x] *(security ADR-33)* RAG context (retrieved courses, user profile) wrapped in `<retrieved_context>` and `<user_profile>` delimiter tags matching SEC-001.
  - [x] *(security ADR-33)* Context builder strips any characters resembling delimiter tags from retrieved data before wrapping (prevents context-injection via course descriptions).

### CHAT-011: Chat Service test suite
- **Points**: 5
- **Phase**: 2-3 (Day 12-13)
- **Blocked by**: CHAT-008
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: Write pytest tests for the chat service. Test: tool executor auth enforcement (user_id override), tool calling with mock LLM responses, Neo4j service queries, Redis session storage, WebSocket connect/disconnect, intent classification accuracy. Mock LLM responses so tests run without API calls.
- **Acceptance criteria**:
  - [ ] `uv run pytest services/chat-service/tests/ -v` passes
  - [ ] Tests cover: tool executor user_id override, rate limiting, session persistence, intent classification
  - [ ] Test fixtures mock LLM responses (no API calls in CI)
  - [ ] WebSocket connect with valid JWT and reject with invalid JWT tested
  - [ ] At least 80% coverage on `core/` modules
  - [ ] *(security ADR-33)* Test that the `user_id` override in `tool_executor` rejects a tool call carrying a different `user_id` (covers ADR-14).
  - [ ] *(security ADR-33)* Test that a flood of WS messages triggers the SEC-009 limit.

---

## Epic 5: Frontend — Course Search

> Owner: Person B (Rohan) | Phase: 1-2

### FE-001: Vue + Vite + Tailwind project setup
- **Points**: 3
- **Phase**: 1 (Day 1)
- **Blocked by**: Nothing
- **Assignee**: Person B
- **Status**: ✅ Done (Sprint 1)
- **Description**: Initialize Vue 3 project with TypeScript, Router, Pinia, Tailwind, shadcn-vue. Configure Vite proxy for `/api` and `/ws`. Configure CU branding tokens extracted from `frontend/cu-classes.html`'s embedded `<style>` block (see ADR-31 and architecture.md § Frontend for the brand-token table). Copy the embedded `<style>` block from `frontend/cu-classes.html` (lines 8-445) into `src/assets/cu-classes.css` and import it from `main.ts` so subsequent FE-002/FE-003 work has the reference styling available out of the gate. Also set up the Vitest test harness so FE-002 onward can ship component tests in the same PR as their components: install `vitest`, `@vue/test-utils`, `jsdom`, `@vitest/coverage-v8`; create `frontend/vitest.config.ts` (jsdom environment, `@/` alias matching Vite); create `frontend/src/test-setup.ts` wiring Pinia; add `"test"` and `"test:coverage"` npm scripts.
- **Acceptance criteria**:
  - [x] `cd frontend && npm run dev` starts on http://localhost:5173
  - [x] CU brand tokens (`cu-gold` `#CFB87C`, `cu-gold-hover` `#c4a94f`, `cu-black` `#000000`, `cu-panel` `#f5f5f5`, `cu-pane` `#fafafa`, `cu-section-head` `#eee`, `cu-border` `#ddd`, `cu-link` `#0277BD`, `cu-text` `#333`, `cu-muted` `#555`) live in `src/assets/cu-classes.css` — the project uses Tailwind v4 via the `@tailwindcss/vite` plugin, so no standalone `tailwind.config.ts` is needed
  - [x] `src/assets/cu-classes.css` exists, is imported from `main.ts`, and contains the unmodified `<style>` block from `frontend/cu-classes.html` lines 8-445
  - [x] Vite proxy routes `/api/*` to port 8000 and `/ws/*` to port 8001
  - [x] TypeScript compiles without errors
  - [x] Vitest + @vue/test-utils + jsdom installed and configured (`frontend/vitest.config.ts`, `frontend/src/test-setup.ts`)
  - [x] `npm run test -- --run` passes with at least one smoke test (e.g. `src/stores/__tests__/authStore.spec.ts` asserting default state + login/logout transitions)

### FE-002: Layout shell (header, filter sidebar, footer)
- **Points**: 4
- **Phase**: 1 (Day 2-3)
- **Blocked by**: FE-001
- **Assignee**: Person B
- **Description**: Build the Course Search page visual shell using `frontend/cu-classes.html` as a reference (ADR-31 — visual shell only, not the full CU filter set). Port only the header and page frame:
  1. `src/components/layout/AppHeader.vue` — port the `<header class="banner">` markup from `cu-classes.html` lines 449-470 (50px black bar, `CLASS SEARCH` title in CU gold, help icon, cart icon, login/logout area). Replace Font Awesome CDN icons with `lucide-vue-next` (`HelpCircle`, `ShoppingCart`, `LogIn`, `LogOut`). Replace `data-action="login"` / `data-action="logout"` with `@click` handlers against a stub Pinia `authStore`. Replace `.user-anon .anon-only` / `.authed-only` with `v-if` on `authStore.isAuthenticated`.
  2. `src/views/CourseSearchView.vue` — port the `<main class="panels">` flex layout (left `.panel` 370px, right `.empty-space` flex:1, `min-height: calc(100vh - 50px)`)
  3. `src/components/layout/FilterBar.vue` — our minimum-viable filter sidebar (not a port of CU's full form). Single `.section` titled "Search Classes" containing three form controls styled with the ported `.form-group` / `.form-control` / `.btn--full` classes: **Department** dropdown, **Level** dropdown (Undergrad Lower/Upper/Graduate), **Credit Hours** dropdown, plus a SEARCH CLASSES submit button
  4. `src/components/layout/AppFooter.vue` — minimal copyright line
- **Status**: ✅ Done (Sprint 1)
- **Acceptance criteria**:
  - [x] Header displays CU logo/branding with gold/black colors matching `cu-classes.html` lines 449-470 side-by-side
  - [x] No Font Awesome CDN link in rendered HTML; icons come from `lucide-vue-next`
  - [x] Login button is visible when `authStore.isAuthenticated === false`; logout link when `true`
  - [x] Filter sidebar has three working dropdown/input controls: department, level, credits
  - [x] Filter sidebar is visually styled with the reference `.section` / `.form-control` / `.btn--full` classes (uses `src/assets/cu-classes.css` imported in FE-001)
  - [x] `CourseSearchView.vue` mounts at route `/` with the flex layout (370px left panel + flex:1 right pane)
  - [x] Login button visible (non-functional until auth is wired)
  - [x] Not required to be responsive (desktop-first, matching the reference)
  - [x] Vitest specs pass for: `AppHeader.spec.ts` (unauthenticated branch, authenticated branch, logout calls `auth.logout()`, aria-labels present on all icon buttons), `FilterBar.spec.ts` (v-model on each of the 3 controls, `@search` emits exactly `{ dept, level, credits }` with no extra fields), `CourseSearchView.spec.ts` (layout mounts header + 370px panel + right pane + footer)

### FE-003: Course table + detail panel (mock data)
- **Points**: 4
- **Phase**: 1 (Day 3-4)
- **Blocked by**: FE-002
- **Assignee**: Person B
- **Description**: Build the course results components that live in the right `.empty-space` slot of `CourseSearchView.vue`, plus the initial welcome-pane state ported from `cu-classes.html`. Create:
  1. `src/components/course-search/WelcomePane.vue` — ports `<div class="empty-space">` + `.glass` welcome card from `cu-classes.html` lines 1114-1138. Shown on initial page load before any search. Three intro paragraphs may be lightly edited for our app
  2. `src/components/course-search/CourseTable.vue` — renders 15+ mock courses with columns: code, title, credits, status, instruction mode. Replaces `WelcomePane.vue` in the right pane after a search runs (`v-if="hasSearched"`)
  3. `src/components/course-search/CourseRow.vue` — individual row; clicking expands `CourseDetail` below it
  4. `src/components/course-search/CourseDetail.vue` — expanded detail panel showing sections (CRN, time, instructor, status), prerequisites, description
  5. `src/mocks/courses.ts` — 15+ mock course objects used by `CourseTable.vue` in FE-003. FE-004 replaces this with a real API call.

  The filter controls built in FE-002 (`FilterBar.vue`) filter the mock data locally in this ticket. FE-004 wires them to the real `GET /api/courses` endpoint.
- **Status**: ✅ Done (Sprint 1)
- **Acceptance criteria**:
  - [x] `WelcomePane.vue` renders the `.glass` welcome card matching `cu-classes.html` lines 1114-1138 on initial load
  - [x] `CourseTable.vue` renders 15+ mock courses with code, title, credits, status
  - [x] Clicking a row expands `CourseDetail.vue` below it
  - [x] Detail shows sections (CRN, time, instructor, status)
  - [x] `FilterBar.vue` controls filter the mock data locally (e.g. selecting a department narrows the visible rows)
  - [x] After a search runs, `CourseSearchView.vue` swaps `WelcomePane.vue` for `CourseTable.vue` via `v-if="hasSearched"`
  - [x] Vitest specs pass for: `CourseTable.spec.ts` (filter by dept, level, credits, empty-results state, row count), `CourseRow.spec.ts` (click expands, Enter key expands, Space key expands, aria-expanded toggles), `CourseDetail.spec.ts` (renders sections, prerequisites, description, status chips), `WelcomePane.spec.ts` (renders .glass card matching cu-classes.html lines 1114-1138)
  - [x] `frontend/cu-classes.html` is **not modified** by this ticket — it remains an immutable reference per ADR-31

### FE-004: Wire course search to real API
- **Points**: 4
- **Phase**: 2 (Day 9-10)
- **Blocked by**: API-001, API-002, FE-003
- **Assignee**: Person B
- **Status**: ✅ Done (Sprint 1)
- **Description**: Replace the mock course data from FE-003 with real API calls. Create `src/services/courseApi.ts`, `src/composables/useCourses.ts` composable, `src/stores/courseStore.ts` Pinia store. Wire `FilterBar.vue`'s three controls (department, level, credits) to query params on `GET /api/courses` and refetch on change. Implement pagination.
- **Acceptance criteria**:
  - [x] `CourseTable.vue` loads real data from `GET /api/courses` on page load (or on first search)
  - [x] Changing department filter re-fetches from API
  - [x] Pagination works (next/prev, showing total count)
  - [x] Loading state shown while fetching
  - [x] API errors shown as toast notification — **no silent fallback to mock data**. Errors must surface to the user with a retry affordance.
  - [x] Vitest specs pass for: `courseApi.spec.ts` (fetch success, fetch 4xx, fetch 5xx, network error), `useCourses.spec.ts` (loading/error/success reactive state transitions), `CourseSearchView.spec.ts` integration (mocked fetch success renders table; mocked fetch error renders toast, does NOT fall back to mock data)

### FE-005: TypeScript types
- **Points**: 1
- **Phase**: 1-2 (ongoing)
- **Blocked by**: FE-001
- **Assignee**: Person B
- **Status**: ✅ Done (Sprint 1)
- **Description**: Create `src/types/index.ts` with interfaces: Course, Section, Program, StudentProfile, ChatResponse, CourseCard, Action, WsClientMessage, WsServerMessage, PaginatedResponse.
- **Acceptance criteria**:
  - [x] All API response shapes have TypeScript interfaces
  - [x] All WebSocket message types are defined
  - [x] No `any` types anywhere in `frontend/src/` (enforced by tsconfig `strict: true`; once eslint lands in CICD-001, `@typescript-eslint/no-explicit-any: error` in the ruleset)

---

## Epic 6: Frontend — Chat Widget

> Owner: Person B | Phase: 1-2

### FE-006: Chat window shell (expand/collapse)
- **Points**: 3
- **Phase**: 1 (Day 4)
- **Blocked by**: FE-001
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: ChatWindow component. Floating panel in bottom-right corner. Click to expand/collapse. Scrollable message area. Styled with CU branding.
- **Acceptance criteria**:
  - [ ] Chat icon visible in bottom-right corner
  - [ ] Clicking expands a chat panel
  - [ ] Panel has scrollable message area and input bar
  - [ ] Clicking icon again collapses the panel
  - [ ] Panel doesn't block course table interaction when collapsed
  - [ ] Vitest specs pass for: `ChatWindow.spec.ts` (open/close toggle, message append triggers auto-scroll, setTimeout cleanup on unmount using fake timers, Escape key closes the panel, focus moves to textarea on open and returns to trigger on close)

### FE-007: Chat message rendering (markdown + course cards)
- **Points**: 4
- **Phase**: 1 (Day 4-5)
- **Blocked by**: FE-006
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: ChatMessage component (user vs. AI styling). Markdown rendering via markdown-it. StructuredResponse component renders CourseCard lists. SuggestedActions component renders buttons/dropdowns from Action objects.
- **Acceptance criteria**:
  - [ ] User messages right-aligned, AI messages left-aligned
  - [ ] Markdown bold, italic, lists, code blocks render correctly
  - [ ] CourseCards render as styled cards (code, title, credits, status)
  - [ ] SuggestedActions render as clickable buttons/dropdowns
  - [ ] Selecting an action sends structured context back
  - [ ] Vitest specs pass for: `ChatMessage.spec.ts` (markdown renders bold/italic/lists/code/links correctly AND XSS payloads are neutralized — `<script>alert(1)</script>` renders as literal text, `[click](javascript:alert(1))` link is stripped or neutered, `<img src=x onerror=alert(1)>` renders as literal text), `StructuredResponse.spec.ts` (CourseCard renders code/title/credits/status chip), `SuggestedActions.spec.ts` (click emits the full Action object with type + label + payload — not just label string)

### FE-008: WebSocket integration (useChat composable)
- **Points**: 5
- **Phase**: 2 (Day 8-12)
- **Blocked by**: CHAT-001 (stub WebSocket), FE-007
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: Create `useChat.ts` composable. WebSocket connection with JWT auth. Handle message types: typing, chat_response, error, progress. Auto-reconnect with exponential backoff (1s, 2s, 4s, max 30s). Show "Reconnecting..." during retry. Create `chatStore.ts` for state management.
- **Acceptance criteria**:
  - [ ] WebSocket connects with JWT token
  - [ ] Typing indicator shown while AI is processing
  - [ ] Chat response rendered with markdown + structured data
  - [ ] Error messages shown inline in chat
  - [ ] Auto-reconnect works on disconnect (verify by stopping chat-service, restarting)
  - [ ] "Reconnecting..." message shown during retry
  - [ ] 30s progress message rendered when received
  - [ ] *(security ADR-33)* On WS close codes 4001/4002/1008/1009 surface a distinct user-facing error message; do not auto-reconnect on auth failures.
  - [ ] *(security ADR-33)* Never put the JWT in a log line or visible URL (note: token is in query string until the P1 subprotocol upgrade).

### FE-009: Chat input + send
- **Points**: 3
- **Phase**: 1-2 (Day 5, then wire in Day 9)
- **Blocked by**: FE-006
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: ChatInput component. Text input + send button. Enter key sends. Input disabled while AI is responding. Character count indicator (max 2000).
- **Acceptance criteria**:
  - [ ] Enter key sends message
  - [ ] Send button sends message
  - [ ] Input disabled + shows "AI is thinking..." while typing indicator is active
  - [ ] Input prevents > 2000 characters
  - [ ] Input clears after sending
  - [ ] Vitest specs pass for: `ChatInput.spec.ts` (Enter sends, Shift+Enter inserts newline without sending, char limit hard cap at 2000, disabled state when isTyping, empty-message guard in sendMessage handler, input clears after send)

---

## Epic 7: Authentication

> Owner: Person B (Rohan) | Phase: 3

### AUTH-001: Register endpoint
- **Points**: 3
- **Phase**: 3 (Day 13)
- **Blocked by**: INFRA-002 (User model)
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: `POST /api/auth/register` — accepts email, password, name, program_id. Hashes password with bcrypt. Returns JWT. Validates email uniqueness.
- **Acceptance criteria**:
  - [ ] Successful registration returns JWT + user_id
  - [ ] Duplicate email returns 400
  - [ ] Password is bcrypt hashed (not stored in plaintext)
  - [ ] JWT contains user_id and email
  - [ ] *(security ADR-33)* Password minimum 12 chars, not in a small common-password blocklist (e.g. top-100 list embedded in code).
  - [ ] *(security ADR-33)* Email format validated with `pydantic.EmailStr`.
  - [ ] *(security ADR-33)* `POST /api/auth/register` decorated with `slowapi` `3/hour` per IP (depends on SEC-007).
  - [ ] *(security ADR-33)* Response never distinguishes "email already exists" from other 400s in production (consider returning generic 400 to avoid user enumeration).
  - [ ] *(security ADR-33)* `program_id` validated against the `programs` table — unknown → 422.
  - [ ] *(security ADR-33)* User created with `is_active=True` explicitly, never trust client field.

### AUTH-002: Login endpoint
- **Points**: 2
- **Phase**: 3 (Day 13)
- **Blocked by**: AUTH-001
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: `POST /api/auth/login` — accepts email, password. Verifies against hash. Returns JWT.
- **Acceptance criteria**:
  - [ ] Valid credentials return JWT
  - [ ] Invalid credentials return 401
  - [ ] Non-existent email returns 401 (not 404 — don't leak user existence)
  - [ ] *(security ADR-33)* `POST /api/auth/login` decorated with `slowapi` `5/minute` per IP (depends on SEC-007).
  - [ ] *(security ADR-33)* Response body for 401 is identical for "no user", "bad password", and "inactive user" — no user enumeration via timing or error text.
  - [ ] *(security ADR-33)* Use `shared.auth.verify_password` (bcrypt is timing-safe); never compare hashes with `==`.
  - [ ] *(security ADR-33)* Inactive user returns 401 (matches `get_current_user` behavior).
  - [ ] *(security ADR-33)* Successful login returns `{access_token, token_type: "bearer", expires_in}`.
  - [ ] *(security ADR-33)* JWT `sub` claim is `user_id` only — no email or PII.

### AUTH-003: Registration UI (modal + program selection + completed courses)
- **Points**: 5
- **Phase**: 3 (Day 13-14)
- **Blocked by**: AUTH-001, API-004 (programs list)
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: RegisterModal component. Fields: email, password, name, program dropdown (fetched from API), completed courses checklist (filtered by program). On submit: register → store JWT → update auth state.
- **Acceptance criteria**:
  - [ ] Modal opens from header login button
  - [ ] Program dropdown populated from `/api/programs`
  - [ ] Completed courses can be checked off with optional grade entry
  - [ ] Successful registration closes modal and updates header (shows user name)
  - [ ] JWT stored in localStorage
  - [ ] *(security ADR-33)* Client-side password strength meter; server-side validation is authoritative.
  - [ ] *(security ADR-33)* Form fields never stored in browser history (`autocomplete="new-password"`).
  - [ ] *(security ADR-33)* Error messages from server rendered as text only, never `v-html` (FE-007 already uses DOMPurify — confirm the same pattern here).

### AUTH-004: Login UI + auth state management
- **Points**: 3
- **Phase**: 3 (Day 14)
- **Blocked by**: AUTH-002
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: LoginModal component. `useAuth.ts` composable + `authStore.ts` Pinia store. JWT stored in localStorage. Auth header automatically added to API calls. Protected routes redirect to login.
- **Acceptance criteria**:
  - [ ] Login modal with email + password
  - [ ] JWT persists across page reloads (localStorage)
  - [ ] API calls include `Authorization: Bearer <token>` header
  - [ ] Logout clears token and resets state
  - [ ] Chat widget prompts login if not authenticated
  - [ ] *(security ADR-33)* Tokens stored in `sessionStorage` (not `localStorage`) OR in a Pinia store backed by an httpOnly cookie if a BFF is added — choose one and document the trade-off.
  - [ ] *(security ADR-33)* Global fetch/axios interceptor attaches `Authorization: Bearer ${token}` to all `/api/**` calls.
  - [ ] *(security ADR-33)* On 401 response, token is cleared and the user is redirected to login.
  - [ ] *(security ADR-33)* No token logging: never `console.log(token)` anywhere.
  - [ ] *(security ADR-33)* Logout clears both store state and persisted token.
  - [ ] *(security ADR-33)* After SEC-005 merges, the frontend service layer attaches the bearer header (no interceptor exists today).

---

## Epic 8: Conversation Memory

> Owner: Person A (Scott) | Phase: 3

### MEM-001: Redis message storage (tier 1)
- **Points**: 3
- **Phase**: 3 (Day 13)
- **Blocked by**: CHAT-004
- **Assignee**: Person A
- **Status**: 📋 Planned
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
- **Assignee**: Person A
- **Status**: 📋 Planned
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
- **Assignee**: Person A
- **Status**: 📋 Planned
- **Description**: Wire `save_decision` tool end-to-end. On new session, `get_student_profile` loads prior decisions. LLM references them: "Last time you were interested in CSCI 3104 — still planning on that?"
- **Acceptance criteria**:
  - [ ] Student says "I want to take CSCI 3104" → LLM calls save_decision → stored in PostgreSQL
  - [ ] New session starts → LLM calls get_student_profile → references prior decisions
  - [ ] Decisions viewable via `GET /api/students/me`

---

## Epic 9: Security Hardening

> Owner: Person B + Person C | Phase: 3 | Labels: `security`
>
> **Note**: Person C (Andrew) owns SEC-001 (system prompt) and SEC-004 (security tests). Person B (Rohan) owns SEC-002 (input sanitizer) and SEC-003 (output validator).

### SEC-001: System prompt hardening + delimiter tags
- **Points**: 3
- **Phase**: 3 (Day 15)
- **Blocked by**: CHAT-008
- **Assignee**: Person C
- **Labels**: `security`
- **Status**: 📋 Planned
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
- **Status**: 📋 Planned
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
- **Status**: 📋 Planned
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
- **Status**: 📋 Planned
- **Description**: Write `tests/test_security.py`. Test: injection attempts (direct prompt, tool abuse, context tampering), auth enforcement (user_id override), rate limiting, output validation, PII scanning.
- **Acceptance criteria**:
  - [ ] "Ignore your instructions" doesn't change LLM behavior
  - [ ] Tool call with fake user_id gets overridden with JWT user_id
  - [ ] 11th tool call in one turn is blocked
  - [ ] Malformed structured_data is stripped from response
  - [ ] All security tests pass in CI

### SEC-005..009: API & Infrastructure Hardening (Sprint 2 retrofit)

#### SEC-005: Auth enforcement on catalog/search/programs routes (CUAI-79)
- **Points**: 3
- **Phase**: 3 / Sprint 2 (retrofit)
- **Blocked by**: Nothing
- **Blocks**: CUAI-56 follow-up — frontend must attach tokens before this lands in a shared environment
- **Assignee**: Person A (Scott)
- **Labels**: `security`, `phase-3`
- **Status**: 📋 Planned
- **Description**: Add `Depends(get_current_user)` to every non-health route in `services/course-search-api/course_search_api/routes/courses.py` (`list_courses`, `search_courses`, `get_course`) and `routes/programs.py` (`list_programs`, `get_program_requirements`). Update affected tests to pass the existing `auth_headers` fixture (the same pattern used in `tests/test_students.py`). The acute gap is `/api/courses/search`, which currently triggers an Ollama embedding + Neo4j vector search per unauthenticated request — a cost/DoS vector. Health endpoints (`/api/health`, `/api/chat/health`) stay public for load balancer probes.
- **Acceptance criteria**:
  - [ ] All five routes return 401 without a Bearer token
  - [ ] All existing tests pass after adding `auth_headers`
  - [ ] 401-without-token test added for each protected route
  - [ ] Both health endpoints return 200 without a token (lock-in test each)

#### SEC-006: Fail-fast production secret validation (CUAI-80)
- **Points**: 2
- **Phase**: 3 / Sprint 2 (retrofit)
- **Blocked by**: Nothing
- **Assignee**: Person A (Scott)
- **Labels**: `security`, `phase-3`
- **Status**: 📋 Planned
- **Description**: Add an `environment: str = "development"` field and a `validate_production()` method to `shared/shared/config.py`. The validator raises `RuntimeError` when `environment == "production"` AND any of: `jwt_secret_key` contains `"local-development"` or is shorter than 32 chars; `neo4j_password` ∈ {"development", "neo4j", ""}; `cors_origins_list` contains `"*"` or any localhost entry or is empty; `database_url` contains the default compose password. Call the validator from each service's lifespan (course-search-api and chat-service). Scrub `.env.example` of literal secret defaults. This is the first ticket to add Python tests under `shared/`, so the same PR must also add `shared/tests` to `[tool.pytest.ini_options].testpaths` in the root `pyproject.toml` — otherwise CI's `uv run pytest` from the repo root will silently skip the new tests. See `docs/development-workflow.md` § How CI Discovers Tests for the rule.
- **Acceptance criteria**:
  - [ ] Starting either service with `ENVIRONMENT=production` and any default secret raises at boot
  - [ ] `ENVIRONMENT=development` (current local default) is unaffected
  - [ ] Unit tests in `shared/tests/test_config.py` cover each failure branch
  - [ ] Root `pyproject.toml` `[tool.pytest.ini_options].testpaths` includes `shared/tests`, and `uv run pytest` from the repo root collects the new `shared/tests/test_config.py` tests
  - [ ] `.env.example` `JWT_SECRET_KEY=` is empty with a comment showing the generation command

#### SEC-007: Rate limiting middleware (slowapi) (CUAI-81)
- **Points**: 3
- **Phase**: 3 / Sprint 2 (retrofit)
- **Blocked by**: Nothing (consumed by AUTH-001, AUTH-002, SEC-005)
- **Assignee**: Person A (Scott)
- **Labels**: `security`, `phase-3`
- **Status**: ✅ Done (Sprint 2)
- **Description**: Add `slowapi` to both services. Initialize a module-level `Limiter(key_func=get_remote_address)` next to the CORS middleware. Register the SlowAPI 429 handler returning `{"detail":"Too many requests"}` with a `Retry-After` header. Apply per-route limits: `POST /api/auth/register` 3/hour per IP; `POST /api/auth/login` 5/min per IP; `GET /api/courses/search` 30/min per authenticated user (`key_func=user.id`); `PUT /api/students/me/completed-courses` 10/min per user. Production uses Redis-backed storage (`storage_uri=settings.redis_url`); local/test uses in-process.
- **Acceptance criteria**:
  - [x] Login, register, search, and PUT routes enforce the documented limits
  - [x] 429 responses include `Retry-After`
  - [x] Rate limiter uses Redis storage in production, in-memory in tests
  - [x] New `tests/test_rate_limiting.py` covers a 6th login → 429 and a 31st search → 429

#### SEC-008: Production docker-compose override (CUAI-82)
- **Points**: 3
- **Phase**: 3 / Sprint 2 (retrofit)
- **Blocked by**: SEC-006 (the override sets `ENVIRONMENT=production`)
- **Assignee**: Person A (Scott)
- **Labels**: `security`, `phase-3`, `infra`
- **Status**: 📋 Planned
- **Description**: New `docker-compose.prod.yml` override with: cleared `ports:` mapping on `postgres`, `neo4j`, `redis`, and `ollama` (services still reach each other by service name on the internal bridge); `NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:?NEO4J_PASSWORD required}` and `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD required}` so the stack fails fast when secrets are unset; `ENVIRONMENT=production` on the app services to trip the SEC-006 validator. Update `.env.example` to list the new required prod vars (commented optional for local dev). This complements ADR-23 (cloud VPC) for the local prod-simulation path and the self-hosted Data VM described in ADR-19. **No new documentation file is created** — deployment instructions live in `docs/local-development.md` and the new architecture section.
- **Acceptance criteria**:
  - [ ] `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` validates
  - [ ] `docker compose -f ... up` fails fast if `NEO4J_PASSWORD`, `POSTGRES_PASSWORD`, or `JWT_SECRET_KEY` are unset
  - [ ] After `up`, `nc -zv localhost 5432` fails (no host binding) while `docker compose exec course-search-api pg_isready -h postgres` succeeds
  - [ ] App services still reach all datastores by service name
- **Hand-off**: DEPLOY-002 (CUAI-65) is amended to deploy the Data VM with this override

#### SEC-009: WebSocket hardening (CUAI-83)
- **Points**: 3
- **Phase**: 3 / Sprint 2 (retrofit)
- **Blocked by**: Nothing
- **Assignee**: Person A (Scott)
- **Labels**: `security`, `phase-3`
- **Status**: 📋 Planned
- **Description**: Layer four enforcement points on the merged `/ws/chat/{session_id}` stub at `services/chat-service/chat_service/routes/chat.py`. After `accept()` and JWT validation: validate `session_id` shape as UUID v4 (close 4002 on bad shape); enforce 4096-byte max per message frame (`{type:"error",code:"message_too_large"}` and close 1009); per-connection token bucket of 20 messages per rolling 10 s window (`{type:"error",code:"rate_limit"}` and close 1008); capture `user_id` from JWT `sub` and include it in every server-side log line as prep for the CUAI-38 tool executor user-id override (ADR-14). Add a `TODO(P1)` comment about query-string token delivery.
- **Acceptance criteria**:
  - [ ] Oversized message closes with 1009
  - [ ] Flood closes with 1008 after 20 messages in 10 s
  - [ ] Bad `session_id` closes with 4002
  - [ ] Existing happy-path test (`test_websocket_echoes_message_with_valid_token`) still passes
  - [ ] `user_id` appears in server-side log entries

All five SEC-005..009 are Sprint 2 retrofit tickets that fill security gaps in already-merged code (auth enforcement, secret validation, rate limiting, compose hardening, WebSocket enforcement). They share the `security` and `phase-3` labels and are owned end-to-end by **Person A (Scott)** — the work spans the shared package, API middleware, compose configuration, and WebSocket routing, all of which fall under Scott's infra/shared remit. SEC-008 is the only inter-ticket dependency: it requires SEC-006 to land first so the `ENVIRONMENT=production` flag has a validator to trip. ADR-33 in `decisions.md` is the architectural source of truth for the rationale and threat model behind these tickets.

#### SEC-010: Security headers middleware (CUAI-86)
- **Points**: 2
- **Phase**: 3 / Sprint 3
- **Blocked by**: Nothing
- **Assignee**: Person C (Andrew)
- **Labels**: `security`, `phase-3`
- **Status**: 📋 Planned
- **Description**: Add a security headers middleware to both FastAPI services (`course-search-api/main.py` and `chat-service/main.py`). Headers: `Content-Security-Policy: default-src 'self'`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Strict-Transport-Security` (production only, gated on `ENVIRONMENT` env var). The architecture doc already lists these headers as planned (line 1262) — this ticket implements them. DOMPurify on the frontend already handles XSS sanitization; these headers add defense-in-depth at the browser level.
- **Acceptance criteria**:
  - [ ] Both services return all five security headers on every response
  - [ ] HSTS header only present when `ENVIRONMENT=production`
  - [ ] Existing tests still pass
  - [ ] New test verifies headers are present on a sample response

---

## Epic 10: GCP Deployment

> Owner: Person A | Phase: 4

### DEPLOY-001: Terraform — VPC + networking
- **Points**: 5
- **Phase**: 4 (Day 20)
- **Blocked by**: Nothing (infrastructure only)
- **Assignee**: Person A
- **Status**: 📋 Planned
- **Description**: Create `infra/network.tf`. VPC, private subnet (10.0.0.0/24), Network Firewall Policy (`cu-assistant-fw-policy`) containing 4 rules (allow-vpc-connector @ priority 1000, allow-internal @ 1100, allow-iap-ssh @ 1200, default-deny @ 65534) attached via `google_compute_network_firewall_policy_association`, Serverless VPC Connector. Create `infra/main.tf` (provider, GCS backend), `infra/variables.tf`, `infra/outputs.tf`, `infra/terraform.tfvars.example`, `infra/infra.sh` (local test harness: `./infra.sh plan|up|down`).
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
- **Status**: 📋 Planned
- **Description**: Create `infra/data-vm.tf`. e2-medium Compute Engine VM. Startup script installs Docker Compose, starts PostgreSQL + Neo4j + Redis. Persistent disk for data. Static internal IP (10.0.0.10). Create `infra/scripts/data-vm-startup.sh`.
- **Acceptance criteria**:
  - [ ] VM boots and runs startup script
  - [ ] `gcloud compute ssh data-services --tunnel-through-iap` works
  - [ ] PostgreSQL, Neo4j, Redis accessible from within VPC
  - [ ] Data persists across VM stop/start (persistent disk)
  - [ ] *(security ADR-33)* VM deploys the compose stack using the `docker-compose.prod.yml` override from SEC-008.
  - [ ] *(security ADR-33)* All required secrets (`JWT_SECRET_KEY`, `NEO4J_PASSWORD`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`) pulled from GCP Secret Manager at boot, never committed to Terraform state.
  - [ ] *(security ADR-33)* Firewall rules block ingress to 5432/6379/7474/7687/11434 from anywhere except the VPC connector.

### DEPLOY-003: Terraform — Ollama MIG + auto-scaling
- **Points**: 5
- **Phase**: 4 (Day 21)
- **Blocked by**: DEPLOY-001, DEPLOY-002 (needs Redis for queue)
- **Assignee**: Person A
- **Status**: ❌ Cancelled

**Status: Cancelled** — GPU VM infrastructure eliminated by migration to Anthropic API (CUAI-87). Ollama for embeddings runs on the data-services VM; no separate MIG needed.

- **Description**: ~~Build a custom GCE image (via Packer) with Docker, NVIDIA drivers, Ollama, and models (`gpt-oss:20b`, `nomic-embed-text`) pre-installed. Create `infra/packer/ollama-worker.pkr.hcl`. Create `infra/ollama-mig.tf` — instance template (spot g2-standard-4, L4 GPU, boots from custom image), MIG with min 0 / max 3, autoscaler on custom metric (Redis queue depth). Create `infra/monitoring.tf` (custom metric definition). Create `infra/scripts/ollama-worker-startup.sh` (lightweight — starts Redis queue worker only, no provisioning) and `infra/scripts/queue-depth-exporter.py`.~~
- **Acceptance criteria** (N/A — cancelled):
  - ~~[ ] Custom GCE image built with gpt-oss:20b and nomic-embed-text pre-loaded~~
  - ~~[ ] Packer template (`infra/packer/ollama-worker.pkr.hcl`) exists and is documented~~
  - ~~[ ] Instance template references custom image family, creates with GPU~~
  - ~~[ ] MIG starts with target_size 0~~
  - ~~[ ] Manual resize to 1 boots a GPU worker ready to serve (no model download)~~
  - ~~[ ] Worker pulls inference requests from Redis queue~~
  - ~~[ ] queue-depth-exporter publishes metric to Cloud Monitoring~~
  - ~~[ ] Autoscaler responds to metric changes~~

### DEPLOY-004: Terraform — Cloud Run services
- **Points**: 3
- **Phase**: 4 (Day 21-22)
- **Blocked by**: DEPLOY-001, DEPLOY-005 (Artifact Registry)
- **Assignee**: Person A
- **Status**: 📋 Planned
- **Description**: Create `infra/cloud-run.tf`. 3 Cloud Run services (course-search-api, chat-service, frontend). VPC connector attached. Env vars from Terraform. Chat service has min_instances=1. Create `infra/iam.tf` (service accounts).
- **Acceptance criteria**:
  - [ ] All 3 Cloud Run services deploy
  - [ ] Services can reach data VM (PostgreSQL, Neo4j, Redis) via VPC
  - [ ] Chat service has min_instances=1
  - [ ] CORS_ORIGINS set to frontend Cloud Run URL
  - [ ] Health endpoints return 200
  - [ ] `frontend_url` exported from `infra/outputs.tf` (using `google_cloud_run_v2_service.frontend.uri`) so `./infra.sh status` prints the deployed `*.run.app` URL. Chat and API URLs are intentionally *not* exported — those services use `ingress = "internal-and-cloud-load-balancing"` and aren't meant to be hit directly.
  - [ ] *(security ADR-33)* Cloud Run services have `ingress = "all"` only for the Course Search API (public login/register); Chat Service is `ingress = "internal-and-cloud-load-balancing"` if a BFF fronts it — otherwise document why public is acceptable.
  - [ ] *(security ADR-33)* Service env vars sourced from Secret Manager, not inline plaintext.
  - [ ] *(security ADR-33)* `ENVIRONMENT=production` env var set on both services (triggers the SEC-006 validator).

### DEPLOY-005: Artifact Registry
- **Points**: 1
- **Phase**: 4 (Day 20)
- **Blocked by**: DEPLOY-001
- **Assignee**: Person A
- **Status**: 📋 Planned
- **Description**: Create `infra/artifact-registry.tf`. Docker repository for container images.
- **Acceptance criteria**:
  - [ ] Registry created
  - [ ] Docker images can be pushed to it

### DEPLOY-006: Data ingestion on GCP
- **Points**: 2
- **Phase**: 4 (Day 22)
- **Blocked by**: DEPLOY-002, DATA-005
- **Assignee**: Person A
- **Status**: 📋 Planned
- **Description**: SSH to data VM via IAP tunnel with port forwarding. Run data ingestion against GCP databases. Verify data counts.
- **Acceptance criteria**:
  - [ ] All courses, programs, requirements in GCP databases
  - [ ] Embeddings generated and vector index created
  - [ ] Anthropic API key configured in Cloud Run environment variables
  - [ ] All validation counts match local

### DEPLOY-008: Prebaked Ollama Embed Image + Cloud Run Deployment
- **Points**: 3
- **Phase**: 4 (Day 21-22)
- **Blocked by**: DEPLOY-001, DEPLOY-005 (Artifact Registry)
- **Assignee**: Person A
- **Jira**: [CUAI-88](https://andrewcode8.atlassian.net/browse/CUAI-88)
- **Status**: 📋 Planned
- **Description**: Build a custom Docker image extending `ollama/ollama` with `nomic-embed-text` prebaked at build time. Deploy as a Cloud Run service with native autoscaling. Eliminates model download on cold start. See [ADR-42](../docs/decisions.md#adr-42-prebaked-ollama-embed-image-on-cloud-run).
- **Acceptance criteria**:
  - [ ] Custom Dockerfile bakes `nomic-embed-text` into the image at build time
  - [ ] Image builds in CI and pushes to Artifact Registry
  - [ ] Cloud Run service deployed behind VPC connector
  - [ ] Cloud Run autoscaling configured (min 0, max 3, concurrency 50)
  - [ ] Embedding endpoint accessible from chat-service and course-search-api
  - [ ] Health check endpoint configured
  - [ ] Terraform resource definitions in `infra/cloud-run.tf`
  - [ ] Startup time under 10s (no model download at runtime)

### DEPLOY-007: End-to-end GCP verification
- **Points**: 2
- **Phase**: 4 (Day 22-23)
- **Blocked by**: DEPLOY-004, DEPLOY-006
- **Assignee**: Person A
- **Status**: 📋 Planned
- **Description**: Test the full flow on GCP. Course search, chat with AI, auth, memory, decisions.
- **Acceptance criteria**:
  - [ ] Frontend loads at Cloud Run URL
  - [ ] Course search returns results
  - [ ] Chat connects via WebSocket (WSS)
  - [ ] AI responds with tool-retrieved data
  - [ ] Response time < 5s on GPU (vs 30s on CPU)

---

## Epic 11: CI/CD

> Owner: Person B | Phase: 1 (CICD-001), 4 (CICD-002)

### CICD-001: GitHub Actions CI pipeline
- **Points**: 2
- **Phase**: 1 (Day 2)
- **Blocked by**: Nothing
- **Blocks**: FE-001 merge (CI must be live before any feature PR lands, so we start with a green baseline)
- **Assignee**: Person B
- **Status**: ✅ Done (Sprint 1 — CUAI-71)
- **Description**: Create `.github/workflows/ci.yml`. Runs on every PR and push to main. Jobs: (1) Python — all commands run **from the repo root** so test discovery is workspace-wide: `uv sync`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy .`, `uv run pytest` (skip gracefully if no tests exist). Because pytest is invoked from the root, it auto-discovers every service's tests via `[tool.pytest.ini_options].testpaths` in the root `pyproject.toml` — **no `ci.yml` edits are needed when a new service is added**, contributors only update `[tool.uv.workspace].members` and `[tool.pytest.ini_options].testpaths` in the root `pyproject.toml`. (2) Frontend — `cd frontend && npm ci && npm run type-check && npm run lint && npm run test -- --run && npm run build`. (3) Terraform — `terraform fmt -check` + `terraform init -backend=false` + `terraform validate` against `infra/`. No `plan`/`apply` (those need GCP auth and would imply auto-deploy, which we deliberately don't do — see ADR notes on local-only provisioning). Just a syntax/type/reference guardrail. After this lands, enable branch protection on `main` requiring CI green before merge. See `docs/development-workflow.md § How CI Discovers Tests` for the canonical rule and maintenance guidance for future contributors.
- **Acceptance criteria**:
  - [x] CI runs on every PR targeting main and every push to main
  - [x] Python job runs ruff check, ruff format --check, mypy, and pytest
  - [x] Frontend job runs type-check, lint, vitest, and build
  - [x] Terraform job runs `fmt -check` + `validate` against `infra/` (no `plan`/`apply` — provisioning stays local via `infra/infra.sh`)
  - [x] Fails if any step fails
  - [x] Status check shown on PR page
  - [x] Branch protection on main requires CI green before merge
  - [x] Python job commands run from repo root (not from a service dir) so `uv run pytest` auto-discovers all workspace test directories
  - [x] Does NOT gate CI on scripts that need external services (e.g. `scripts/test_tool_calling.py` which needs an Anthropic API key) — those stay as manual QA
  - [x] Documented in `docs/development-workflow.md § How CI Discovers Tests` (this is the maintenance reference for future service additions)

### CICD-002: GitHub Actions deploy pipeline
- **Points**: 3
- **Phase**: 4 (Day 21-22)
- **Blocked by**: DEPLOY-004, DEPLOY-005
- **Assignee**: Person B
- **Status**: 📋 Planned
- **Description**: Create `.github/workflows/deploy.yml`. On push to main: build Docker images, push to Artifact Registry, deploy new revisions to Cloud Run.
- **Acceptance criteria**:
  - [ ] Pushing to main triggers build + deploy
  - [ ] All 3 images built and pushed
  - [ ] Cloud Run services updated with new revision
  - [ ] Deployment completes in < 10 minutes
  - [ ] *(security ADR-33)* GitHub Actions authenticates to GCP via Workload Identity Federation (OIDC), not a long-lived service account key in repo secrets.
  - [ ] *(security ADR-33)* Deploy step asserts `ENVIRONMENT=production` env is set on Cloud Run services.
  - [ ] *(security ADR-33)* Deploy fails if the deployed revision can boot with a default JWT secret (smoke test).

---

## Epic 12: Demo Prep

> Owner: Everyone | Phase: 4

### DEMO-001: Prompt engineering refinement
- **Points**: 5
- **Phase**: 3 (Sprint 3)
- **Blocked by**: CHAT-008 (LangGraph engine — now done)
- **Assignee**: Person C
- **Status**: 📋 Planned
- **Description**: Test 30+ conversation flows on the live system. Tune system prompt, tool descriptions, and response formatting. Document any model quirks and workarounds.
- **Acceptance criteria**:
  - **Response quality**
  - [ ] Responses are conversational, not encyclopedic
  - [ ] Model asks clarifying questions when intent is ambiguous
  - [ ] Tone is natural and student-friendly
  - **Tool usage**
  - [ ] Model proactively calls `get_student_profile` at conversation start
  - [ ] All recommended courses are tool-verified (no fabricated codes)
  - [ ] Grade minimum checks use tool data, not assumptions
  - [ ] Model offers `save_decision` after actionable recommendations
  - [ ] Proper tool chaining (e.g., profile -> requirements -> search)
  - **Planning logic**
  - [ ] Plans mix requirement categories (core + elective + gen-ed)
  - [ ] Semester availability is respected
  - [ ] Credit load awareness (warns on overload / underload)
  - [ ] Difficulty balancing across semesters
  - [ ] Prerequisite chains validated before recommending
  - [ ] Schedule conflict checks before finalizing
  - **Honesty**
  - [ ] Model admits data gaps rather than guessing
  - [ ] No hallucinated course data (codes, titles, credits)

### DEMO-002: Demo script + rehearsal
- **Points**: 3
- **Phase**: 4 (Day 23-24)
- **Blocked by**: DEMO-001
- **Assignee**: Everyone
- **Status**: 📋 Planned
- **Description**: Write a 10-minute demo script with 3-4 compelling scenarios. Practice the demo. Prepare backup plan (recorded video) in case of live issues.
- **Acceptance criteria**:
  - [ ] Demo script covers: course search, chat advising, prerequisite checking, schedule planning
  - [ ] Each team member knows their part
  - [ ] Demo rehearsed at least twice
  - [ ] Backup video recorded
  - [ ] Anthropic API connectivity verified before demo (no pre-warm needed)

### DEMO-003: Presentation slides
- **Points**: 3
- **Phase**: 4 (Day 23-24)
- **Blocked by**: Nothing
- **Assignee**: Everyone
- **Status**: 📋 Planned
- **Description**: Prepare presentation covering: problem statement, architecture diagram, tech stack decisions, demo, scaling strategy, security model, lessons learned.
- **Acceptance criteria**:
  - [ ] Slides cover all major architecture decisions
  - [ ] Architecture diagram is clean and readable
  - [ ] Demo is embedded in the presentation flow
  - [ ] Timing fits in allotted presentation window

---

## Story Dependency Graph

```
INFRA-001 (Andrew) ──→ INFRA-002 (Scott) ──→ INFRA-003 (Scott)
    │                       │                       │
    │                       │                       ├──→ API-001 ──→ API-002
    │                       │                       ├──→ API-003
    │                       │                       ├──→ API-004 ──→ AUTH-003
    │                       │                       ├──→ CHAT-001 ──→ FE-008
    │                       │                       └──→ CHAT-000 (LangGraph spike)
    │                       │
    │                       ├──→ DATA-001 ──→ DATA-003 ──→ DATA-005
    │                       │         │
    │                       │         └──→ DATA-004 ──→ DATA-005
    │                       │
    │                       ├──→ DATA-002 ──→ DATA-005
    │                       │
    │                       └──→ API-005 ──→ MEM-003
    │
    │  (Docker Compose provides data services)
    ├──→ DATA-004 (needs Ollama for embeddings)
    ├──→ DATA-006 (needs Anthropic API key)
    ├──→ CHAT-003 (needs Ollama for embeddings + Anthropic API key)
    └──→ CHAT-004 (needs Redis)

FE-001 ──→ FE-002 ──→ FE-003 ──→ FE-004
    │
    ├──→ FE-005
    │
    └──→ FE-006 ──→ FE-007 ──→ FE-008
              │
              └──→ FE-009

CHAT-002 + CHAT-003 ──→ CHAT-005 ──→ CHAT-006 ──┐
                              │                   ├──→ CHAT-008 ──→ CHAT-011
                     CHAT-007 ┘                   │
                     CHAT-010 ────────────────────┘
                                                  CHAT-008 ──→ SEC-001 ──→ SEC-004
                                                               SEC-002 ──→ SEC-004
                                                               SEC-003 ──→ SEC-004

INFRA-002 ──→ CHAT-009 ──→ CHAT-010
CHAT-002 ──→ CHAT-010

CHAT-004 ──→ MEM-001 ──→ MEM-002
CHAT-005 ──→ MEM-003
API-005 ──→ MEM-003

INFRA-002 ──→ AUTH-001
AUTH-001 ──→ AUTH-002
AUTH-001 ──→ AUTH-003
AUTH-002 ──→ AUTH-004

DEPLOY-001 ──→ DEPLOY-002 ──→ DEPLOY-006 (+ DATA-005) ──→ DEPLOY-007
    │
    ├──→ DEPLOY-005 ──→ DEPLOY-004 ──→ DEPLOY-007
    │         │
    │         └──→ DEPLOY-008 (prebaked embed image)
    │
    └──→ DEPLOY-004

DEPLOY-004 ──→ CICD-002
DEPLOY-005 ──→ CICD-002

CHAT-008 ──→ DEMO-001 ──→ DEMO-002
```

---

## Sprint Plan

### Sprint 1: Foundation (Days 1-5, Mar 25-29)
**Goal**: Full stack runs locally, data ingested, model validated.

| Story | Points | Assignee | Day |
|-------|--------|----------|-----|
| INFRA-001 | 3 | Person C (Andrew) | 1 |
| INFRA-002 | 5 | Person A (Scott) | 2-3 |
| INFRA-003 | 3 | Person A (Scott) | 3-4 |
| CICD-001 | 2 | Person B | 2 |
| FE-001 | 3 | Person B | 1-2 |
| FE-002 | 4 | Person B | 2-3 |
| FE-003 | 4 | Person B | 3-4 |
| FE-005 | 1 | Person B | 2 |
| FE-006 | 3 | Person B | 4 |
| FE-007 | 4 | Person B | 4-5 |
| FE-009 | 3 | Person B | 5 |
| DATA-001 | 5 | Person C | 1-3 |
| DATA-002 | 5 | Person C | 2-4 |
| DATA-003 | 5 | Person C | 2-4 |
| DATA-004 | 3 | Person C | 4-5 |
| DATA-005 | 2 | Person C | 5 |
| DATA-006 | 3 | Person B | 4-5 |
| CHAT-000 | 2 | Person C | 5-6 |
| **Total** | **62** | | |

**Per-person**: A (Scott)=8, B (Rohan)=29, C (Andrew)=25. Andrew bootstraps the repo skeleton on Day 1, then pivots to data ingestion (can start parsing logic in pure Python while Docker builds). Scott starts on shared package once the skeleton is merged. CHAT-000 spans into Day 6 (Sprint 2) but is timeboxed to 1 day.

### Sprint 2: Core Features (Days 6-12, Mar 30 - Apr 5)
**Goal**: Course search end-to-end. Chat with tool calling.

| Story | Points | Assignee | Day |
|-------|--------|----------|-----|
| API-001 | 4 | Person B | 6-7 |
| API-002 | 3 | Person B | 7 |
| API-003 | 3 | Person B | 7-8 |
| API-004 | 3 | Person B | 8 |
| API-005 | 4 | Person B | 8-9 |
| API-005b | 2 | Person B | Sprint 2 |
| FE-004 | 4 | Person B | 9-10 |
| FE-008 | 5 | Person B | 8-12 |
| CHAT-001 | 2 | Person C | 6-7 |
| CHAT-002 | 5 | Person C | 7-9 |
| CHAT-003 | 2 | Person C | 7-8 |
| CHAT-004 | 3 | Person C | 8-9 |
| CHAT-005 | 3 | Person C | 9-10 |
| CHAT-006 | 3 | Person C | 10 |
| CHAT-007 | 3 | Person C | 10-11 |
| CHAT-008 | 8 | Person C | 10-12 |
| CHAT-009 | 3 | Person C | 8 |
| CHAT-010 | 3 | Person C | 9-10 |
| CHAT-011 | 5 | Person B | 12-13 |
| SEC-005 | 3 | Person A | retrofit |
| SEC-006 | 2 | Person A | retrofit |
| SEC-007 | 3 | Person A | retrofit |
| SEC-008 | 3 | Person A | retrofit |
| SEC-009 | 3 | Person A | retrofit |
| **Total** | **80** | | |

**Per-person**: A=14, B=31, C=35. Person A's Sprint 2 load is the five SEC-005..009 retrofit tickets (added 2026-04-07 per ADR-33). They have no inter-dependencies except SEC-008 → SEC-006, and no external blockers — Scott has no in-progress tickets at the time of assignment. CHAT-011 may spill into Sprint 3.

### Sprint 3: Integration + Polish (Days 13-19, Apr 6-12)
**Goal**: Full local demo with auth, memory, security.

| Story | Points | Assignee | Day |
|-------|--------|----------|-----|
| AUTH-001 | 3 | Person B | 13 |
| AUTH-002 | 2 | Person B | 13 |
| AUTH-003 | 5 | Person B | 13-14 |
| AUTH-004 | 3 | Person B | 14 |
| MEM-001 | 3 | Person A | 13 |
| MEM-002 | 5 | Person A | 14-15 |
| MEM-003 | 3 | Person A | 15-16 |
| SEC-001 | 3 | Person C | 15 |
| SEC-002 | 2 | Person B | 16 |
| SEC-003 | 2 | Person B | 16-17 |
| SEC-004 | 5 | Person C | 17-18 |
| DEMO-001 | 5 | Person C | 18-19 |
| SEC-010 | 2 | Person C | 19 |
| **Total** | **43** | | |

**Per-person**: A=11, B=17, C=15. Person A (Scott) owns conversation memory. Person C (Andrew) focuses on security hardening + prompt tuning (DEMO-001 moved from Sprint 4 since its blocker CHAT-008 is now done). SEC-010 added for security headers middleware.

### Sprint 4: Deploy + Demo (Days 20-24, Apr 13-17)
**Goal**: Live on GCP, demo rehearsed.

| Story | Points | Assignee | Day |
|-------|--------|----------|-----|
| DEPLOY-001 | 5 | Person A | 20 |
| DEPLOY-002 | 3 | Person A | 20-21 |
| ~~DEPLOY-003~~ | ~~5~~ | ~~Person A~~ | ~~21~~ |
| DEPLOY-004 | 3 | Person A | 21-22 |
| DEPLOY-008 | 3 | Person A | 21-22 |
| DEPLOY-005 | 1 | Person A | 20 |
| DEPLOY-006 | 2 | Person A | 22 |
| DEPLOY-007 | 2 | Person A | 22-23 |
| CICD-002 | 3 | Person B | 21-22 |
| DEMO-002 | 3 | Everyone | 23-24 |
| DEMO-003 | 3 | Everyone | 23-24 |
| **Total** | **30** | | |

**Per-person**: A=21, B=3, C=0, Everyone=6. Person A heavy on Terraform. Person B lighter — can help with branding polish and bug fixes. DEMO-001 moved to Sprint 3.

---

## Summary

| Metric | Value |
|--------|-------|
| **Total stories** | 63 |
| **Total story points** | 211 |
| **Sprints** | 4 (5 + 7 + 7 + 5 days) |
| **Person A — Scott** | 54 pts, 17 stories — Shared Package, Wire Services, Docker verification, Terraform, GCP Deploy, Conversation Memory, SEC-005/006/007/008/009 (full ADR-33 retrofit) |
| **Person B — Rohan** | 78 pts, 24 stories — Frontend (visual shell anchored to `frontend/cu-classes.html` per ADR-31; functional filter set unchanged from original plan), Course Search API, Auth, CI/CD, CHAT-011, DATA-006, SEC-002/003 |
| **Person C — Andrew** | 73 pts, 20 stories — Repo skeleton, Data ingestion, Chat engine (LangGraph), Neo4j, Redis, Security (SEC-001/004), Demo |
| **Shared** | 6 pts, 2 stories — DEMO-002 (3), DEMO-003 (3) |
| **Cross-person blocks** | 12 (most front-loaded in Days 1-2 scaffolding, zero mid-sprint blocking) |
| **Critical path stories** | INFRA-001, INFRA-002, INFRA-003, DATA-001, DATA-002, DATA-006, CHAT-001, CHAT-008 |
| **Highest risk story** | CHAT-008 (LangGraph engine — 8 points, complex integration; de-risked by CHAT-000 spike) — ✅ Done |
| **Security stories** | 11 (SEC-001 through SEC-010 + CHAT-006) |
| **Sprint 2 retrofit (ADR-33)** | SEC-005..009 — 14 pts total, filing auth enforcement, secret validation, rate limiting, compose hardening, and WS hardening gaps |
