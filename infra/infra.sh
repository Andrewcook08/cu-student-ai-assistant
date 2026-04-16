#!/usr/bin/env bash
# Local test harness for the infra Terraform.
#
# Usage:
#   ./infra.sh plan     # dry-run — no cloud changes
#   ./infra.sh up       # provision everything (plan → apply saved plan)
#   ./infra.sh down     # tear everything down
#   ./infra.sh status   # list deployed resources + show outputs
#   ./infra.sh secrets  # populate empty data-vm-* secrets with random values
#
# Assumes `terraform` is installed and `gcloud auth application-default login`
# has been run so the GCS state backend is accessible.
#
# Firewall rules live inside a google_compute_network_firewall_policy, so
# destroy/recreate cycles do not trigger the legacy VPC firewall name-tombstone.

set -euo pipefail
cd "$(dirname "$0")"

# Post-destroy drift check: anything left in GCP whose name matches the
# project prefix is unmanaged and would block a future re-apply or keep
# costing money. Bare gcloud, no terraform state involved.
check_drift() {
  local found=0
  echo "── Drift check (GCP resources matching cu-assistant-*) ──"

  for cmd_args in \
    "networks list --filter=name~cu-assistant" \
    "networks subnets list --filter=name~cu-assistant" \
    "network-firewall-policies list --filter=name~cu-assistant" \
    "firewall-rules list --filter=network~cu-assistant"; do
    local out
    out=$(gcloud compute $cmd_args --format="value(name)" 2>/dev/null || true)
    if [[ -n "$out" ]]; then
      echo "  ⚠️  $cmd_args:"
      echo "$out" | sed 's/^/      /'
      found=1
    fi
  done

  local connectors
  connectors=$(gcloud compute networks vpc-access connectors list \
    --region=us-central1 --filter="name~cu-assistant" \
    --format="value(name)" 2>/dev/null || true)
  if [[ -n "$connectors" ]]; then
    echo "  ⚠️  vpc-access connectors:"
    echo "$connectors" | sed 's/^/      /'
    found=1
  fi

  if [[ $found -eq 0 ]]; then
    echo "  ✅ Clean — no orphaned resources."
  else
    echo
    echo "Orphans above are NOT managed by Terraform. Delete via gcloud or"
    echo "investigate why they exist before re-running ./infra.sh up."
    return 1
  fi
}

# Populate empty data-vm-* secrets with random hex values.
# Idempotent: skips any secret that already has a version (no rotation surprise).
# Run after the first `./infra.sh up` — Terraform creates the secret shells,
# this fills them so the VM startup script can boot the databases.
populate_secrets() {
  local names=(data-vm-postgres-password data-vm-neo4j-password data-vm-redis-password)
  for name in "${names[@]}"; do
    if gcloud secrets versions list "$name" --limit=1 --format="value(name)" 2>/dev/null | grep -q .; then
      echo "  ✓ $name already populated — skipping"
    else
      echo "  + $name — adding random value"
      gcloud secrets versions add "$name" --data-file=<(openssl rand -hex 20) >/dev/null
    fi
  done
}

# Populate empty cloud-run-* secrets by deriving values from the data-vm-* secrets.
# Idempotent: skips any secret that already has a version.
# Must run after populate_secrets (data-vm-* must exist first).
# anthropic-api-key is intentionally skipped — Andrew must populate it manually.
populate_cloud_run_secrets() {
  # Pull the passwords that were already set for the data VM
  local postgres_pw neo4j_pw redis_pw
  postgres_pw=$(gcloud secrets versions access latest --secret=data-vm-postgres-password 2>/dev/null)
  neo4j_pw=$(gcloud secrets versions access latest --secret=data-vm-neo4j-password 2>/dev/null)
  redis_pw=$(gcloud secrets versions access latest --secret=data-vm-redis-password 2>/dev/null)

  if [[ -z "$postgres_pw" || -z "$neo4j_pw" || -z "$redis_pw" ]]; then
    echo "  ✗ data-vm-* secrets not populated yet — run ./infra.sh secrets first"
    return 1
  fi

  _populate_if_empty() {
    local name="$1" value="$2"
    if gcloud secrets versions list "$name" --limit=1 --format="value(name)" 2>/dev/null | grep -q .; then
      echo "  ✓ $name already populated — skipping"
    else
      echo "  + $name"
      gcloud secrets versions add "$name" --data-file=<(echo -n "$value") >/dev/null
    fi
  }

  _populate_if_empty "cloud-run-database-url" \
    "postgresql+psycopg://postgres:${postgres_pw}@10.0.0.10:5432/cu_assistant"
  _populate_if_empty "cloud-run-neo4j-password" "${neo4j_pw}"
  _populate_if_empty "cloud-run-redis-url" "redis://:${redis_pw}@10.0.0.10:6379"

  if gcloud secrets versions list "cloud-run-jwt-secret-key" --limit=1 --format="value(name)" 2>/dev/null | grep -q .; then
    echo "  ✓ cloud-run-jwt-secret-key already populated — skipping"
  else
    echo "  + cloud-run-jwt-secret-key — adding random value"
    gcloud secrets versions add "cloud-run-jwt-secret-key" \
      --data-file=<(openssl rand -hex 32) >/dev/null
  fi

  echo
  echo "  ⚠ anthropic-api-key must be populated manually (Andrew's key):"
  echo "    gcloud secrets versions add anthropic-api-key --data-file=<(echo -n 'sk-ant-...')"
}

cmd="${1:-}"

case "$cmd" in
  plan)
    terraform init -input=false
    terraform plan
    ;;
  up)
    terraform init -input=false
    terraform plan -out=tfplan
    terraform apply tfplan
    rm -f tfplan
    echo
    echo "── Populating data-vm secrets ──"
    populate_secrets
    echo
    echo "── Populating cloud-run secrets ──"
    populate_cloud_run_secrets
    echo
    echo "If data-vm secrets were just populated for the first time, reset the VM so"
    echo "startup re-fetches them:"
    echo "  gcloud compute instances reset data-services --zone=us-central1-a"
    ;;
  secrets)
    populate_secrets
    echo
    populate_cloud_run_secrets
    ;;
  down)
    terraform init -input=false
    terraform destroy -auto-approve
    echo
    check_drift
    ;;
  status)
    terraform init -input=false
    echo "── Managed resources ──"
    terraform state list
    echo
    echo "── Outputs ──"
    terraform output
    ;;
  *)
    echo "usage: $0 {plan|up|down|status|secrets}" >&2
    echo "  secrets  populate data-vm-* and cloud-run-* Secret Manager secrets" >&2
    exit 1
    ;;
esac
