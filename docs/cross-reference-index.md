# Cross-Reference Index

> Where to find each concept's canonical definition and which files reference it.
> When updating a concept, start with the **Canonical Source** — other files should reference it, not duplicate it.

| Concept | Canonical Source | Also Referenced In |
|---------|------------------|--------------------|
| PostgreSQL schema / tables | `architecture.md` § Data Architecture | `implementation-guide.md`, `jira-epics-and-stories.md` |
| Neo4j graph schema | `architecture.md` § Neo4j Graph Schema | `implementation-guide.md`, `jira-epics-and-stories.md` |
| API endpoints / routes | `architecture.md` § API Design | `implementation-guide.md`, `jira-epics-and-stories.md`, `claude-code-project-context.md` |
| Tool definitions (`@tool`) | `architecture.md` § Tool Calling | `implementation-guide.md`, `jira-epics-and-stories.md` |
| Tech stack choices | `architecture.md` § Tech Stack | `decisions.md`, `claude-code-project-context.md` |
| Scaling / infra config | `architecture.md` § Scaling Strategy | `decisions.md`, `implementation-guide.md` |
| Security model | `architecture.md` § Security | `decisions.md`, `implementation-guide.md`, `jira-epics-and-stories.md` |
| Repo structure / file paths | `architecture.md` § Repo Structure | `claude-code-project-context.md`, `development-workflow.md` |
| Docker / local dev setup | `local-development.md` | `implementation-guide.md`, `claude-code-project-context.md` |
| Env vars / config | `architecture.md` + `.env.example` | `implementation-guide.md`, `claude-code-project-context.md` |
| Team assignments / phases | `architecture.md` § Implementation Phases | `jira-epics-and-stories.md`, `development-workflow.md`, `implementation-guide.md` |
| Commands (uv, docker) | `claude-code-project-context.md` | `local-development.md`, `development-workflow.md` |
| ADR decisions | `decisions.md` | `architecture.md` (cross-refs) |
| Jira story details | `jira-epics-and-stories.md` | `implementation-guide.md` |
| Git / branching workflow | `development-workflow.md` | `claude-code-project-context.md` |
| Dataset counts | `architecture.md` § Datasets | `jira-epics-and-stories.md` (acceptance criteria) |
| Conversation memory | `architecture.md` § Conversation Memory | `decisions.md` (ADR-8), `implementation-guide.md`, Jira stories (MEM-*) |
| Ollama model choice | `decisions.md` § ADR-26 | `architecture.md` § Tech Stack, `claude-code-project-context.md` |
