"""Course Search API — stateless REST over PostgreSQL."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neo4j import AsyncGraphDatabase
from shared.config import settings
from shared.database import engine
from shared.middleware import SecurityHeadersMiddleware
from shared.models import Base
from shared.rate_limit import make_rate_limit_handler
from slowapi.errors import RateLimitExceeded

from course_search_api.limiter import limiter
from course_search_api.routes import auth, courses, programs, students


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings.validate_production()
    Base.metadata.create_all(bind=engine)
    # Long-lived singletons — avoid per-request construction overhead.
    app.state.http_client = httpx.AsyncClient(timeout=120.0)
    app.state.neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        await app.state.neo4j_driver.close()


app = FastAPI(
    title="CU Course Search API",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, make_rate_limit_handler(limiter))  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(SecurityHeadersMiddleware, environment=settings.environment)


app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(programs.router)
app.include_router(students.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
