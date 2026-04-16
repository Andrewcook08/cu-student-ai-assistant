# Prebaked Ollama embedding service for Cloud Run (CUAI-88).
# Bakes nomic-embed-text (768-dim) into the image at build time so the
# container starts instantly without a pull on first request.
# See ADR-42 (docs/decisions.md) for the rationale and design constraints.

FROM ollama/ollama:0.20.7

ENV OLLAMA_HOST=0.0.0.0:11434

# Start the daemon in the background, wait for it to accept API calls (no fixed
# sleep — `ollama list` only succeeds once the daemon is ready), pull the model,
# then terminate the daemon so the image commits cleanly.
RUN ollama serve & \
    until ollama list >/dev/null 2>&1; do sleep 0.5; done && \
    ollama pull nomic-embed-text:v1.5 && \
    pkill ollama

EXPOSE 11434
