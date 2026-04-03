# Story Routing Table

Map the story ID prefix to the architecture.md sections that are relevant for building it.

| Story prefix | Architecture sections to read | Also check |
|-------------|-------------------------------|------------|
| INFRA- | § Repo Structure, § Tech Stack, § Service Architecture | local-development.md |
| DATA- | § Data Architecture, § Neo4j Graph Schema, § PostgreSQL Schema, § Prerequisite Parsing, § Neo4j Vector Indexes | — |
| API- | § API Design, § PostgreSQL Schema, § Data Architecture (datasets table for expected shapes) | — |
| CHAT- | § Tool Calling, § Service Architecture (chat service), § Conversation Memory, § Security (defense 1: tool auth) | decisions.md ADR-5 (LangGraph), ADR-6 (tool calling), ADR-7 (Redis queue) |
| FE- | § Frontend, § API Design (for the request/response contract), § Chat Response Schema | — |
| AUTH- | § API Design (auth endpoints), § Security (defense 1), § Student Profile — POC vs Production | decisions.md ADR-10 (JWT) |
| MEM- | § Conversation Memory, § Tool Calling (get_student_profile, save_decision) | decisions.md ADR-8 (two-tier memory), ADR-9 (persistent decisions) |
| SEC- | § Security (all 6 defenses), § Tool Calling (tool executor) | decisions.md ADR-14 (tool auth), ADR-17 (defense in depth) |
| DEPLOY- | § GCP Deployment, § Network Security, § Scaling Strategy, § Ollama GPU Auto-Scaling | decisions.md ADR-13 (GCP), ADR-18 (Terraform), ADR-19 (self-hosted DBs), ADR-23 (private subnet) |
| CICD- | § Repo Structure (GitHub Actions section) | development-workflow.md § PR Workflow |
| DEMO- | § Implementation Phases (Phase 4) | — |
