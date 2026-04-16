# ─────────────────────────────────────────────
# Data Services VM  (DEPLOY-002 / CUAI-65)
# e2-standard-4 Compute Engine VM running PostgreSQL + Neo4j + Redis in Docker.
# No public IP — reachable from Cloud Run via the Serverless VPC Connector.
# Developer access via IAP: gcloud compute ssh data-services --tunnel-through-iap
# ─────────────────────────────────────────────

locals {
  common_labels = {
    project    = "cu-assistant"
    service    = "data-vm"
    managed_by = "terraform"
  }
}

# ── Static internal IP ──────────────────────────────────────────────────────
# Fixed at 10.0.0.10 so DB connection strings stay stable across stop/start.

resource "google_compute_address" "data_vm" {
  name         = "data-services-ip"
  subnetwork   = google_compute_subnetwork.private.id
  address_type = "INTERNAL"
  address      = "10.0.0.10"
  region       = var.region

  depends_on = [google_project_service.apis["compute.googleapis.com"]]
}

# ── Persistent data disk ─────────────────────────────────────────────────────
# Survives VM stop/start. Startup script mounts it at /data.
# All three databases store their data here via bind mounts.

resource "google_compute_disk" "data_vm_data" {
  name   = "data-services-data"
  type   = "pd-balanced"
  zone   = var.zone
  size   = var.data_disk_size_gb
  labels = local.common_labels

  depends_on = [google_project_service.apis["compute.googleapis.com"]]
}

# ── Snapshot policy ──────────────────────────────────────────────────────────
# Daily backup with 7-day retention. Snapshots are kept even if the disk is
# deleted, protecting against accidental terraform destroy.

resource "google_compute_resource_policy" "data_vm_backup" {
  name   = "data-vm-daily-snapshot"
  region = var.region
  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = "07:00"
      }
    }
    retention_policy {
      max_retention_days    = 7
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }
    snapshot_properties {
      storage_locations = [var.region]
    }
  }
}

resource "google_compute_disk_resource_policy_attachment" "data_vm_backup" {
  name = google_compute_resource_policy.data_vm_backup.name
  disk = google_compute_disk.data_vm_data.name
  zone = var.zone
}

# ── Service account ──────────────────────────────────────────────────────────
# Least-privilege: Secret Manager reader + Monitoring writer.
# cloud-platform scope on the VM lets IAM gate all API access.

resource "google_service_account" "data_vm" {
  account_id   = "data-vm-sa"
  display_name = "Data Services VM"
  description  = "Reads secrets at boot; writes queue-depth metrics to Cloud Monitoring"
}

# ── Secret Manager shells ────────────────────────────────────────────────────
# Terraform creates the secret resources but not their values.
# Operators populate each secret before the VM is useful:
#
#   gcloud secrets versions add data-vm-postgres-password \
#     --data-file=<(openssl rand -hex 20)
#   gcloud secrets versions add data-vm-neo4j-password \
#     --data-file=<(openssl rand -hex 20)
#   gcloud secrets versions add data-vm-redis-password \
#     --data-file=<(openssl rand -hex 20)
#
# Values never enter Terraform state.

locals {
  data_vm_secret_names = [
    "data-vm-postgres-password",
    "data-vm-neo4j-password",
    "data-vm-redis-password",
  ]
}

resource "google_secret_manager_secret" "data_vm" {
  for_each  = toset(local.data_vm_secret_names)
  secret_id = each.value
  labels    = local.common_labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis["secretmanager.googleapis.com"]]
}

resource "google_secret_manager_secret_iam_member" "data_vm" {
  for_each = toset(local.data_vm_secret_names)

  secret_id = google_secret_manager_secret.data_vm[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.data_vm.email}"
}

# ── VM assets bucket ─────────────────────────────────────────────────────────
# Stores docker-compose.yml and docker-compose.prod.yml so the startup script
# pulls the real repo files rather than maintaining an inline copy.
# Terraform re-uploads on every apply — VM picks up changes on next reboot.

