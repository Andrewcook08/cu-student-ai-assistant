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
    reset_data_vm_if_needed
    ;;
  secrets)
    populate_secrets
    reset_data_vm_if_needed
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
    exit 1
    ;;
esac
