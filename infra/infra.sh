#!/usr/bin/env bash
# Local test harness for the infra Terraform.
#
# Usage:
#   ./infra.sh plan     # dry-run — no cloud changes
#   ./infra.sh up       # provision everything (plan → apply saved plan)
#   ./infra.sh down     # tear everything down
#   ./infra.sh status   # list deployed resources + show outputs
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
    echo "usage: $0 {plan|up|down|status}" >&2
    exit 1
    ;;
esac
