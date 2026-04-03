---
name: start-work
description: Load focused context for a Jira story before building. Reads only the relevant doc sections instead of everything.
argument-hint: <story-id e.g. CHAT-008 or DATA-001>
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash
---

**Load focused context for story: $ARGUMENTS**

Do NOT start coding yet. Your job is to gather and present the right context so the next prompt can build efficiently.

## Step 0: Check branch

Run `git branch --show-current`. If on `main`:
1. Grep `docs/development-workflow.md` for `$ARGUMENTS` to find the CUAI-XX Jira key
2. Build the branch name: `feat/CUAI-XX-<short description from story>`
3. Run `git checkout -b <branch name>`

If already on a feature branch, note it and continue.

## Step 1: Find the story

Grep `docs/jira-epics-and-stories.md` for `$ARGUMENTS`. Extract:
- Full story description
- Acceptance criteria
- Blocked by (dependencies)
- Points and phase

If the story ID isn't found, tell the user and stop.

## Step 2: Load relevant architecture sections

Use the routing table in [story-routing.md](story-routing.md) to determine which sections of `docs/architecture.md` are relevant for this story's prefix (DATA-, CHAT-, API-, FE-, etc.).

Read ONLY those sections from architecture.md. Do not read the entire file.

To extract a section, grep for the header and read from there to the next same-level header:
```bash
grep -n "^## " docs/architecture.md
```
Then use `sed` to extract the line range for each relevant section.

## Step 3: Load implementation guide context

Read the relevant phase and person section from `docs/implementation-guide.md`:
- Determine which phase this story belongs to (from the Jira doc)
- Determine which person owns it
- Read just that phase+person subsection

## Step 4: Check for related decisions

If the story references an ADR (e.g., "See ADR-6"), read just that ADR from `docs/decisions.md`.

## Step 5: Present context

Output a focused brief:

```
## Story: $ARGUMENTS
<story description + acceptance criteria>

## Blocked by
<dependency status - note which are done vs pending>

## Architecture context
<relevant sections, summarized to key specs the implementation needs>

## Implementation notes
<relevant guidance from the implementation guide>

## Key files to create/modify
<list the files this story touches based on the architecture doc>
```

Then say: **"Context loaded. Ready to build — describe what you want to start with or say 'go' to follow the implementation guide."**