resource "google_storage_bucket" "vm_assets" {
  name                        = "${var.project_id}-vm-assets"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
  labels                      = local.common_labels

  public_access_prevention = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis["storage.googleapis.com"]]
}

resource "google_storage_bucket_object" "docker_compose" {
  name   = "docker-compose.yml"
  source = "${path.module}/../docker-compose.yml"
  bucket = google_storage_bucket.vm_assets.name
}

resource "google_storage_bucket_object" "docker_compose_prod" {
  name   = "docker-compose.prod.yml"
  source = "${path.module}/../docker-compose.prod.yml"
  bucket = google_storage_bucket.vm_assets.name
}

resource "google_storage_bucket_iam_member" "data_vm_assets_reader" {
  bucket = google_storage_bucket.vm_assets.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.data_vm.email}"
}

# ── Developer IAM — IAP tunnel + OS Login ────────────────────────────────────
# Codified so access survives project rebuilds.
# Populate developer_accounts in terraform.tfvars (not .example).

resource "google_project_iam_member" "iap_tunnel" {
  for_each = toset(var.developer_accounts)
  project  = var.project_id
  role     = "roles/iap.tunnelResourceAccessor"
  member   = "user:${each.value}"
}

resource "google_project_iam_member" "os_login" {
  for_each = toset(var.developer_accounts)
  project  = var.project_id
  role     = "roles/compute.osLogin"
  member   = "user:${each.value}"
}

# ── Compute Engine VM ────────────────────────────────────────────────────────

resource "google_compute_instance" "data_services" {
  name         = "data-services"
  machine_type = "e2-standard-4"
  zone         = var.zone
  labels       = local.common_labels

  deletion_protection = true

  boot_disk {
    initialize_params {
      image  = "ubuntu-os-cloud/ubuntu-2204-lts"
      size   = 20
      type   = "pd-balanced"
      labels = local.common_labels
    }
  }

  # Persistent disk attached as "data-disk" → /dev/disk/by-id/google-data-disk
  attached_disk {
    source      = google_compute_disk.data_vm_data.self_link
    device_name = "data-disk"
    mode        = "READ_WRITE"
  }

  network_interface {
    subnetwork = google_compute_subnetwork.private.id
    network_ip = google_compute_address.data_vm.address
    # No access_config block — no public IP, VPC-internal only
  }

  service_account {
    email  = google_service_account.data_vm.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script            = file("${path.module}/scripts/data-vm-startup.sh")
    vm-assets-bucket          = google_storage_bucket.vm_assets.name
    enable-oslogin            = "TRUE"
    google-logging-enabled    = "true"
    google-monitoring-enabled = "true"
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  tags = ["data-services"]

  depends_on = [
    google_project_service.apis["compute.googleapis.com"],
    google_project_service.apis["secretmanager.googleapis.com"],
    google_compute_network_firewall_policy_association.main,
    google_secret_manager_secret_iam_member.data_vm,
    google_storage_bucket_iam_member.data_vm_assets_reader,
    google_storage_bucket_object.docker_compose,
    google_storage_bucket_object.docker_compose_prod,
  ]
}

# ── Uptime / down alert ──────────────────────────────────────────────────────
# Fires if the VM has been stopped for 5+ minutes.
# Populate alert_notification_channels in terraform.tfvars.

resource "google_monitoring_alert_policy" "data_vm_down" {
  display_name = "Data VM down"
  combiner     = "OR"

  conditions {
    display_name = "VM instance stopped"
    condition_threshold {
      filter          = "metric.type=\"compute.googleapis.com/instance/uptime\" AND resource.type=\"gce_instance\" AND resource.labels.instance_id=\"${google_compute_instance.data_services.instance_id}\""
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = var.alert_notification_channels

  depends_on = [google_project_service.apis["monitoring.googleapis.com"]]
}
