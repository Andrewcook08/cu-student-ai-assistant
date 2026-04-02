FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY shared/ shared/
COPY services/course-search-api/ services/course-search-api/

RUN uv sync --package course-search-api --frozen --no-dev

WORKDIR /app/services/course-search-api
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
