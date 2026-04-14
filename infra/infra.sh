#!/usr/bin/env bash
# Local test harness for the infra Terraform.
#
# Usage:
#   ./infra.sh plan   # dry-run — no cloud changes
#   ./infra.sh up     # provision everything (plan → apply saved plan)
#   ./infra.sh down   # tear everything down
#
# Assumes `terraform` is installed and `gcloud auth application-default login`
# has been run so the GCS state backend is accessible.
#
# Firewall rules live inside a google_compute_network_firewall_policy, so
# destroy/recreate cycles do not trigger the legacy VPC firewall name-tombstone.

set -euo pipefail
cd "$(dirname "$0")"

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
    ;;
  *)
    echo "usage: $0 {plan|up|down}" >&2
    exit 1
    ;;
esac
