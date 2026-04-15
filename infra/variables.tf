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

variable "data_disk_size_gb" {
  description = "Size in GB of the persistent data disk attached to the data-services VM"
  type        = number
  default     = 50
}

variable "developer_accounts" {
  description = "List of developer Google accounts (user:email) to grant IAP tunnel + OS Login access"
  type        = list(string)
  default     = []
}

variable "alert_notification_channels" {
  description = "List of Cloud Monitoring notification channel resource names for VM alerts"
  type        = list(string)
  default     = []
}
