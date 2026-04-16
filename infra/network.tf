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
# Network Firewall Policy  (default-deny model)
# Uses the Network Firewall Policy API instead of legacy VPC firewall rules.
# Rules are identified by priority within the policy, not by global name —
# so destroy/recreate cycles don't collide with GCP's name-tombstone behavior.
# ─────────────────────────────────────────────

resource "google_compute_network_firewall_policy" "main" {
  name        = "cu-assistant-fw-policy"
  description = "Default-deny ingress; explicit allows for internal, IAP SSH, and VPC connector"

  depends_on = [google_project_service.apis["compute.googleapis.com"]]
}

resource "google_compute_network_firewall_policy_association" "main" {
  name              = "cu-assistant-fw-policy-assoc"
  firewall_policy   = google_compute_network_firewall_policy.main.name
  attachment_target = google_compute_network.vpc.id
}

# Cloud Run → data-services VM + ollama workers (database + inference ports only)
# Note: Neo4j HTTP browser (7474) is intentionally excluded — clients use Bolt (7687).
# Port 7474 is blocked from all sources by the default-deny rule at priority 65534.
resource "google_compute_network_firewall_policy_rule" "allow_vpc_connector" {
  firewall_policy = google_compute_network_firewall_policy.main.name
  rule_name       = "allow-vpc-connector"
  description     = "Cloud Run (via VPC connector) → backend services"
  priority        = 1000
  direction       = "INGRESS"
  action          = "allow"

  match {
    src_ip_ranges = [var.vpc_connector_range]
    layer4_configs {
      ip_protocol = "tcp"
      ports       = ["5432", "7687", "6379", "11434"]
    }
  }
}

# VM-to-VM traffic within the private subnet (data VM ↔ ollama workers, exporters)
resource "google_compute_network_firewall_policy_rule" "allow_internal" {
  firewall_policy = google_compute_network_firewall_policy.main.name
  rule_name       = "allow-internal"
  description     = "VM-to-VM traffic within the private subnet"
  priority        = 1100
  direction       = "INGRESS"
  action          = "allow"

  match {
    src_ip_ranges = ["10.0.0.0/24"]
    layer4_configs {
      ip_protocol = "all"
    }
  }
}

# Developer SSH via IAP TCP tunnel — no public IP or bastion needed (see ADR-23)
# Scoped to the data-services VM service account so future VMs are not automatically
# SSH-reachable via IAP without an explicit rule change.
resource "google_compute_network_firewall_policy_rule" "allow_iap_ssh" {
  firewall_policy         = google_compute_network_firewall_policy.main.name
  rule_name               = "allow-iap-ssh"
  description             = "Developer SSH through IAP TCP tunnel (data-services VM only)"
  priority                = 1200
  direction               = "INGRESS"
  action                  = "allow"
  target_service_accounts = [google_service_account.data_vm.email]

  match {
    src_ip_ranges = ["35.235.240.0/20"]
    layer4_configs {
      ip_protocol = "tcp"
      ports       = ["22"]
    }
  }
}

# Explicit default-deny — catches anything the allow rules above don't match
resource "google_compute_network_firewall_policy_rule" "default_deny" {
  firewall_policy = google_compute_network_firewall_policy.main.name
  rule_name       = "default-deny-ingress"
  description     = "Catch-all deny for unmatched ingress traffic"
  priority        = 65534
  direction       = "INGRESS"
  action          = "deny"

  match {
    src_ip_ranges = ["0.0.0.0/0"]
    layer4_configs {
      ip_protocol = "all"
    }
  }
}

# ─────────────────────────────────────────────
# Cloud NAT (Outbound access for private VMs)
# Allows the data-services VM to reach the internet 
# to download Docker/updates without a public IP.
# ─────────────────────────────────────────────

resource "google_compute_router" "router" {
  name    = "cu-assistant-router"
  network = google_compute_network.vpc.id
  region  = var.region
}

resource "google_compute_router_nat" "nat" {
  name                               = "cu-assistant-nat"
  router                             = google_compute_router.router.name
  region                             = google_compute_router.router.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}
