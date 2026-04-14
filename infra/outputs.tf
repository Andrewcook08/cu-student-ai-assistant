output "vpc_name" {
  description = "VPC network name"
  value       = google_compute_network.vpc.name
}

output "vpc_self_link" {
  description = "VPC network self-link (used by subnetworks and firewall rules)"
  value       = google_compute_network.vpc.self_link
}

output "subnet_self_link" {
  description = "Private subnet self-link (used by Compute Engine VM and MIG)"
  value       = google_compute_subnetwork.private.self_link
}

output "vpc_connector_id" {
  description = "Serverless VPC Connector ID (referenced by Cloud Run services)"
  value       = google_vpc_access_connector.connector.id
}

output "vpc_connector_name" {
  description = "Serverless VPC Connector name"
  value       = google_vpc_access_connector.connector.name
}
