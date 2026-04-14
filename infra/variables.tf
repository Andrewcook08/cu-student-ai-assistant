variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "vpc_connector_range" {
  description = "IP range for the Serverless VPC Connector (/28, must not overlap with 10.0.0.0/24)"
  type        = string
  default     = "10.8.0.0/28"
}
