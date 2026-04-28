# CU Student AI Assistant

A class project for CSCI Big Data Architecture at CU Boulder (Spring 2026).

## The problem

Picking classes at CU is harder than it should be. The course catalog is a static website. Degree requirements live in PDFs. Prerequisite chains are buried in dropdowns. The only personalized help is your advisor — and advisors are overloaded with hundreds of students.

So most students plan their schedule the hard way: by spending an afternoon flipping between catalog tabs, requirement sheets, and RateMyProfessor, trying to keep it all in their head at once.

## The idea

What if you could just *ask*?

> *"I'm a CS major, I've finished my intro sequence, and I want a lighter semester next spring with at least one upper-division CS class. What should I take?"*

That's what this project is: an AI assistant that knows the CU catalog, understands degree requirements, and can actually have a conversation about your schedule — not just spit back search results.

## What it does

- **Search the catalog** by department, level, keywords, time of day, instructor
- **Chat with an AI** that has read the entire CU course catalog (3,400+ courses, 200+ degree programs, the full prerequisite graph)
- **Get personalized recommendations** grounded in real courses you can actually register for — no hallucinated class numbers
- **Remember your decisions** across sessions so you don't have to re-explain your situation every time

The chat side is the interesting part. It uses Claude as the language model, but the answers are grounded in our own database — so when it tells you to take CSCI 3104, that's a real class, with a real prereq chain, taught by a real instructor next semester.

## Why we built it this way

The class is called Big Data Architecture, so the goal isn't just "ship a chatbot." It's to build something that looks like how a real production system would be put together if a small team had to ship it.

That meant making real architectural decisions and living with them:

- **Two backend services, not one.** A fast REST API for course search, a separate streaming service for chat. They scale differently, fail differently, and shouldn't share a process.
- **A graph database, not just SQL.** Prerequisites are a graph. Trying to model "what classes does CSCI 3104 transitively unlock?" in pure SQL is painful. Neo4j makes it natural.
- **A real ingest pipeline.** The catalog comes in as messy JSON, gets cleaned, embedded, and loaded into two databases. It runs as a Cloud Run Job, not a script someone forgot to run.
- **Fully ephemeral infrastructure.** The whole stack on GCP can be torn down to $0 and brought back up from scratch in 20 minutes. No "don't touch that, it's been running since October."

We wrote down every non-obvious decision as an ADR (50+ of them) so a future teammate — or grader — can see *why* a choice was made, not just *what* was chosen.

## The team

- **Andrew** — data ingest, AI / chat service, GCP infra
- **Rohan** — frontend, course search API
- **Scott** — shared infrastructure, deploy pipeline, cross-cutting concerns

## Where to look next

| If you want to… | Read this |
|---|---|
| See the design and the tradeoffs | [`docs/architecture.md`](docs/architecture.md) |
| Understand *why* things are the way they are | [`docs/decisions.md`](docs/decisions.md) |
| See the assistant in action | [`docs/example-conversation.md`](docs/example-conversation.md) |
| Run it locally | [`docs/local-development.md`](docs/local-development.md) |
| Stand it up on GCP (or tear it down) | [`infra/README.md`](infra/README.md) |

## Status

This is a class project, not a live service. The cloud stack is ephemeral and torn down between demos to keep cost at zero. Code is on `main`; ongoing work happens in `docs/*` and `feat/*` branches and lands through PRs.
