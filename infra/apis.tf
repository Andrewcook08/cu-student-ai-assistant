# ─────────────────────────────────────────────
# GCP API Enablement
# Ensures terraform apply on a fresh project
# enables all required APIs automatically.
# ─────────────────────────────────────────────

locals {
  required_apis = [
    "compute.googleapis.com",
    "vpcaccess.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "monitoring.googleapis.com",
    "iam.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.required_apis)
  service  = each.value

  # Don't disable APIs on terraform destroy — other resources may depend on them
  disable_on_destroy = false
}
