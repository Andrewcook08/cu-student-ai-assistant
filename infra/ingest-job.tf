# ─────────────────────────────────────────────
# Ingest Pipeline Cloud Run Job  (CUAI-69 / DEPLOY-006)
# Runs data ingestion against the data-services VM (postgres + neo4j) and
# the ollama-embed Cloud Run service (CUAI-88). Triggered manually via:
#   gcloud run jobs execute ingest-pipeline --args="--mode=upsert" --region=us-central1
# Cloud Run Jobs provide a built-in 3-attempt retry as a second safety layer
# on top of the application-level exponential backoff.
# ─────────────────────────────────────────────

locals {
  image_ingest = var.image_tag != "" ? "${local.image_base}/ingest-pipeline:${var.image_tag}" : local.placeholder_image
}

# ─────────────────────────────────────────────
# Service Account
# ─────────────────────────────────────────────

resource "google_service_account" "ingest_job" {
  account_id   = "ingest-job-sa"
  display_name = "Ingest Pipeline Job"
  description  = "Cloud Run Job: reads secrets for DB/embed access; no public-facing role"
}

# ─────────────────────────────────────────────
# IAM — Artifact Registry reader
# ─────────────────────────────────────────────

resource "google_project_iam_member" "ingest_job_ar_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.ingest_job.email}"
}

# ─────────────────────────────────────────────
# IAM — Secret Manager accessors
# Reuses the existing cloud-run secret shells created in cloud-run.tf.
# The ingest job needs DATABASE_URL and NEO4J_PASSWORD only — not Redis or JWT.
# ─────────────────────────────────────────────

resource "google_secret_manager_secret_iam_member" "ingest_job_database_url" {
  secret_id = google_secret_manager_secret.cloud_run["cloud-run-database-url"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ingest_job.email}"
}

resource "google_secret_manager_secret_iam_member" "ingest_job_neo4j_password" {
  secret_id = google_secret_manager_secret.cloud_run["cloud-run-neo4j-password"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ingest_job.email}"
}

# ─────────────────────────────────────────────
# Cloud Run Job
# ─────────────────────────────────────────────

resource "google_cloud_run_v2_job" "ingest_pipeline" {
  name     = "ingest-pipeline"
  location = var.region

  template {
    # Cloud Run Jobs built-in retry: 3 attempts before marking the execution failed.
    # Application-level retry (exponential backoff) runs inside each attempt.
    task_count   = 1
    parallelism  = 1

    template {
      service_account = google_service_account.ingest_job.email
      max_retries     = 3
      timeout         = "3600s"

      # ALL_TRAFFIC: routes all egress through the VPC connector so the job
      # can reach both the data-services VM (10.0.0.10) and the internal-only
      # ollama-embed Cloud Run service.
      vpc_access {
        connector = google_vpc_access_connector.connector.id
        egress    = "ALL_TRAFFIC"
      }

      containers {
        image = local.image_ingest

        resources {
          limits = {
            memory = "1Gi"
            cpu    = "1"
          }
        }

        # ── Non-sensitive config ──────────────────────────────────────────
        env {
          name  = "ENVIRONMENT"
          value = "production"
        }
        env {
          name  = "NEO4J_URI"
          value = "bolt://${local.data_vm_ip}:7687"
        }
        env {
          name  = "NEO4J_USER"
          value = "neo4j"
        }
        env {
          name  = "OLLAMA_URL"
          value = local.ollama_embed_url_effective
        }
        env {
          name  = "OLLAMA_EMBED_MODEL"
          value = "nomic-embed-text"
        }
        # Unused by ingest but required by shared/config.py Settings model
        env {
          name  = "REDIS_URL"
          value = "redis://${local.data_vm_ip}:6379"
        }
        env {
          name  = "CORS_ORIGINS"
          value = "https://unused"
        }
        env {
          name  = "ANTHROPIC_MODEL"
          value = var.anthropic_model
        }
        env {
          name  = "JWT_SECRET_KEY"
          value = "unused-by-ingest-job"
        }

        # ── Sensitive config — sourced from Secret Manager ────────────────
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.cloud_run["cloud-run-database-url"].secret_id
              version = "latest"
            }
          }
        }
        env {
          name = "NEO4J_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.cloud_run["cloud-run-neo4j-password"].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.apis["run.googleapis.com"],
    google_vpc_access_connector.connector,
    google_artifact_registry_repository.docker,
    google_project_iam_member.ingest_job_ar_reader,
    google_secret_manager_secret_iam_member.ingest_job_database_url,
    google_secret_manager_secret_iam_member.ingest_job_neo4j_password,
  ]
}
