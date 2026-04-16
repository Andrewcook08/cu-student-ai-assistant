# Prebaked Ollama embedding service for Cloud Run (CUAI-88).
# Bakes nomic-embed-text (768-dim) into the image at build time so the
# container starts instantly without a pull on first request.
# See ADR-42 (docs/decisions.md) for the rationale and design constraints.

FROM ollama/ollama:latest

ENV OLLAMA_HOST=0.0.0.0:11434

RUN ollama serve & sleep 5 && ollama pull nomic-embed-text && pkill ollama

EXPOSE 11434
