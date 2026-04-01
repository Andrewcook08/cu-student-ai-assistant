# Development Workflow

> How the team works day-to-day: branching, PRs, testing, and Claude Code setup for each team member.

---

## Table of Contents
- [Branch Strategy](#branch-strategy)
- [Jira Automation](#jira-automation)
- [PR Workflow](#pr-workflow)
- [Testing Strategy](#testing-strategy)
- [Claude Code Setup — Shared](#claude-code-setup--shared)
- [Claude Code Setup — Person A (Infrastructure + Backend)](#claude-code-setup--person-a)
- [Claude Code Setup — Person B (Frontend)](#claude-code-setup--person-b)
- [Claude Code Setup — Person C (Data + AI)](#claude-code-setup--person-c)
- [Daily Workflow](#daily-workflow)
- [Handling Conflicts](#handling-conflicts)

---

## Branch Strategy

```
main (protected — CI must pass, requires 1 approval)
  │
  ├── feat/CUAI-45-uv-workspace           (Person A — INFRA-001)
  ├── feat/CUAI-46-shared-package          (Person A — INFRA-002)
  ├── feat/CUAI-52-course-ingestion        (Person C — DATA-001)
  ├── feat/CUAI-56-vue-setup               (Person B — FE-001)
  ├── feat/CUAI-39-course-listing          (Person A — API-001)
  ├── feat/CUAI-30-langgraph-engine        (Person C — CHAT-008)
  └── ...
```

**Rules:**
- Branch from `main`, PR back to `main`
- One branch per Jira story
- **Branch name must include the Jira key** (`CUAI-XX`) — this drives the automated Jira transitions (see [Jira Automation](#jira-automation))
- Keep branches short-lived (1-2 days max). Merge often.
- Pull `main` into your branch daily to avoid drift
- If two stories are tightly coupled (e.g., INFRA-002 + INFRA-003), they can share a branch — use the primary ticket's Jira key

**Branch naming**: `feat/CUAI-XX-short-description`
```bash
git checkout main && git pull
git checkout -b feat/CUAI-39-course-listing
```

> **Finding your Jira key**: Each story in Jira has a key like `CUAI-39`. The story ID from the docs (e.g., `API-001`) is in the ticket title. Use the `CUAI-XX` key in branch names, not the story ID.

---

## Jira Automation

A GitHub Actions workflow (`.github/workflows/jira-sync.yml`) automatically syncs PR status to Jira. No manual Jira updates needed — just follow the branching convention.

### How It Works

| GitHub Event | Jira Transition | What Happens |
|-------------|----------------|--------------|
| PR **opened** targeting `main` | **To Do → In Progress** | Ticket moves to "In Progress", comment added with PR link |
| **Reviewer manually added** to PR | **In Progress → In Review** | Ticket moves to "In Review" |
| PR **merged** to `main` | **In Review → Done** | Ticket moves to "Done", comment added with merge details |

> **Important**: The "In Review" transition requires you to **manually add a reviewer** to the PR (via GitHub UI or `gh pr edit --add-reviewer`). Branch protection rules that require reviews do NOT trigger this — they only block merging until someone approves. You must explicitly request a review.

### Requirements

1. **Branch name must contain `CUAI-XX`** — the workflow extracts this to find the Jira ticket
2. **GitHub Secrets** must be configured (repo Settings → Secrets → Actions):

| Secret | Value |
|--------|-------|
| `JIRA_USER_EMAIL` | Your Atlassian account email |
| `JIRA_API_TOKEN` | Generate at https://id.atlassian.com/manage-profile/security/api-tokens |

### Example Flow

```
1. git checkout -b feat/CUAI-39-course-listing    # Start work
2. # ... write code, commit, push ...
3. gh pr create --title "CUAI-39: Course listing"  # → Jira: In Progress
4. gh pr edit --add-reviewer teammate              # → Jira: In Review (manual step!)
5. # ... reviewer approves ...
6. gh pr merge --squash                            # → Jira: Done
```

### What About CI Checks?

The CI pipeline (lint, format, typecheck, tests) is **not implemented yet** — that's CUAI-71 in Sprint 4. Until then, run checks locally before pushing:
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

### If a PR Has No Jira Key

Branches without `CUAI-XX` in the name are silently skipped — no Jira transition, no error. Use this for non-ticket work like docs-only or config changes.

---

## PR Workflow

### Creating a PR

```bash
# Make sure your branch is up to date with main
git fetch origin && git rebase origin/main

# Push
git push -u origin feat/CUAI-39-course-listing

# Create PR (use gh CLI or GitHub UI)
# Include Jira key in title for traceability
gh pr create --title "CUAI-39: Course listing endpoint with filters" --body "..."
```

### PR Requirements

Before a PR can merge:
1. **CI passes** — ruff check, ruff format, mypy, pytest (automated via GitHub Actions)
2. **1 approval** from another team member
3. **No merge conflicts** with main

### PR Review

Keep reviews fast (< 24 hours). Focus on:
- Does it match the architecture doc?
- Does it break anything for another person's work?
- Are there tests for the critical parts?

Don't block on:
- Style (ruff handles this)
- Type issues (mypy handles this)
- Minor naming preferences

### Merging

Squash merge to keep `main` history clean:
```bash
gh pr merge --squash
```

---

## Testing Strategy

**Philosophy: test the boundaries, not everything.**

### What to Test

| Category | Why | Examples |
|----------|-----|---------|
| **Tools + tool executor** | Contract between LLM and data. Wrong shape = broken chat. | `test_tools.py`: each tool returns expected dict shape |
| **Auth** | Security bugs are expensive. | `test_auth.py`: JWT create/decode, password hash, user_id override |
| **Prerequisite parser** | Regex over messy data. Edge cases will bite you. | `test_prerequisites.py`: all 5 patterns, typos, edge cases |
| **API endpoints** | Catch 500s before they hit the frontend. | `test_courses.py`: filters, pagination, 404s, auth |
| **Security** | Injection attempts, rate limiting, output validation. | `test_security.py`: prompt injection, tool abuse, PII scanning |

### What NOT to Test

| Category | Why |
|----------|-----|
| SQLAlchemy models | Trust the ORM. If the schema is wrong, ingestion fails obviously. |
| Pydantic schemas | Trust the library. Invalid data raises ValidationError. |
| Config loading | pydantic-settings is well-tested. |
| Frontend components | Test visually. Automated component tests are slow to write and brittle. |
| LangGraph wiring | Integration-test by running the chat. Unit-testing state machines is painful. |

### When to Write Tests

**Not TDD. Test before merge.**

1. Write the code
2. Get it working manually (curl, browser, Neo4j browser)
3. Write tests for the categories above
4. Run `uv run pytest -x -v` before pushing
5. CI runs the full suite on PR

### Running Tests

```bash
# All tests
uv run pytest

# One service
uv run pytest services/course-search-api/tests/ -v
uv run pytest services/chat-service/tests/ -v

# One file
uv run pytest services/chat-service/tests/test_tools.py -v

# Stop on first failure
uv run pytest -x

# Full CI check
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```

---

## Claude Code Setup — Shared

### What Everyone Gets Automatically

The `CLAUDE.md` at the repo root is read by Claude Code on every session. It contains:
- Project structure and tech stack
- All commands (uv, docker, etc.)
- Code conventions (Python, frontend, auth, testing, git)
- Environment variable reference

**No one needs to manually explain the project to Claude Code.** It reads `CLAUDE.md` on startup.

### Install Claude Code

```bash
# Install (everyone)
npm install -g @anthropic-ai/claude-code

# Navigate to the repo
cd cu-student-ai-assistant

# Start Claude Code
claude
```

### First Session Setup (Everyone)

On the first run, Claude Code will read `CLAUDE.md` and understand the project. Run these to verify your local environment:

```bash
# In Claude Code, ask:
# "Verify my local environment is set up correctly"
# It will check: uv, docker, node, .env file, database connectivity
```

### Shared Principles for Prompting Claude Code

1. **Reference the story ID**: "Implement API-001: course listing endpoint with filters"
2. **Point to the architecture**: "Follow the API spec in docs/architecture.md"
3. **Specify the file**: "Edit services/course-search-api/app/routes/courses.py"
4. **Ask for tests after code**: "Now write tests for the endpoint in tests/test_courses.py"
5. **Run checks before committing**: "Run ruff check, ruff format, mypy, and pytest"

---

## Claude Code Setup — Person A

> **Role**: Infrastructure, Backend (Course Search API), Docker, Terraform
> **Works in**: `shared/`, `services/course-search-api/`, `docker-compose.yml`, `infra/`, `.github/`

### Recommended Workflow

Person A's work is the most foundational — others depend on it. Speed matters in Phase 1.

**Typical session:**
```
You: Implement INFRA-002: Create the shared Python package.
     Follow the implementation guide in docs/implementation-guide.md,
     Phase 1, Person A, step 2. Create all files listed there:
     config.py, database.py, models.py, auth.py, schemas.py.

You: Now run uv sync and make sure it works.

You: Write tests for auth.py — JWT create/decode, password hash/verify.

You: Run the full check suite: ruff check, format, mypy, pytest.

You: Commit and push to feat/INFRA-002-shared-package.
```

**Phase-by-phase focus:**

| Phase | Person A Focus | Key Prompt Patterns |
|-------|---------------|-------------------|
| 1 | Scaffolding, Docker, shared package | "Create [file] following the implementation guide" |
| 2 | Course Search API endpoints | "Implement GET /api/courses with filters. Use SQLAlchemy queries against the Course model. Follow the pagination convention in the implementation guide." |
| 3 | Auth endpoints, student profile, decisions | "Implement POST /api/auth/register. Hash password with shared/auth.py. Return JWT." |
| 4 | Terraform, GCP deployment | "Create infra/network.tf following the architecture doc Network Security section." |

**Tips for Person A:**
- When creating API endpoints, tell Claude Code to use `Depends(get_db)` and `Depends(get_current_user)` from `dependencies.py`
- Always ask Claude Code to run `uv run ruff check . && uv run mypy .` after writing code — catches issues before PR
- For Terraform: paste the relevant HCL snippets from `architecture.md` and say "implement this in infra/[file].tf"

---

## Claude Code Setup — Person B

> **Role**: Frontend (Vue + TypeScript)
> **Works in**: `frontend/`

### Recommended Workflow

Person B works mostly independently in `frontend/`. Rarely touches Python.

**Typical session:**
```
You: Implement FE-003: Course table and detail panel.
     Create CourseTable.vue, CourseRow.vue, and CourseDetail.vue
     in frontend/src/components/course-search/.
     Use mock data from frontend/src/mocks/courses.ts for now.
     Style with Tailwind using CU branding (cu-gold, cu-black).

You: Now open http://localhost:5173 and verify it looks right.
     [paste a screenshot if needed]

You: Implement FE-008: WebSocket integration with useChat composable.
     Follow the WebSocket protocol defined in docs/implementation-guide.md
     Phase 2, Person B section. Include auto-reconnect with exponential
     backoff.
```

**Phase-by-phase focus:**

| Phase | Person B Focus | Key Prompt Patterns |
|-------|---------------|-------------------|
| 1 | Vue setup, layout, mock components | "Create [Component].vue with Tailwind styling. Use mock data." |
| 2 | WebSocket integration, API wiring | "Create useChat.ts composable. Connect to ws://localhost:8001/ws/chat/{sessionId}." |
| 3 | Auth UI, structured responses | "Create LoginModal.vue. On submit, POST to /api/auth/login, store JWT in localStorage." |
| 4 | CI/CD, branding polish | "Create .github/workflows/ci.yml that runs lint, format, typecheck, and tests on PR." |

**Tips for Person B:**
- Tell Claude Code the exact Tailwind colors: "Use bg-cu-black text-cu-gold for the header"
- For composables, reference the WebSocket protocol types from `src/types/index.ts`
- When wiring API calls, say "Use the Vite proxy — call /api/courses, not http://localhost:8000/api/courses"
- Frontend has no automated tests — verify visually. Ask Claude Code "does this component handle the loading state and error state?"

### Node Commands (for Claude Code context)

```bash
cd frontend
npm install              # Install deps
npm run dev              # Dev server on :5173
npm run build            # Production build
npm run type-check       # TypeScript check
```

---

## Claude Code Setup — Person C

> **Role**: Data Ingestion, AI/Chat Engine (LangGraph, tools, Neo4j, Redis)
> **Works in**: `data/`, `services/chat-service/`

### Recommended Workflow

Person C has the most complex work — data parsing, LLM integration, graph queries, tool calling. Break tasks into small pieces.

**Typical session:**
```
You: Implement DATA-003: Prerequisite regex parser.
     Read the prerequisite parsing section in docs/architecture.md
     for the patterns and counts. Write data/ingest/parse_prerequisites.py.
     Handle: single prereq, OR alternatives, AND requirements,
     corequisites, restrictions. Store raw_text on every edge.

You: Write tests for the parser. Test all 5 patterns plus edge cases:
     typos ("prerequsite"), missing parentheses, combined AND+OR.
     Put tests in data/tests/test_prerequisites.py.

You: Run it against the real data. How many courses parsed successfully
     out of the 2,830 with prerequisites?
```

**For LangGraph (the hardest part):**
```
You: Implement CHAT-008: LangGraph conversation engine.
     Read the LangGraph docs for the ReAct agent pattern.
     The state machine is: classify_intent → build_context →
     call_llm → maybe_call_tools (loop) → validate_output → respond.
     Tools are already defined in core/tools.py.
     Start with a minimal version: just call_llm → maybe_call_tools → respond.
     Skip intent classification and memory for now — add those later.
```

**Phase-by-phase focus:**

| Phase | Person C Focus | Key Prompt Patterns |
|-------|---------------|-------------------|
| 1 | JSON parsing, DB writes, embeddings, model validation | "Parse cu_classes.json. The structure is {dept: {course_code: {fields}}}. Write to PostgreSQL and Neo4j." |
| 2 | Neo4j queries, tools, LangGraph engine, Redis queue | "Write a Cypher query that traverses the prerequisite chain for a course. Use variable-length paths." |
| 3 | Memory, system prompt, security | "Implement two-tier memory. Store last 20 messages in Redis. When over 20, summarize with the LLM." |
| 4 | Prompt tuning, demo prep | "Test these 10 conversation scenarios and tell me which ones fail. Adjust the system prompt." |

**Tips for Person C:**
- For Neo4j Cypher queries, always tell Claude Code to use parameterized queries: "Use $code not f-strings"
- For LangGraph, build incrementally: get one tool call working before adding all 6
- For the Redis queue, start with the simple pattern: LPUSH to enqueue, BRPOP to dequeue, pub/sub for results
- When testing tool calling, use `scripts/test_tool_calling.py` — run it after any tool description changes
- The tool executor retry logic is critical — make sure Claude Code implements the "retry once on ValidationError" pattern

### Debugging LLM Issues

When the LLM misbehaves (wrong tool, bad params, hallucination):
```
You: The LLM is calling search_courses when asked about prerequisites.
     Read the tool docstrings in core/tools.py. The docstring for
     check_prerequisites should clearly say "Use when a student asks
     about requirements for a SPECIFIC course." Adjust the docstring
     to be more distinct from search_courses.

You: The LLM is generating malformed JSON for tool parameters.
     Show me the last 5 tool calls from the audit log.
     [Then adjust tool schemas or switch models]
```

---

## Daily Workflow

### Morning (5 min)

```bash
# Pull latest main
git checkout main && git pull

# Switch to your feature branch and rebase
git checkout feat/YOUR-STORY
git rebase origin/main

# Start services if not running
docker compose up -d postgres neo4j redis ollama

# Start Claude Code
claude
```

### Working (during the day)

```
1. Tell Claude Code which story you're working on
2. Point it to the implementation guide for detailed instructions
3. Let it write code
4. Ask it to run checks: ruff, mypy, pytest
5. Review the diff before committing
6. Commit with story ID: "API-001: Add course listing endpoint with filters"
7. Push and create PR when the story is complete
```

### Before Creating a PR (5 min)

```bash
# Make sure everything passes
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest

# Check for accidental .env or secret commits
git diff --cached --name-only | grep -E '\.env$|tfvars$|\.json$'
```

### End of Day

```bash
# Push your branch even if not done (backup)
git push

# Stop services if not needed overnight
docker compose down
```

---

## Handling Conflicts

### When Multiple People Touch the Same File

The most likely conflict zones:
- `shared/shared/models.py` — Person A (schema) + Person C (new models)
- `shared/shared/schemas.py` — Person A (API schemas) + Person C (chat schemas)
- `docker-compose.yml` — Person A (services) + Person C (new containers)

**Prevention**: Communicate when you're about to modify a shared file. Keep changes to shared files in small, focused PRs that merge fast.

**Resolution**: If you hit a merge conflict:
```
You: I have a merge conflict in shared/shared/models.py after rebasing.
     Show me the conflict markers and help me resolve it.
     Keep both sets of changes — Person A added the User model
     and I added the ToolAuditLog model.
```

### When Person C Is Blocked on Person A

If Person A's scaffolding isn't ready and Person C needs to start:
```bash
# Person C: write parsing logic in pure Python (no DB needed)
# Test with: python -c "from data.ingest.ingest_courses import parse_course; ..."

# Or: create a temporary branch from Person A's WIP branch
git fetch origin
git checkout -b feat/DATA-001-course-ingestion origin/feat/INFRA-002-shared-package
```
