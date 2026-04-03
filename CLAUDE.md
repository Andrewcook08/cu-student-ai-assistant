# CU Student AI Assistant

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- One task per subagent for focused execution

**When to use a subagent (Task tool):**
- One focused job: research, edit a file, review code, run a grep
- Task needs context from the main conversation
- Sequential dependency: output of one feeds the next

**When to use agent teams (parallel agents):**
- Multiple independent units of work that touch completely different files
- If two tasks could edit the same file, they cannot be parallelized — use sequential subagents instead

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

Each in-progress ticket gets its own subfolder under `tasks/`:
```
tasks/
├── CUAI-20/
│   ├── todo.md             # Plan + checkable items + review
│   └── notes.md            # Optional: scratch notes, data discoveries
├── CUAI-42/
│   └── todo.md
└── ...
```

- **Create folder**: `tasks/<TICKET-KEY>/todo.md` when starting a ticket
- **Remove folder**: Delete `tasks/<TICKET-KEY>/` when the ticket is resolved

### Workflow
1. **Plan First**: Write plan to `tasks/<TICKET-KEY>/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/<TICKET-KEY>/todo.md`

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
