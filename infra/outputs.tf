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

output "data_vm_internal_ip" {
  description = "Internal IP of the data-services VM (use in DATABASE_URL, NEO4J_URI, REDIS_URL)"
  value       = google_compute_address.data_vm.address
}

output "frontend_url" {
  description = "Public URL of the frontend Cloud Run service (*.run.app). Printed by ./infra.sh status."
  value       = google_cloud_run_v2_service.frontend.uri
}

output "ollama_embed_url" {
  description = "Internal URL of the ollama-embed Cloud Run service (CUAI-88). Reachable only via VPC connector from course-search-api and chat-service."
  value       = google_cloud_run_v2_service.ollama_embed.uri
}
