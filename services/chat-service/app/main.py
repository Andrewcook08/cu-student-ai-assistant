"""Chat Service — stateful AI orchestration."""

from fastapi import FastAPI

app = FastAPI(title="CU Chat Service")


@app.get("/api/chat/health")
async def health():
    return {"status": "ok"}
