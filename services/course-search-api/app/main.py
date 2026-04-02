"""Course Search API — stateless REST over PostgreSQL."""

from fastapi import FastAPI

app = FastAPI(title="CU Course Search API")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
