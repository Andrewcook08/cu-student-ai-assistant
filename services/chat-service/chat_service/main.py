"""Chat Service — stateful AI orchestration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

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
    try:
        yield
    finally:
        await app.state.neo4j_driver.close()


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
