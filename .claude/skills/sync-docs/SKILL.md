---
name: sync-docs
description: Extract doc changes from the current feature branch into a separate PR targeting main for review.
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash
---

**Extract doc changes from this feature branch and open a PR to main.**

## Steps

1. Confirm we're on a feature branch, not main. If on main, stop.
2. Diff against main for doc-only changes (`docs/**`, `*.md`, `.claude/**`). If none, stop.
3. Get the ticket key from the current branch name (e.g., `CUAI-23` from `feat/CUAI-23-whatever`).
4. Check if a `docs/<ticket>-updates` branch already exists (local or remote).
5. Create or update that branch off main with just the doc files from this feature branch.
6. Push it and open a PR with `gh` if one doesn't already exist. Title: `docs: updates from <ticket>`.
7. Switch back to the original feature branch.
8. Say: **"Doc PR opened/updated: `docs/<ticket>-updates`. Have a teammate review and merge, then run `/pull-main` to pick up the changes."**