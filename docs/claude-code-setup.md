# Claude Code Setup

> How to set up Claude Code for this project. Do this once after cloning the repo.

---

## 1. Install Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

Or see the [official docs](https://docs.anthropic.com/en/docs/claude-code) for other install methods.

## 2. Understand what's automatic

**`CLAUDE.md`** in the repo root is loaded automatically every conversation. It contains workflow rules (plan mode, verification, task management) that guide how Claude works on this project. You don't need to do anything — just having it in the repo is enough.

## 3. Bootstrap project context into memory

Claude Code has a per-project memory system that persists across conversations. The first time you use Claude Code on this repo, load the project context:

```
cd cu-student-ai-assistant
claude
```

Then in your first conversation, say:

```
Read docs/claude-code-project-context.md and save it all to your memory.
```

This gives Claude the architecture, conventions, commands, and environment variable reference so it doesn't need to re-discover them each session.

## 4. Optional: Add your role context

Tell Claude who you are so it can tailor responses:

- **Scott**: "I'm Scott, Person A on the team. I own the shared package, conversation memory, Docker, Terraform, and GCP deployment."
- **Rohan**: "I'm Rohan, Person B on the team. I own the frontend, Course Search API, auth endpoints, and CI/CD."
- **Andrew**: "I'm Andrew, Person C on the team. I own data ingestion, AI/chat engine, LangGraph, Neo4j, Redis, and security."

Claude will save this to memory and use it in future conversations.

## 5. Working with Claude Code

Key things to know:

- **Plans directory**: Implementation plans live in `plans/` (gitignored). Claude writes plans here before building.
- **Tasks directory**: Task tracking and lessons learned live in `tasks/` — Claude uses `tasks/todo.md` for progress and `tasks/lessons.md` for self-correction patterns.
- **Jira keys**: Reference tickets by their story ID (e.g., "work on INFRA-001") — Claude knows the Jira project structure.
- **Branch naming**: Create your branch first (`feat/CUAI-XX-short-description`), then tell Claude what to build.
- **Verification**: Claude will run `uv run ruff check .`, tests, and other checks before marking work done.

## 6. Useful commands inside Claude Code

| Command | What it does |
|---------|-------------|
| `/plan` | Enter plan mode — Claude researches and writes a plan before coding |
| `/compact` | Compress conversation context when it gets long |
| `! <command>` | Run a shell command in-session (e.g., `! docker compose up -d`) |
