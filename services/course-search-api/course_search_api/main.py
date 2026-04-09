"""Course Search API — stateless REST over PostgreSQL."""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j import AsyncGraphDatabase
from shared.config import settings
from shared.database import engine
from shared.models import Base
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


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    response = JSONResponse(content={"detail": "Too many requests"}, status_code=429)
    current_limit = getattr(request.state, "view_rate_limit", None)
    if current_limit:
        window_stats = limiter._limiter.get_window_stats(
            current_limit[0], *current_limit[1]
        )
        retry_after = max(1, int(window_stats[0] - time.time()))
        response.headers["Retry-After"] = str(retry_after)
    return response


app = FastAPI(title="CU Course Search API", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(programs.router)
app.include_router(students.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
