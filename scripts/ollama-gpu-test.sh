#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# ollama-gpu-test.sh — Spin up a spot L4 GPU VM with Ollama for testing
#
# Usage:
#   ./scripts/ollama-gpu-test.sh up      # create VM, install Ollama, pull model
#   ./scripts/ollama-gpu-test.sh status   # check VM status + Ollama health
#   ./scripts/ollama-gpu-test.sh ssh      # SSH into the VM
#   ./scripts/ollama-gpu-test.sh down     # delete VM
#   ./scripts/ollama-gpu-test.sh env      # print .env.local overrides
#
# After "up", update .env.local with the output from "env", then restart
# your local uvicorn. Everything else (Postgres, Neo4j, Redis) stays local.
#
# Cost: ~$0.28/hr (spot pricing). Delete when done.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

VM_NAME="ollama-gpu-test"
ZONE="${ZONE:-}"
MACHINE_TYPE="g2-standard-4"

# Zones to try in order when no ZONE is specified.
ZONE_CANDIDATES=(
  us-central1-a us-central1-b us-central1-c
  us-east1-b us-east1-c us-east1-d
  us-west1-a us-west1-b
  us-west4-a us-west4-b
  europe-west4-a europe-west4-b europe-west4-c
)
GPU_TYPE="nvidia-l4"
BOOT_DISK_SIZE="80GB"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:32b}"
EMBED_MODEL="nomic-embed-text"

# Resolve project from gcloud config
PROJECT=$(gcloud config get-value project 2>/dev/null)
if [[ -z "$PROJECT" ]]; then
  echo "ERROR: No GCP project set. Run: gcloud config set project <PROJECT_ID>"
  exit 1
fi

# ── Helpers ───────────────────────────────────────────────────────────

find_vm_zone() {
  gcloud compute instances list \
    --project="$PROJECT" \
    --filter="name=$VM_NAME" \
    --format="value(zone)" 2>/dev/null | head -1
}

require_vm_zone() {
  if [[ -z "$ZONE" ]]; then
    ZONE=$(find_vm_zone)
  fi
  if [[ -z "$ZONE" ]]; then
    echo "ERROR: VM '$VM_NAME' not found. Run: ./scripts/ollama-gpu-test.sh up"
    exit 1
  fi
}

get_external_ip() {
  require_vm_zone
  gcloud compute instances describe "$VM_NAME" \
    --zone="$ZONE" \
    --format="get(networkInterfaces[0].accessConfigs[0].natIP)" 2>/dev/null
}

wait_for_ssh() {
  echo "Waiting for SSH to become available..."
  for i in $(seq 1 30); do
    if gcloud compute ssh "$VM_NAME" --zone="$ZONE" --command="echo ready" &>/dev/null; then
      return 0
    fi
    sleep 5
  done
  echo "ERROR: SSH not available after 150s"
  exit 1
}

wait_for_ollama() {
  local ip=$1
  echo "Waiting for Ollama to become available..."
  for i in $(seq 1 30); do
    if curl -sf "http://${ip}:11434/api/tags" &>/dev/null; then
      return 0
    fi
    sleep 5
  done
  echo "ERROR: Ollama not responding after 150s"
  exit 1
}

# ── Commands ──────────────────────────────────────────────────────────

