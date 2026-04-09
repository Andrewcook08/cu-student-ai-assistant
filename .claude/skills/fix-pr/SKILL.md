---
name: fix-pr
description: Fix all issues identified in a PR review comment. Checks out the PR branch, implements every fix, runs tests, and pushes.
argument-hint: <PR number>
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash Edit Write
---

**Fix all review issues on PR: $ARGUMENTS**

You are a senior engineer implementing fixes for every issue identified in a PR review. Your job is to fix everything — not partially, not "good enough" — every single issue gets resolved.

## Step 1: Load the review

Fetch the review comments on PR `$ARGUMENTS`:
```bash
gh api repos/{owner}/{repo}/issues/$ARGUMENTS/comments --jq '.[].body'
```

Parse out every numbered issue from the review comment(s). For each issue extract:
- **Issue number and title**
- **Severity** (Critical / High / Medium / Low / Info)
- **Category** (Defensive 4a-4f / Best Practice 5a-5e / AC Gap / Test Quality / Scope)
- **Gap description** — what's wrong
- **Fix** — the suggested code change

If there are multiple review comments (initial + follow-up), combine all issues into a single ordered list. Deduplicate — if the same issue appears in both an initial and follow-up comment, use the most detailed version.

**Info-severity items are documentation/awareness only — skip them unless they have a concrete code fix.**

## Step 2: Check out the PR branch

```bash
gh pr checkout $ARGUMENTS
```

Verify you're on the correct branch:
```bash
git branch --show-current
```

Pull latest to avoid conflicts:
```bash
git pull --rebase origin $(git branch --show-current)
```

## Step 3: Plan the fixes

Before writing any code, create a plan. Group issues by file to minimize context switching:

```
## Fix Plan for PR $ARGUMENTS

### File: <path>
- Issue #N: <what to change>
- Issue #M: <what to change>

### File: <path>
- Issue #K: <what to change>

### New files needed:
- <path>: <why>

### Tests to add/modify:
- <path>: <what tests>
```

**Ordering rules:**
1. Fix issues in dependency order — if issue #3's fix depends on issue #1's fix, do #1 first
2. Within a file, fix top-to-bottom to avoid line number drift
3. Do all production code fixes before test fixes
4. If two issues touch the same file, do them together to avoid re-reading

Present this plan and wait for confirmation before proceeding. If the user says "go" or confirms, proceed. If they want changes to the plan, adjust first.

## Step 4: Implement fixes

For each issue, in the planned order:

### Before fixing:
1. Read the file that needs to change (full context, not just the diff area)
2. Understand the surrounding code — don't break something else while fixing this issue
3. If the review comment includes a specific code fix, use it as a starting point but verify it's correct in context (review suggestions are sometimes simplified)

### While fixing:
1. Make the minimal change that resolves the issue — don't refactor surrounding code
2. If the fix requires adding an import, add it
3. If the fix requires a new constant, define it near related constants
4. If the fix requires a new function, place it near related functions
5. Match the existing code style exactly (indentation, naming, patterns)

### After fixing each issue:
1. Re-read the changed file to verify the fix is correct in context
2. Check that no other code in the file depends on the old behavior
3. If the fix changes a public interface (function signature, event shape, store action), grep for all callers and update them too

**Do NOT:**
- Add features beyond what the review requested
- Refactor code that wasn't flagged in the review
- Change formatting in lines you didn't need to touch
- Add comments explaining the fix (the fix should be self-evident; the review comment has the explanation)

## Step 5: Add or update tests

For each fix that changes behavior:

1. **If the review says "add a test"** — add the specific test described
2. **If the fix changes error handling** — add a test that triggers the error path and verifies the new behavior
3. **If the fix adds a guard/validation** — add a test that exercises the guard (both passing and failing cases)
4. **If the fix is purely internal** (e.g., adding try/catch that doesn't change external behavior) — verify existing tests still pass, no new test needed

**Test quality rules (from the review skill):**
- Assert specific values, not ranges (`assert status == 403`, not `assert status in (401, 403)`)
- Each failure mode gets its own test
- Test names describe the behavior, not the implementation

## Step 6: Verify everything works

Run the full test suite for each affected service:

**Python (backend):**
```bash
cd services/<service> && uv run pytest -x -q 2>&1 | tail -20
```

**Frontend:**
```bash
cd frontend && npx vitest run --reporter=verbose 2>&1 | tail -30
```

**Lint and type checks:**
```bash
# Python
cd services/<service> && uv run ruff check . && uv run ruff format --check . && uv run mypy .

# Frontend
cd frontend && npx vue-tsc --noEmit && npx eslint .
```

**If any test fails:**
1. Read the failure output carefully
2. Determine if the failure is from your fix (you broke something) or pre-existing
3. If your fix broke it — fix the fix, don't skip the test
4. If pre-existing — note it but don't fix unrelated failures in this PR

**If ruff format fails:** run `ruff format .` directly — don't hand-edit formatting.

## Step 7: Create the commit

Stage only the files you changed:
```bash
git add <file1> <file2> ...
```

**Never `git add .` or `git add -A`** — only add files you intentionally modified.

Write a commit message that references every issue fixed:

```bash
git commit -m "$(cat <<'COMMIT_EOF'
fix: address review feedback on PR #$ARGUMENTS

- <Issue #1 title>: <one-line summary of fix>
- <Issue #2 title>: <one-line summary of fix>
- ...

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
COMMIT_EOF
)"
```

## Step 8: Push and verify

```bash
git push origin $(git branch --show-current)
```

Wait for CI to start, then check status:
```bash
gh pr checks $ARGUMENTS --watch
```

If CI fails, diagnose and fix immediately — do not leave the PR with failing CI.

## Step 9: Post confirmation comment

After CI passes, post a comment on the PR confirming all fixes:

```bash
gh pr comment $ARGUMENTS --body "$(cat <<'EOF'
## Review Fixes Applied

All issues from the review have been addressed:

| # | Issue | Status | Commit |
|---|-------|--------|--------|
| 1 | <title> | Fixed | <short sha> |
| 2 | <title> | Fixed | <short sha> |
| ... | ... | ... | ... |

**Tests:** All passing (<N> total)
**CI:** Green
EOF
)"
```

## Important: Handle edge cases

- **If a fix requires backend AND frontend changes:** Make both changes in the same commit. Don't leave the contract broken between commits.
- **If a fix conflicts with another fix:** Resolve the conflict in favor of the higher-severity issue, then verify both are still addressed.
- **If the suggested fix in the review is wrong or incomplete:** Implement the correct fix that addresses the underlying issue described in the "Gap" section. The gap description is the requirement; the code suggestion is a hint.
- **If an issue is marked "Info" with no code fix:** Skip it — note "Info — no code change needed" in the confirmation table.
- **If you discover a NEW issue while fixing:** Fix it if it's in a file you're already changing and it's obvious (e.g., a typo, a missing import). Otherwise note it in the confirmation comment as "New issue found: ..." but don't fix it — that's scope creep for the current pass.
