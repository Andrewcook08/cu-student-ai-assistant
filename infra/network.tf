# ─────────────────────────────────────────────
# VPC Network
# ─────────────────────────────────────────────

resource "google_compute_network" "vpc" {
  name                    = "cu-assistant-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.apis["compute.googleapis.com"]]
}

# Private subnet — all VMs land here, no public IPs
resource "google_compute_subnetwork" "private" {
  name          = "cu-assistant-private"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

# ─────────────────────────────────────────────
# Serverless VPC Connector
# Bridges Cloud Run (serverless) → private VPC
# ─────────────────────────────────────────────

resource "google_vpc_access_connector" "connector" {
  name          = "cu-assistant-connector"
  region        = var.region
  ip_cidr_range = var.vpc_connector_range
  network       = google_compute_network.vpc.name

  depends_on = [google_project_service.apis["vpcaccess.googleapis.com"]]
}

# ─────────────────────────────────────────────
# Firewall Rules  (default-deny model)
# ─────────────────────────────────────────────

# Cloud Run → data-services VM + ollama workers (database + inference ports only)
resource "google_compute_firewall" "allow_vpc_connector" {
  name    = "allow-vpc-connector"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["5432", "7687", "6379", "11434"]
  }

  source_ranges = [var.vpc_connector_range]
}

# VM-to-VM traffic within the private subnet (data VM ↔ ollama workers, queue-depth-exporter → Redis)
resource "google_compute_firewall" "allow_internal" {
  name    = "allow-internal"
  network = google_compute_network.vpc.name

  allow {
    protocol = "all"
  }

  source_ranges = ["10.0.0.0/24"]
}

# Developer SSH via IAP TCP tunnel — no public IP or bastion needed (see ADR-23)
resource "google_compute_firewall" "allow_iap_ssh" {
  name    = "allow-iap-ssh"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # Google's IAP IP range — all IAP tunnel traffic originates here
  source_ranges = ["35.235.240.0/20"]
}

# Block everything else — lowest priority, catches anything not matched above
resource "google_compute_firewall" "default_deny" {
  name     = "default-deny-ingress"
  network  = google_compute_network.vpc.name
  priority = 65534

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]
}
