---
name: review-pr
description: Deep review of a pull request for defensive coding, correctness, and production readiness. Use when asked to review a PR.
argument-hint: <PR number or CUAI-XX ticket key>
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash
---

**Review PR: $ARGUMENTS**

You are a staff engineer reviewing a pull request. Your job is to find every gap that could cause issues in production — not just style nits. Apply the same defensive rigor as our strongest merged code (CUAI-40 LangGraph engine).

## Step 1: Locate the PR

If `$ARGUMENTS` is a number, use it directly as the PR number.
If `$ARGUMENTS` is a ticket key (e.g., CUAI-51), find the PR:
```bash
gh pr list --search "$ARGUMENTS" --state all --json number,title,state,headRefName,url
```

Get the Jira ticket for context (acceptance criteria, description):
- Use Jira MCP tools to get the issue

## Step 2: Understand the full diff

```bash
gh pr diff <number> --name-only
gh pr diff <number>
```

Read every changed file in full context — don't just skim the diff. For each modified file, read the current version on the branch to understand the surrounding code.

Check CI status:
```bash
gh pr view <number> --json statusCheckRollup,mergeable,reviews
```

## Step 3: Understand the backend/frontend contract

If the PR touches frontend code that talks to a backend (or vice versa):
- Read the backend endpoint the frontend calls
- Read the frontend code that consumes the backend response
- Verify the types/schemas match on both sides

**Common contract mismatches to check:**
- Message types the frontend expects vs what the backend actually sends
- Error formats (does the backend send `type: "error"` or wrap errors in `type: "chat_response"`?)
- Fields the frontend renders that the backend never populates
- Auth token handling (where is it stored, how is it sent, what happens when it expires?)

## Step 4: Apply the defensive boundary checklist

For every external boundary in the changed code (network calls, WebSocket messages, user input, database queries, file I/O, JSON parsing, third-party API calls), verify ALL of the following:

### 4a. Try/catch at every external boundary
- [ ] Every `JSON.parse`, `json.loads`, or deserialization is wrapped in try/catch
- [ ] Every network call (fetch, WebSocket send/receive, HTTP request) has error handling
- [ ] Every database query has error handling
- [ ] No unhandled promise rejections or unhandled async exceptions
- [ ] Malformed input at any boundary cannot crash the handler or silently kill processing

**Anti-pattern to catch:** `JSON.parse(event.data)` without try/catch — a single malformed frame kills all future message processing.

### 4b. Graceful degradation — every failure has a plan
- [ ] When dependency X fails, the code either retries, falls back, or shows a clear user-facing error
- [ ] No silent failures — every caught exception either recovers, logs, or surfaces to the user
- [ ] Errors shown to users are for things that actually failed, not for states that haven't happened yet (e.g., don't show "auth failed" before the user has tried to authenticate)

**Anti-pattern to catch:** `connect()` called on mount before checking if auth token exists, showing "Authentication failed" before the user logs in.

### 4c. Never silently die — detect invisible failures
- [ ] Long-lived connections (WebSocket, SSE) have a heartbeat/ping mechanism to detect silent death
- [ ] Timeouts exist for every operation that could hang indefinitely
- [ ] If a connection dies silently, the user is informed and recovery is attempted

**Anti-pattern to catch:** WebSocket with `onclose` handler but no heartbeat — NAT timeout kills the connection, `onclose` never fires, UI shows "typing" forever.

### 4d. Input validation — don't trust the caller
- [ ] User input is validated before being processed or stored
- [ ] Empty/whitespace inputs are rejected at the boundary, not sent downstream
- [ ] Data from external sources (API responses, WebSocket messages, tool results) is validated against expected schema before use

**Anti-pattern to catch:** `send("")` adds a blank message to the store, sends it to the backend which ignores it — UI shows a message bubble that was never processed.

### 4e. Guard against runaway state
- [ ] Any list/array that grows over time has a cap or cleanup mechanism
- [ ] Loops that depend on external conditions have a max-iteration guard
- [ ] Recursive or re-entrant operations have guards against double-invocation

**Anti-pattern to catch:** `messages.push()` with no cap — hour-long sessions accumulate hundreds of messages in memory.

### 4f. Idempotent initialization — safe under re-entry
- [ ] Initialization functions guard against being called twice
- [ ] Component mount/unmount cycles can't create duplicate resources (connections, timers, listeners)
- [ ] Cleanup (unmount, disconnect, dispose) is thorough — no leaked timers, connections, or event listeners

**Anti-pattern to catch:** `connect()` with no guard — rapid mount/unmount creates two live WebSockets.

## Step 5: Best practices and conventions

Check the changed code against established best practices. These apply regardless of language or framework — they're about writing production-grade code.

