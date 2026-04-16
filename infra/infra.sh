#!/usr/bin/env bash
# Local test harness for the infra Terraform.
#
# Usage:
#   ./infra.sh plan     # dry-run — no cloud changes
#   ./infra.sh up       # provision everything (plan → apply saved plan)
#   ./infra.sh down     # tear everything down
#   ./infra.sh status   # list deployed resources + show outputs
#   ./infra.sh secrets  # populate empty data-vm-* and cloud-run-* secrets
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

# Flips to 1 whenever populate_secrets adds a new version to any data-vm-*
# secret. Used by reset_data_vm_if_needed to decide whether the VM boot ran
# with empty secrets and therefore needs a reset. Never touched by the
# cloud-run-* populator — those secrets are read by Cloud Run at revision
# boot, not by the VM startup script.
DATA_VM_SECRETS_ADDED=0

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
      DATA_VM_SECRETS_ADDED=1
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

  local data_vm_ip
  data_vm_ip=$(terraform output -raw data_vm_internal_ip)

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
    "postgresql+psycopg://postgres:${postgres_pw}@${data_vm_ip}:5432/cu_assistant"
  _populate_if_empty "cloud-run-neo4j-password" "${neo4j_pw}"
  _populate_if_empty "cloud-run-redis-url" "redis://:${redis_pw}@${data_vm_ip}:6379"

  if gcloud secrets versions list "cloud-run-jwt-secret-key" --limit=1 --format="value(name)" 2>/dev/null | grep -q .; then
    echo "  ✓ cloud-run-jwt-secret-key already populated — skipping"
  else
    echo "  + cloud-run-jwt-secret-key — adding random value"
    gcloud secrets versions add "cloud-run-jwt-secret-key" \
      --data-file=<(openssl rand -hex 32) >/dev/null
  fi

  # anthropic-api-key needs a version so Cloud Run chat-service can create
  # its revision (the env block references versions/latest). Seed a placeholder
  # only — Andrew must overwrite with the real key before chat-service can
  # pass validate_production() on a real image.
  if gcloud secrets versions list "anthropic-api-key" --limit=1 --format="value(name)" 2>/dev/null | grep -q .; then
    echo "  ✓ anthropic-api-key already populated — skipping"
  else
    echo "  + anthropic-api-key — seeding placeholder (Andrew must overwrite)"
    gcloud secrets versions add "anthropic-api-key" \
      --data-file=<(echo -n "PLACEHOLDER_REPLACE_WITH_REAL_KEY") >/dev/null
  fi

  echo
  echo "  ⚠ anthropic-api-key placeholder must be replaced with Andrew's real key:"
  echo "    gcloud secrets versions add anthropic-api-key --data-file=<(echo -n 'sk-ant-...')"
}

# Reset the data VM so its startup script re-runs against the now-populated
# secrets. Only needed when populate_secrets actually added versions: on a
# fresh `./infra.sh up` the VM boots during `terraform apply` before the
# shells have values, so its docker-compose stack fails to start. On re-apply
# of a healthy stack, populate_secrets skips everything and this is a no-op,
# so we don't pointlessly power-cycle the VM.
reset_data_vm_if_needed() {
  if [[ $DATA_VM_SECRETS_ADDED -eq 1 ]]; then
    echo
    echo "── Resetting data-services VM so startup script re-fetches secrets ──"
    gcloud compute instances reset data-services --zone=us-central1-a
  fi
}

# Disable deletion protection on the data-services VM so `terraform destroy`
# can delete it. The VM carries deletion_protection=true in Terraform as a
# safety net against accidental destroys from the console; we flip it off
# just-in-time during `./infra.sh down` so an intentional teardown still works.
# No-op if the VM doesn't exist (clean state, or down already ran).
disable_vm_deletion_protection() {
  if gcloud compute instances describe data-services \
      --zone=us-central1-a --format="value(name)" &>/dev/null; then
    echo "── Disabling deletion protection on data-services VM ──"
    gcloud compute instances update data-services \
      --zone=us-central1-a --no-deletion-protection >/dev/null
  fi
}

# Delete all snapshots of the data-services-data disk so nothing billable
# survives `./infra.sh down`. Terraform's snapshot policy sets
# KEEP_AUTO_SNAPSHOTS on disk delete — useful for an ongoing project, but
# this is a school project where "down" must reach $0. Matches by the
# source-disk name so we only touch snapshots our stack produced.
delete_data_vm_snapshots() {
  local names
  names=$(gcloud compute snapshots list \
    --filter="sourceDisk~data-services-data" \
    --format="value(name)" 2>/dev/null || true)
  if [[ -n "$names" ]]; then
    echo "── Deleting data VM snapshots ──"
    echo "$names" | xargs -r gcloud compute snapshots delete --quiet
  fi
}

cmd="${1:-}"

case "$cmd" in
  plan)
    terraform init -input=false
    terraform plan
    ;;
  up)
    terraform init -input=false

    # Three-phase apply: Cloud Run services reference cloud-run-*/versions/latest
    # in their env_from blocks, and Cloud Run refuses to create a revision when
    # the referenced version doesn't exist. `populate_cloud_run_secrets` can't
    # run until the secret shells exist and the data_vm_internal_ip output is
    # populated. So the order must be:
    #   1. Create the minimum needed to populate secrets: secret shells + IP.
    #   2. Populate all secret versions.
    #   3. Apply everything else — VM, Cloud Run services, IAM bindings.
    echo "── Phase 1: secret shells + static IP ──"
    terraform apply -auto-approve \
      -target=google_compute_address.data_vm \
      -target=google_secret_manager_secret.data_vm \
      -target=google_secret_manager_secret.cloud_run \
      -target=google_secret_manager_secret.anthropic_key

    echo
    echo "── Phase 2: populating secret versions ──"
    populate_secrets
    echo
    populate_cloud_run_secrets

    echo
    echo "── Phase 3: provisioning VM + Cloud Run + IAM ──"
    terraform apply -auto-approve

    reset_data_vm_if_needed
    ;;
  secrets)
    populate_secrets
    echo
    populate_cloud_run_secrets
    reset_data_vm_if_needed
    ;;
  down)
    terraform init -input=false
    disable_vm_deletion_protection
    terraform destroy -auto-approve
    echo
    delete_data_vm_snapshots
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
