---
name: start-work
description: Load focused context for a Jira story before building. Reads only the relevant doc sections instead of everything.
argument-hint: <story-id e.g. CHAT-008 or DATA-001>
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash
---

**Load focused context for story: $ARGUMENTS**

Do NOT start coding yet. Your job is to gather and present the right context so the next prompt can build efficiently.

## Step 1: Find the story

Grep `docs/jira-epics-and-stories.md` for `$ARGUMENTS`. Extract:
- Full story description
- Acceptance criteria
- Blocked by (dependencies) — note the story IDs of blockers
- Points and phase

If the story ID isn't found, tell the user and stop.

## Step 2: Check blocker status in Jira

For each blocking story ID found in Step 1:
1. Grep `docs/development-workflow.md` and `docs/jira-epics-and-stories.md` to find the CUAI-XX Jira key for each blocker
2. Query the Jira API for each blocker's status:
```bash
   curl -s -u "$JIRA_USER_EMAIL:$JIRA_API_TOKEN" \
     "$JIRA_BASE_URL/rest/api/3/issue/CUAI-XX?fields=status,summary" \
     | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['fields']['status']['name'], '-', d['fields']['summary'])"
```
3. Classify each blocker as **Done** or **Blocking**

If Jira credentials are not set or the API call fails, fall back to reporting the blockers from the docs without status and warn the user to verify manually.

## Step 3: Load relevant architecture sections

Use the routing table in [story-routing.md](story-routing.md) to determine which sections of `docs/architecture.md` are relevant for this story's prefix (DATA-, CHAT-, API-, FE-, etc.).

Read ONLY those sections from architecture.md. Do not read the entire file.

To extract a section, grep for the header and read from there to the next same-level header:
```bash
grep -n "^## " docs/architecture.md
```
Then use `sed` to extract the line range for each relevant section.

## Step 4: Load implementation guide context

Read the relevant phase and person section from `docs/implementation-guide.md`:
- Determine which phase this story belongs to (from the Jira doc)
- Determine which person owns it
- Read just that phase+person subsection

## Step 5: Check for related decisions

If the story references an ADR (e.g., "See ADR-6"), read just that ADR from `docs/decisions.md`.

## Step 6: Present context

Output a focused brief:
```
## Story: $ARGUMENTS
<story description + acceptance criteria>

## Blockers
<for each dependency: story ID, CUAI key, Jira status (Done/In Progress/To Do)>
<if any are not Done: "⚠️ BLOCKED — the following dependencies are not complete:">
<if all Done: "✅ All dependencies complete">

## Architecture context
<relevant sections, summarized to key specs the implementation needs>

## Implementation notes
<relevant guidance from the implementation guide>

## Key files to create/modify
<list the files this story touches based on the architecture doc>
```

## Step 7: Ensure correct branch

**If any blockers are not Done**, say: **"This story is blocked. Resolve the dependencies above before starting."** and stop.

If all clear, run `git branch --show-current`. If already on a feature branch for this story, continue.

If on `main` or a different story's branch:
1. Grep `docs/development-workflow.md` for `$ARGUMENTS` to find the CUAI-XX Jira key
2. Build the branch name: `feat/CUAI-XX-<short-description-from-story>`
3. Check if the branch exists locally:
```bash
   git branch --list "feat/CUAI-*$ARGUMENTS*" "feat/*<jira-key>*"
```
4. If not found locally, fetch and check remote:
```bash
   git fetch origin
   git branch -r --list "origin/feat/CUAI-*$ARGUMENTS*" "origin/feat/*<jira-key>*"
```
5. If found on remote, check it out locally:
```bash
   git checkout -b <branch-name> origin/<branch-name>
```
6. If found locally, switch to it:
```bash
   git checkout <branch-name>
```
7. Only if not found anywhere, create new:
```bash
   git checkout -b <branch-name>
```

Then say: **"Context loaded, on branch `<branch-name>`. Ready to build — describe what you want to start with or say 'go' to follow the implementation guide."**