---
name: verify-pr
description: Re-review a PR after fixes have been pushed. Loads the original review, checks every issue was resolved, and either approves or flags remaining gaps.
argument-hint: <PR number>
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash
---

**Verify fixes on PR: $ARGUMENTS**

You are a staff engineer doing a second-pass review. A review was posted, fixes were pushed — your job is to verify every single issue was properly resolved. No rubber-stamping.

## Step 1: Load the original review

Fetch all comments on PR `$ARGUMENTS`:
```bash
gh api repos/{owner}/{repo}/issues/$ARGUMENTS/comments --jq '.[].body'
```

Parse every numbered issue from the review comment(s). Build a checklist:

```
| # | Issue | Severity | Category | Expected Fix |
|---|-------|----------|----------|--------------|
| 1 | ... | ... | ... | <what the review said to do> |
| 2 | ... | ... | ... | ... |
```

Include issues from ALL review comments (initial, follow-up, defensive boundary review). Deduplicate by issue content, keeping the most detailed version.

## Step 2: Get the new changes

Find what was pushed since the review:
```bash
gh pr diff $ARGUMENTS --name-only
gh pr diff $ARGUMENTS
```

Also check the commits pushed after the review comments:
```bash
gh pr view $ARGUMENTS --json commits --jq '.commits[-5:] | .[] | "\(.oid[:7]) \(.messageHeadline)"'
```

Check CI status:
```bash
gh pr view $ARGUMENTS --json statusCheckRollup,mergeable
```

## Step 3: Verify each issue — one by one

For EACH issue from the original review, do ALL of the following:

### 3a. Find the fix

- Search the diff for changes that address this specific issue
- If the fix isn't obvious in the diff, read the full file to check if it was addressed differently than suggested
- If you can't find any change related to this issue, mark it as **NOT FIXED**

### 3b. Verify the fix is correct

Don't just check "was code added" — verify the fix actually solves the problem:

- **Try/catch added?** → Does it catch the right exception type? Does it handle the error properly (not just swallow it)?
- **Guard added?** → Does it guard against the right condition? Is the early return correct?
- **Validation added?** → Does it validate the right field? Does it reject the right inputs?
- **Test added?** → Does the test actually exercise the fix? Would the test have failed before the fix?
- **Lock-in test added?** → Does it assert the specific value, not a range? Would it catch a regression?

### 3c. Check for regressions

- Did the fix break any existing functionality?
- Did the fix change a public interface that other code depends on? Were all callers updated?
- Did the fix introduce a new issue that wasn't in the original review?

### 3d. Rate the fix

For each issue, assign one of:
- **FIXED** — issue is fully resolved, fix is correct
- **PARTIALLY FIXED** — attempt was made but the fix is incomplete or has a gap
- **NOT FIXED** — no change addressing this issue, or the change doesn't solve the problem
- **INCORRECTLY FIXED** — a change was made but it introduces a new problem or doesn't address the root cause
- **SKIPPED (Info)** — issue was Info severity with no code change needed

## Step 4: Run the defensive boundary checklist on the NEW code

Don't just verify the review issues — re-run the defensive checks on the current state of the code. Fixes sometimes introduce new gaps:

- [ ] Did a try/catch fix accidentally swallow an error that should propagate?
- [ ] Did a guard/validation fix create a new code path that's untested?
- [ ] Did a new constant/import get added but not used, or used incorrectly?
- [ ] Did a test fix test the mock instead of the actual behavior?
- [ ] Does the fix match the existing code style (indentation, naming, patterns)?

## Step 5: Check test results

Verify all tests pass on the latest commit:
```bash
gh pr checks $ARGUMENTS
```

If CI is not green, this is an automatic blocker — report it.

## Step 6: Write the verification result

Post a comment on the PR using `gh pr comment`. Use one of two formats:

### If ALL Critical/High/Medium issues are fixed:

```
## Re-Review — All Issues Resolved

Verified every issue from the original review against the latest changes.

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | <title> | Critical | FIXED — <one-line description of how> |
| 2 | <title> | High | FIXED — <one-line description of how> |
| 3 | <title> | Low | FIXED — <one-line description of how> |
| 4 | <title> | Info | SKIPPED — no code change needed |

**CI:** Green
**Tests:** All passing
**Verdict:** Ready to merge.
```

### If ANY Critical/High/Medium issues remain:

```
## Re-Review — Issues Remaining

Verified every issue from the original review. **<N> issues are not yet resolved.**

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | <title> | Critical | NOT FIXED — <what's still wrong> |
| 2 | <title> | High | PARTIALLY FIXED — <what's missing> |
| 3 | <title> | Medium | FIXED — <one-line description> |
| 4 | <title> | Low | FIXED — <one-line description> |

### Remaining issues requiring changes:

#### Issue #1: <title> (Critical) — NOT FIXED

**Original problem:** <from the review>

**Current state:** <what the code looks like now>

**What's still needed:**
<specific code change required>

---

<repeat for each unresolved issue>

**CI:** <Green/Red>
**Tests:** <passing count>
**Verdict:** Not ready to merge. <N> issues remaining.
```

## Rules

- **Be strict on Critical and High.** These must be fully resolved — no "close enough."
- **Be reasonable on Low.** If the spirit of the fix is right even if the approach differs from the suggestion, mark it FIXED.
- **Don't invent new issues.** This pass is about verifying the existing review, not finding new things. The only exception is if a fix introduced a NEW bug — flag that as "INCORRECTLY FIXED" with the regression described.
- **Check the actual code, not just the diff.** A diff can look right but be in the wrong location, missing context, or conflicting with nearby code.
- **If something was fixed differently than suggested but the underlying problem is solved**, mark it FIXED. The review's suggested fix was a hint, not a spec — the gap description is what matters.
