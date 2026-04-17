FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY shared/ shared/
COPY data/ data/

RUN uv sync --package data-ingest --frozen --no-dev

RUN adduser --disabled-password --no-create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["/app/.venv/bin/python", "-m", "data.ingest", "run"]
CMD ["--mode=upsert"]
