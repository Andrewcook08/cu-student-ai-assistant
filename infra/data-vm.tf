# ─────────────────────────────────────────────
# Data Services VM  (DEPLOY-002 / CUAI-65)
# e2-medium Compute Engine VM running PostgreSQL + Neo4j + Redis in Docker.
# No public IP — reachable from Cloud Run via the Serverless VPC Connector.
# Developer access via IAP: gcloud compute ssh data-services --tunnel-through-iap
# ─────────────────────────────────────────────

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
  name = "data-services-data"
  type = "pd-standard"
  zone = var.zone
  size = var.data_disk_size_gb

  depends_on = [google_project_service.apis["compute.googleapis.com"]]
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

# ── Compute Engine VM ────────────────────────────────────────────────────────

resource "google_compute_instance" "data_services" {
  name         = "data-services"
  machine_type = "e2-medium"
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 20
      type  = "pd-standard"
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
    startup-script   = file("${path.module}/scripts/data-vm-startup.sh")
    vm-assets-bucket = google_storage_bucket.vm_assets.name
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
