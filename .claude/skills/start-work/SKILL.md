---
name: start-work
description: Load focused context for a Jira ticket before building. Reads only the relevant doc sections instead of everything.
argument-hint: <jira-key e.g. CUAI-20>
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash
---

**Load focused context for: $ARGUMENTS**

Do NOT start coding yet. Your job is to gather and present the right context so the next prompt can build efficiently.

## Step 1: Get the ticket from Jira

Use the Jira MCP tools to get the issue for `$ARGUMENTS`. Extract:
- Summary/title (contains the story ID like INFRA-002, CHAT-008, etc.)
- Description
- Status
- Blocked by / linked issues

From the summary, extract the **story ID prefix** (e.g., INFRA-, DATA-, CHAT-, API-, FE-, AUTH-, MEM-, SEC-, DEPLOY-, CICD-, DEMO-). This is used for doc routing in later steps.

## Step 2: Check blocker status

For each blocking/linked issue from Step 1, get its status via Jira MCP. Classify each as **Done** or **Blocking**.

## Step 3: Find story details in docs

Using the story ID from the Jira summary, grep `docs/jira-epics-and-stories.md` for it. Extract:
- Acceptance criteria
- Points and phase

## Step 4: Load relevant architecture sections

Use the routing table in [story-routing.md](story-routing.md) to determine which sections of `docs/architecture.md` are relevant based on the story ID prefix.

Read ONLY those sections from architecture.md. Do not read the entire file.

To extract a section, grep for the header and read from there to the next same-level header:
```bash
grep -n "^## " docs/architecture.md
```
Then use `sed` to extract the line range for each relevant section.

## Step 5: Load implementation guide context

Read the relevant phase and person section from `docs/implementation-guide.md`:
- Determine which phase this story belongs to (from the Jira doc)
- Determine which person owns it
- Read just that phase+person subsection

## Step 6: Check for related decisions

If the story references an ADR (e.g., "See ADR-6"), read just that ADR from `docs/decisions.md`.

## Step 7: Present context

Output a focused brief:
```
## $ARGUMENTS: <summary>
<description + acceptance criteria from docs>

## Blockers
<for each dependency: CUAI key, summary, status (Done/In Progress/To Do)>
<if any are not Done: "⚠️ BLOCKED — the following dependencies are not complete:">
<if all Done: "✅ All dependencies complete">

## Architecture context
<relevant sections, summarized to key specs the implementation needs>

## Implementation notes
<relevant guidance from the implementation guide>

## Key files to create/modify
<list the files this story touches based on the architecture doc>
```

## Step 8: Ensure correct branch

Run `git branch --show-current`. Check if a branch for this ticket exists:
1. Check local:
```bash
   git branch --list "*$ARGUMENTS*"
```
2. If not found locally, check remote:
```bash
   git fetch origin
   git branch -r --list "*$ARGUMENTS*"
```

**If any blockers are not Done AND no branch exists anywhere:**
Say: **"This story is blocked and hasn't been started. Resolve the dependencies above before starting."** and stop.

**If any blockers are not Done BUT a branch exists:**
Switch to the branch (checkout local, or checkout from remote if only there). Then:
1. Run `git log --oneline main..<branch> | head -20` to show work already done
2. Summarize what's been implemented vs what acceptance criteria remain
3. Say: **"This story is blocked but in progress on `<branch>`. Here's what's done so far and what's still waiting on dependencies. You may be able to work on the unblocked parts."**

**If all blockers are Done:**
If on `main` or a different story's branch:
1. Build the branch name: `feat/$ARGUMENTS-<short-description>`
2. If found on remote: `git checkout -b <branch> origin/<branch>`
3. If found locally: `git checkout <branch>`
4. Only if not found anywhere, create new: `git checkout -b <branch>`

Then say: **"Context loaded, on branch `<branch-name>`. Ready to build — describe what you want to start with or say 'go' to follow the implementation guide."**