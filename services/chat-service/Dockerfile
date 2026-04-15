FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY shared/ shared/
COPY services/chat-service/ services/chat-service/

RUN uv sync --package chat-service --frozen --no-dev

RUN adduser --disabled-password --no-create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app

USER appuser
WORKDIR /app/services/chat-service
EXPOSE 8001
CMD ["/app/.venv/bin/uvicorn", "chat_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
