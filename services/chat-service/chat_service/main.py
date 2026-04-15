"""Chat Service — stateful AI orchestration."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

import anthropic
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neo4j import AsyncGraphDatabase
from shared.config import settings
from shared.middleware import SecurityHeadersMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chat_service.core.llm_engine import build_graph
from chat_service.core.tool_executor import ToolExecutor
from chat_service.core.tools import make_tools
from chat_service.routes import chat
from chat_service.services.postgres_service import build_postgres_engine
from chat_service.services.redis_service import build_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings.validate_production()
    # Long-lived singleton — the driver owns a connection pool and must
    # outlive individual requests. Tool handlers pull it off app.state.
    app.state.neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    # Long-lived httpx client for Ollama embeddings only. Timeout is
    # split per phase so that the generous inference budget doesn't also
    # apply to connect / write / pool — an unreachable Ollama should
    # surface in seconds, not minutes.
    app.state.ollama_client = httpx.AsyncClient(
        base_url=settings.ollama_url,
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
    )
    # Anthropic SDK client for LLM inference (chat completions, intent
    # classification fallback, summary generation).
    app.state.anthropic_client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
    )
    # Long-lived Redis client. Owns its own connection pool internally,
    # so the same instance is reused across requests by every helper in
    # chat_service.services.redis_service.
    app.state.redis = build_redis_client(settings.redis_url, settings.redis_password)
    # Long-lived async Postgres engine. Owns its own pool, separate
    # from course-search-api's sync engine in shared/shared/database.py.
    app.state.postgres_engine = build_postgres_engine(settings.database_url)
    # Sessionmaker constructed once here so each tool call opens its own
    # short-lived session without re-creating the maker. expire_on_commit=False
    # keeps attributes readable after commit (e.g. server_default timestamps).
    app.state.postgres_sessionmaker = async_sessionmaker(
        app.state.postgres_engine, expire_on_commit=False, class_=AsyncSession
    )
    # Build all seven LangChain tools as closures over the live service
    # handles. CHAT-008 binds app.state.tools to the LLM; CHAT-006's
    # executor dispatches via app.state.tool_registry.
    toolset = make_tools(
        neo4j_driver=app.state.neo4j_driver,
        postgres_sessionmaker=app.state.postgres_sessionmaker,
        ollama_client=app.state.ollama_client,
    )
    app.state.tools = toolset.tools
    app.state.tool_registry = toolset.registry
    # Auth-enforcing tool executor — CHAT-006's ToolExecutor wraps every
    # LLM-generated tool call with JWT user_id override, rate limiting,
    # parameter whitelisting, and audit logging.
    app.state.tool_executor = ToolExecutor(
        tool_registry=app.state.tool_registry,
        postgres_sessionmaker=app.state.postgres_sessionmaker,
    )
    # Compiled LangGraph conversation graph — CHAT-008.  Built once at
    # startup; each ainvoke() operates on an independent state copy so
    # concurrent WebSocket sessions are safe.
    app.state.conversation_graph = build_graph(
        anthropic_api_key=settings.anthropic_api_key,
        anthropic_model=settings.anthropic_model,
        anthropic_client=app.state.anthropic_client,
        tools=app.state.tools,
        tool_executor=app.state.tool_executor,
        ollama_client=app.state.ollama_client,
        neo4j_driver=app.state.neo4j_driver,
        postgres_sessionmaker=app.state.postgres_sessionmaker,
    )
    try:
        yield
    finally:
        # Nested try/finally so a failure closing one resource still lets
        # the others close — otherwise a later aclose would be skipped.
        try:
            await app.state.neo4j_driver.close()
        finally:
            try:
                await app.state.ollama_client.aclose()
            finally:
                try:
                    await app.state.anthropic_client.close()
                finally:
                    try:
                        await app.state.redis.aclose()
                    finally:
                        await app.state.postgres_engine.dispose()


app = FastAPI(title="CU Chat Service", lifespan=lifespan)

app.include_router(chat.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware, environment=settings.environment)


@app.get("/api/chat/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
