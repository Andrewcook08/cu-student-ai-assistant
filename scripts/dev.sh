#!/usr/bin/env bash
set -euo pipefail

# ── CU Student AI Assistant — Dev Environment Manager ──────────────
# Usage:
#   scripts/dev.sh up [--seed]   Start containers, optionally seed data
#   scripts/dev.sh down          Stop containers (keep volumes)
#   scripts/dev.sh reset         Wipe volumes + fresh start with seed
#   scripts/dev.sh seed          Run data ingestion (containers must be running)
#   scripts/dev.sh status        Show container health

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Models to pull into Ollama before seeding.
OLLAMA_MODELS=("nomic-embed-text" "gpt-oss:20b")

HEALTH_TIMEOUT=120  # seconds to wait for all services to be healthy

# ── Helpers ─────────────────────────────────────────────────────────

info()  { printf '\033[1;34m▸ %s\033[0m\n' "$*"; }
ok()    { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
warn()  { printf '\033[1;33m⚠ %s\033[0m\n' "$*"; }
err()   { printf '\033[1;31m✖ %s\033[0m\n' "$*" >&2; }

wait_healthy() {
    info "Waiting for services to be healthy (timeout: ${HEALTH_TIMEOUT}s)..."
    local elapsed=0
    local services=("postgres" "neo4j" "redis" "ollama")
    while (( elapsed < HEALTH_TIMEOUT )); do
        local all_healthy=true
        for svc in "${services[@]}"; do
            local health
            health=$(docker compose ps --format '{{.Health}}' "$svc" 2>/dev/null || echo "missing")
            if [[ "$health" != "healthy" ]]; then
                all_healthy=false
                break
            fi
        done
        if $all_healthy; then
            ok "All data services healthy."
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    err "Timed out waiting for healthy services after ${HEALTH_TIMEOUT}s."
    docker compose ps
    return 1
}

pull_models() {
    for model in "${OLLAMA_MODELS[@]}"; do
        if docker compose exec -T ollama ollama list 2>/dev/null | grep -q "^${model}"; then
            ok "Model '${model}' already present."
        else
            info "Pulling Ollama model '${model}'..."
            docker compose exec -T ollama ollama pull "$model"
            ok "Model '${model}' pulled."
        fi
    done
}

run_ingestion() {
    info "Step 1/4: Ingesting courses..."
    uv run --package data-ingest python -m data.ingest.ingest_courses
    ok "Courses ingested."

    info "Step 2/4: Parsing prerequisites..."
    uv run --package data-ingest python -m data.ingest.parse_prerequisites
    ok "Prerequisites parsed."

    info "Step 3/4: Ingesting requirements..."
    uv run --package data-ingest python -m data.ingest.ingest_requirements
    ok "Requirements ingested."

    info "Step 4/4: Building embeddings (this may take a few minutes)..."
    uv run --package data-ingest python -m data.ingest.build_embeddings
    ok "Embeddings built."
}

# ── Commands ────────────────────────────────────────────────────────

cmd_up() {
    local seed=false
    for arg in "$@"; do
        case "$arg" in
            --seed) seed=true ;;
            *) err "Unknown flag: $arg"; exit 1 ;;
        esac
    done

    info "Starting Docker containers..."
    docker compose up -d
    wait_healthy

    if $seed; then
        cmd_seed
    else
        ok "Containers running. Use 'scripts/dev.sh seed' to ingest data."
    fi
}

cmd_down() {
    info "Stopping containers (volumes preserved)..."
    docker compose down
    ok "Containers stopped."
}

cmd_reset() {
    warn "This will DELETE all data volumes and rebuild from scratch."
    info "Stopping containers and removing volumes..."
    docker compose down -v
    ok "Volumes removed."

    info "Rebuilding..."
    docker compose up -d --build
    wait_healthy
    cmd_seed
    ok "Full reset complete."
}

cmd_seed() {
    info "Seeding databases..."
    pull_models
    run_ingestion
    ok "All data seeded successfully."
}

cmd_status() {
    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
}

# ── Dispatch ────────────────────────────────────────────────────────

case "${1:-help}" in
    up)     shift; cmd_up "$@" ;;
    down)   cmd_down ;;
    reset)  cmd_reset ;;
    seed)   cmd_seed ;;
    status) cmd_status ;;
    *)
        cat <<'USAGE'
Usage: scripts/dev.sh <command> [flags]

Commands:
  up [--seed]   Start containers; --seed also pulls models + ingests data
  down          Stop containers (keep data volumes)
  reset         Wipe volumes, rebuild containers, and seed from scratch
  seed          Pull models + run all 4 ingestion steps
  status        Show container status and ports
USAGE
        exit 1
        ;;
esac
