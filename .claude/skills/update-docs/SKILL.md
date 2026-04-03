---
name: update-docs
description: Propagate an implementation change across all project documentation with zero stale references.
argument-hint: <description of what changed>
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash Edit Write Task
---

Propagate this change across all project docs: **$ARGUMENTS**

## Phase 1: Build a change manifest

1. Identify stale terms (old values) and new terms (replacements)
2. Map affected files using [cross-reference-map.md](cross-reference-map.md)
3. Write the manifest: summary, stale terms, new terms, files + sections to update

## Phase 2: Update files with subagents

Dispatch one **Task** per affected file. Follow the per-file instructions in [subagent-instructions.md](subagent-instructions.md). Pass the full change manifest to each subagent.

**Order matters:** architecture.md first, decisions.md second, then remaining files in parallel.

## Phase 3: Verify

Dispatch one **Task** to grep all docs for every stale term from the manifest. Report any remaining occurrences with file and line number. If any found, fix them directly.

## Phase 4: Report

List files updated, what changed in each, verification result, and whether a new ADR was added.