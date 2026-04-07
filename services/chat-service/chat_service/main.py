"""Chat Service — stateful AI orchestration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neo4j import AsyncGraphDatabase
from shared.config import settings

from chat_service.routes import chat


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Long-lived singleton — the driver owns a connection pool and must
    # outlive individual requests. Tool handlers pull it off app.state.
    app.state.neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    # Long-lived httpx client for Ollama. Timeout is split per phase so
    # that the generous inference budget doesn't also apply to connect /
    # write / pool — an unreachable Ollama should surface in seconds, not
    # minutes. Read timeout is the inference budget: chat completions on
    # larger models can run ~60s, 120s leaves headroom.
    app.state.ollama_client = httpx.AsyncClient(
        base_url=settings.ollama_url,
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
    )
    try:
        yield
    finally:
        # Nested try/finally so a failure closing one resource still lets
        # the other close — otherwise the second aclose would be skipped.
        try:
            await app.state.neo4j_driver.close()
        finally:
            await app.state.ollama_client.aclose()


app = FastAPI(title="CU Chat Service", lifespan=lifespan)

app.include_router(chat.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/chat/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