cmd_up() {
  # Build the list of zones to try.
  if [[ -n "$ZONE" ]]; then
    zones=("$ZONE")
  else
    zones=("${ZONE_CANDIDATES[@]}")
  fi

  echo "Creating spot $MACHINE_TYPE + $GPU_TYPE VM: $VM_NAME"
  echo "Project: $PROJECT"
  echo "Trying zones: ${zones[*]}"
  echo ""

  local created=false
  for z in "${zones[@]}"; do
    echo "→ Trying $z ..."
    if gcloud compute instances create "$VM_NAME" \
      --project="$PROJECT" \
      --zone="$z" \
      --machine-type="$MACHINE_TYPE" \
      --accelerator="type=$GPU_TYPE,count=1" \
      --boot-disk-size="$BOOT_DISK_SIZE" \
      --image-family=common-cu129-ubuntu-2204-nvidia-580 \
      --image-project=deeplearning-platform-release \
      --maintenance-policy=TERMINATE \
      --tags=ollama-test \
      --metadata=install-nvidia-driver=True,startup-script='#!/bin/bash
        # Log everything for debugging
        exec > /var/log/ollama-setup.log 2>&1
        set -ex

        # Verify GPU driver is working
        nvidia-smi

        # Install Ollama
        curl -fsSL https://ollama.com/install.sh | sh

        # Configure Ollama to listen on all interfaces
        mkdir -p /etc/systemd/system/ollama.service.d
        cat > /etc/systemd/system/ollama.service.d/override.conf <<CONF
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_KEEP_ALIVE=-1"
CONF
        systemctl daemon-reload
        systemctl restart ollama

        # Wait for Ollama to be ready then pull models
        export HOME=/root
        sleep 5
        ollama pull '"$OLLAMA_MODEL"'
        ollama pull '"$EMBED_MODEL"'

        # Warmup: load model into VRAM (OLLAMA_KEEP_ALIVE=-1 keeps it forever)
        ollama run '"$OLLAMA_MODEL"' "hi" </dev/null || true
      ' 2>&1; then
      ZONE="$z"
      created=true
      break
    else
      echo "  ✗ $z unavailable, trying next..."
      echo ""
    fi
  done

  if [[ "$created" != "true" ]]; then
    echo ""
    echo "ERROR: Could not create VM in any zone. All zones are stocked out."
    echo "Try again later or specify a zone manually: ZONE=<zone> $0 up"
    exit 1
  fi

  echo ""

  # Open firewall for Ollama port (idempotent)
  if ! gcloud compute firewall-rules describe allow-ollama-test --project="$PROJECT" &>/dev/null; then
    echo "Creating firewall rule for port 11434..."
    gcloud compute firewall-rules create allow-ollama-test \
      --project="$PROJECT" \
      --allow=tcp:11434 \
      --target-tags=ollama-test \
      --source-ranges="0.0.0.0/0" \
      --description="Temporary: allow Ollama access for GPU testing"
  fi

  echo ""
  echo "VM created in $ZONE. The startup script is installing NVIDIA drivers + Ollama"
  echo "and pulling $OLLAMA_MODEL. This takes ~5-10 minutes."
  echo ""
  echo "Monitor progress:"
  echo "  ./scripts/ollama-gpu-test.sh ssh"
  echo "  sudo tail -f /var/log/ollama-setup.log"
  echo ""
  echo "When ready, run:"
  echo "  ./scripts/ollama-gpu-test.sh env"
}

cmd_status() {
  local ip
  ip=$(get_external_ip)
  if [[ -z "$ip" ]]; then
    echo "VM not found or not running."
    exit 1
  fi

  echo "VM: $VM_NAME ($ip)"
  echo ""

  # Check Ollama
  if curl -sf "http://${ip}:11434/api/tags" &>/dev/null; then
    echo "Ollama: UP"
    echo ""
    echo "Loaded models:"
    curl -sf "http://${ip}:11434/api/tags" | python3 -m json.tool 2>/dev/null \
      | grep -E '"name"|"size"' || true
    echo ""
    echo "Running models:"
    curl -sf "http://${ip}:11434/api/ps" | python3 -m json.tool 2>/dev/null || true
  else
    echo "Ollama: NOT RESPONDING (still starting up?)"
    echo ""
    echo "Check startup logs:"
    echo "  ./scripts/ollama-gpu-test.sh ssh"
    echo "  sudo tail -f /var/log/ollama-setup.log"
  fi
}

cmd_ssh() {
  require_vm_zone
  gcloud compute ssh "$VM_NAME" --zone="$ZONE"
}

cmd_down() {
  require_vm_zone
  echo "Deleting VM: $VM_NAME (zone: $ZONE)"
  gcloud compute instances delete "$VM_NAME" \
    --zone="$ZONE" \
    --quiet

  echo "Deleting firewall rule..."
  gcloud compute firewall-rules delete allow-ollama-test \
    --project="$PROJECT" \
    --quiet 2>/dev/null || true

  echo "Done. VM and firewall rule removed."
}

cmd_env() {
  local ip
  ip=$(get_external_ip)
  if [[ -z "$ip" ]]; then
    echo "ERROR: VM not found. Run: ./scripts/ollama-gpu-test.sh up"
    exit 1
  fi

  # Verify Ollama is responding
  if ! curl -sf "http://${ip}:11434/api/tags" &>/dev/null; then
    echo "WARNING: Ollama not responding yet at $ip:11434"
    echo "The startup script may still be running. Check with:"
    echo "  ./scripts/ollama-gpu-test.sh status"
    echo ""
  fi

  echo "# Add these to .env.local (replacing existing OLLAMA_ lines):"
  echo "OLLAMA_URL=http://${ip}:11434"
  echo "OLLAMA_MODEL=${OLLAMA_MODEL}"
}

# ── Dispatch ──────────────────────────────────────────────────────────

case "${1:-help}" in
  up)     cmd_up ;;
  status) cmd_status ;;
  ssh)    cmd_ssh ;;
  down)   cmd_down ;;
  env)    cmd_env ;;
  *)
    echo "Usage: $0 {up|status|ssh|down|env}"
    echo ""
    echo "  up      Create spot L4 GPU VM, install Ollama, pull $OLLAMA_MODEL"
    echo "  status  Check VM and Ollama health"
    echo "  ssh     SSH into the VM"
    echo "  down    Delete VM and firewall rule"
    echo "  env     Print .env.local overrides for connecting"
    ;;
esac
