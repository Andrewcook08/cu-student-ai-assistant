---
name: pull-main
description: Pull latest main and rebase local feature branches on it. No argument rebases current branch. Pass "all" to rebase all local feature branches.
argument-hint: [all]
disable-model-invocation: true
allowed-tools: Bash
---

**Rebase on latest main.**

## If `$ARGUMENTS` is empty:

1. Confirm we're on a feature branch. If on main, just pull and stop.
2. Stash uncommitted changes if any.
3. Pull latest main.
4. Rebase the current branch on main.
5. If conflicts, list the files and stop. Do not abort.
6. If clean, push with `--force-with-lease` and pop stash.
7. Clean up any local `docs/*-updates` branches that have been merged.

## If `$ARGUMENTS` is `all`:

1. Stash uncommitted changes and record the current branch.
2. Pull latest main.
3. For each local `feat/*` branch, attempt rebase on main.
   - If clean: push with `--force-with-lease`.
   - If conflicts: abort the rebase, add to conflict list, continue with next branch.
4. Return to the original branch, pop stash.
5. Clean up merged `docs/*-updates` branches.
6. Report which branches succeeded and which had conflicts.