### 5a. Security best practices
- [ ] No secrets, tokens, or credentials hardcoded or logged (check for `console.log(token)`, `logger.info(f"token={token}")`, etc.)
- [ ] Auth tokens are not exposed in URLs, logs, or error messages (query string tokens are a known P1 — flag if new instances are introduced)
- [ ] SQL/Cypher queries use parameterized values, never string interpolation
- [ ] User input is sanitized before being used in queries, rendered in HTML, or passed to shell commands
- [ ] CORS, CSP, and other security headers are not weakened by the change
- [ ] Dependencies added are pinned to a version range (not `*` or unpinned)
- [ ] No new OWASP Top 10 vulnerabilities introduced (injection, XSS, broken auth, etc.)

### 5b. API and interface design
- [ ] HTTP status codes are semantically correct (don't return 200 for errors, don't return 500 for validation failures)
- [ ] Error responses have consistent shape (`{"detail": "..."}` not mixed formats)
- [ ] New endpoints have appropriate rate limiting
- [ ] Breaking changes to existing APIs are flagged (changed response shapes, removed fields, new required params)
- [ ] WebSocket close codes are semantically correct and documented

### 5c. State management and data flow
- [ ] State is owned by one source of truth (not duplicated between store and component local state)
- [ ] Derived state is computed, not manually synced
- [ ] Side effects (API calls, WebSocket operations) are isolated from pure state updates
- [ ] Cleanup happens on every exit path (component unmount, connection close, error throw)
- [ ] No race conditions between async operations that modify shared state

### 5d. Code quality
- [ ] Functions do one thing — no 200-line functions mixing concerns
- [ ] Error messages are actionable for the user ("Please log in again" not "Error 4001")
- [ ] Magic numbers and strings are named constants with comments explaining why that value
- [ ] Public API surface is minimal — internal helpers are not exported
- [ ] Type safety is maintained — no `any` casts, no `type: ignore` without justification

### 5e. Project conventions (specific to this repo)

**Python:**
- [ ] Async for all functions that hit DB or external services
- [ ] Pydantic models for API request/response shapes
- [ ] `Depends()` for FastAPI dependency injection
- [ ] Parameterized queries only — no f-string SQL or Cypher
- [ ] ruff-compatible formatting (line length 100)
- [ ] Strict mypy compliance — no untyped functions in changed code

**Frontend (Vue/TypeScript):**
- [ ] Composition API with `<script setup lang="ts">`
- [ ] Pinia for state management — no component-local state for shared data
- [ ] Types in `src/types/index.ts`, composables in `src/composables/`, API clients in `src/services/`
- [ ] No `any` types without justification

**Auth:**
- [ ] Tool executor ALWAYS overrides `user_id` with the JWT value — never trust the LLM
- [ ] Both services validate the same JWT tokens via `shared/auth.py`

**Git/PR:**
- [ ] Commit messages reference Jira key
- [ ] No committed `.env`, `terraform.tfvars`, or `data/raw/*.json`

## Step 6: Verify acceptance criteria coverage

Compare every AC from the Jira ticket against the implementation:
- [ ] Each AC has corresponding code that implements it
- [ ] Each AC has a test that verifies it (or a lock-in test that prevents regression)
- [ ] Any AC marked as "lock-in" (e.g., "health endpoints remain public") has an explicit regression test

**If an AC is missing implementation or tests, flag it as a gap.**

## Step 7: Check test quality

- [ ] Tests cover happy path AND error/edge cases
- [ ] Tests assert specific values, not just "not error" (e.g., assert 403 specifically, not `in (401, 403)`)
- [ ] Each distinct failure mode has its own test (missing header vs invalid token vs expired token)
- [ ] Mocks/stubs are realistic — they match the actual API/interface they're replacing
- [ ] No unrelated test changes or test noise

## Step 8: Check for noise and scope creep

- [ ] Every changed file is relevant to the ticket
- [ ] No stray formatting changes to unrelated files
- [ ] No "while I'm here" refactors that aren't part of the ticket
- [ ] Comments in the code match the actual behavior (no stale TODOs or wrong descriptions)

## Step 9: Write the review

Post a single comment on the PR using `gh pr comment`. Structure it as:

```
## Code Review — <TICKET>: <title>

<1-2 sentence overall assessment>

---

### <N>. <Issue title> (<Severity>)

**Category:** <Defensive (4a-4f) / Best Practice (5a-5e) / AC Gap / Test Quality / Scope>

**Gap:** <what's missing and why it matters>

**Fix:**
<code example showing the specific fix>

---

<repeat for each issue>

### Summary

| # | Issue | Severity | Category |
|---|-------|----------|----------|
| 1 | ... | Critical/High/Medium/Low/Info | Defensive (4a-4f) / Best Practice (5a-5e) / AC Gap / Test Quality / Scope |

All items must be fixed before merge.
```

**Severity guide:**
- **Critical** — will cause bugs, data loss, or security issues in production
- **High** — will cause bad UX or silent failures that are hard to debug
- **Medium** — creates tech debt or fragility that will cause issues later
- **Low** — code quality, naming, stale comments
- **Info** — noting a design decision, not requesting a change

**If the PR is clean**, say so explicitly: "No issues found. This PR meets the defensive boundary standard." Don't invent issues to justify the review.
