# Subagent Instructions

When dispatching a Task for each file, include the change manifest and the file-specific instructions below.

## Base prompt for every subagent
```
You are updating one documentation file. Read the file, find every reference to the stale terms in the manifest, update to new values, and grep the file afterward for any you missed.

CHANGE MANIFEST:
<paste here>

FILE: docs/<name>.md
SECTIONS: <from manifest>
```

## File-specific additions

### architecture.md
- Update Table of Contents if sections were added/removed/renamed
- Update Open Questions if any were resolved
- Verify internal cross-references (ADR links, section anchors)

### decisions.md
- Add a new ADR if the change is a new architectural decision
- Never edit published ADR decisions/rationale; write a new ADR that supersedes
- ADRs are append-only historical records

### implementation-guide.md
- Update sequence, instructions, and checkpoints
- If references to architecture.md exist (post-restructure), verify they still resolve
- If duplicated code blocks remain (pre-restructure), update them

### jira-epics-and-stories.md
- Update affected story descriptions and acceptance criteria
- Update dependency graph if dependencies changed
- Update sprint plan if assignments or timing changed
- Update summary table at bottom
- **Track which stories were modified — report their story IDs back so the main agent can update Jira in Phase 3**

### local-development.md
- Update port map, docker-compose details, or commands if affected
- Update troubleshooting section if relevant

### development-workflow.md
- Update per-person Claude Code sections if team assignments changed
- Update branch naming or PR workflow if affected

### claude-code-project-context.md
- Keep it thin; update commands and conventions only
- If it references architecture.md (post-restructure), verify references

### claude-code-setup.md
- Rarely affected; only update if Claude Code workflow changed