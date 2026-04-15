#!/bin/bash
# data-vm-startup.sh
# Runs on every VM boot via GCE metadata startup-script (idempotent).
#
# What this does:
#   1. Installs Docker CE + Compose plugin (skips if already installed)
#   2. Mounts the persistent data disk at /data (formats on first boot only)
#   3. Fetches secrets from GCP Secret Manager
#   4. Writes docker-compose.yml + .env to /data/compose
#   5. Starts PostgreSQL, Neo4j, and Redis via docker compose up -d
#
# Prerequisites — populate secret values before the VM is useful:
#   gcloud secrets versions add data-vm-postgres-password \
#     --data-file=<(openssl rand -hex 20)
#   gcloud secrets versions add data-vm-neo4j-password \
#     --data-file=<(openssl rand -hex 20)
#   gcloud secrets versions add data-vm-redis-password \
#     --data-file=<(openssl rand -hex 20)
set -euo pipefail
exec > >(tee /var/log/data-vm-startup.log) 2>&1

log() { echo "[startup] $(date -u +%H:%M:%S) $*"; }

on_failure() {
  log "STARTUP FAILED at line $1 (exit $2)"
  echo "failed at $(date -u +%FT%TZ)" > /var/log/data-vm-startup.FAILED
}
trap 'on_failure "$LINENO" "$?"' ERR

log "Starting data-vm-startup.sh"

# ── 1. Install Docker ──────────────────────────────────────────────────────────

if ! command -v docker &>/dev/null; then
  log "Installing Docker CE..."
  apt-get update -q
  apt-get install -y -q ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable --now docker
  log "Docker installed: $(docker --version)"
else
  log "Docker already present: $(docker --version)"
fi

# ── 2. Mount persistent data disk ─────────────────────────────────────────────
# The Terraform attached_disk device_name "data-disk" surfaces as this path.

DATA_DISK_ID="/dev/disk/by-id/google-data-disk"
MOUNT_POINT="/data"

mkdir -p "${MOUNT_POINT}"

if ! blkid "${DATA_DISK_ID}" &>/dev/null; then
  log "First boot — formatting data disk..."
  mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard "${DATA_DISK_ID}"
fi

if ! mountpoint -q "${MOUNT_POINT}"; then
  log "Mounting data disk at ${MOUNT_POINT}..."
  mount -o discard,defaults "${DATA_DISK_ID}" "${MOUNT_POINT}"
fi

if ! grep -q "${DATA_DISK_ID}" /etc/fstab; then
  echo "${DATA_DISK_ID} ${MOUNT_POINT} ext4 discard,defaults,nofail 0 2" >> /etc/fstab
  log "Added fstab entry (auto-mount on reboot)"
fi

# Bind-mount targets — one directory per database on the persistent disk
mkdir -p \
  "${MOUNT_POINT}/postgres" \
  "${MOUNT_POINT}/neo4j" \
  "${MOUNT_POINT}/redis"

# ── 3. Fetch secrets from GCP Secret Manager ──────────────────────────────────

log "Fetching secrets..."
PROJECT=$(curl -sf \
  "http://metadata.google.internal/computeMetadata/v1/project/project-id" \
  -H "Metadata-Flavor: Google")

secret() {
  gcloud secrets versions access latest --secret="$1" --project="${PROJECT}"
}

POSTGRES_PASSWORD=$(secret "data-vm-postgres-password")
NEO4J_PASSWORD=$(secret "data-vm-neo4j-password")
REDIS_PASSWORD=$(secret "data-vm-redis-password")
log "Secrets fetched"

# ── 4. Write compose files ─────────────────────────────────────────────────────

COMPOSE_DIR="${MOUNT_POINT}/compose"
mkdir -p "${COMPOSE_DIR}"

# .env — actual secret values read by docker compose at startup
# mode 600: root-only, not readable by other OS users
cat > "${COMPOSE_DIR}/.env" <<EOF
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
NEO4J_PASSWORD=${NEO4J_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
EOF
chmod 600 "${COMPOSE_DIR}/.env"

# Pull the real compose files from GCS (uploaded by terraform apply).
# Using the actual docker-compose.prod.yml ensures no host port bindings
# and required-secret validation — satisfies SEC-008 (CUAI-82).
BUCKET=$(curl -sf \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/vm-assets-bucket" \
  -H "Metadata-Flavor: Google")

log "Pulling compose files from gs://${BUCKET}..."
for i in 1 2 3 4 5; do
  gsutil cp "gs://${BUCKET}/docker-compose.yml"      "${COMPOSE_DIR}/docker-compose.yml" && \
  gsutil cp "gs://${BUCKET}/docker-compose.prod.yml" "${COMPOSE_DIR}/docker-compose.prod.yml" && break
  log "gsutil cp failed (attempt ${i}) — retrying in 10 s"
  sleep 10
done
log "Compose files ready"

# ── 5. Start data services ─────────────────────────────────────────────────────

log "Starting data services (postgres, neo4j, redis)..."
cd "${COMPOSE_DIR}"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres neo4j redis

log "Verifying services started (up to 60 s)..."
for i in 1 2 3 4 5 6; do
  docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
  if docker compose -f docker-compose.yml -f docker-compose.prod.yml ps | grep -q "unhealthy"; then
    if [ "${i}" -eq 6 ]; then
      log "STARTUP FAILED — one or more services unhealthy after 60 s"
      exit 1
    fi
    log "Services not yet healthy (attempt ${i}/6) — retrying in 10 s..."
    sleep 10
  else
    log "All services running"
    break
  fi
done

log "data-vm-startup.sh complete"
