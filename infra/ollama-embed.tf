# ─────────────────────────────────────────────
# Ollama Embed Service  (CUAI-88 / DEPLOY-008)
# Prebaked Cloud Run service running nomic-embed-text via Ollama.
# Callable only from course-search-api and chat-service via VPC connector.
# ADR-42: embed model is baked into the container image to avoid cold-pull latency.
# ─────────────────────────────────────────────

locals {
  image_ollama_embed = var.image_tag != "" ? "${local.image_base}/ollama-embed:${var.image_tag}" : local.placeholder_image
}

# ─────────────────────────────────────────────
# Service Account
# ─────────────────────────────────────────────

resource "google_service_account" "ollama_embed" {
  account_id   = "ollama-embed-sa"
  display_name = "Ollama Embed Service"
  description  = "Cloud Run: pulls ollama-embed image from Artifact Registry; called by course-search-api and chat-service"
}

# ─────────────────────────────────────────────
# Artifact Registry reader
# ─────────────────────────────────────────────

resource "google_project_iam_member" "ollama_embed_ar_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.ollama_embed.email}"
}

# ─────────────────────────────────────────────
# Cloud Run v2 Service
# ─────────────────────────────────────────────

resource "google_cloud_run_v2_service" "ollama_embed" {
  name     = "ollama-embed"
  location = var.region
  # INTERNAL_ONLY: this service is not exposed to the public internet.
  # It is only reachable from other Cloud Run services via the Serverless VPC Connector.
  ingress = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.ollama_embed.email
    # Ollama serializes inference per-model per-process (OLLAMA_NUM_PARALLEL=1
    # default). Setting concurrency=1 forces Cloud Run to spin up additional
    # instances under load instead of queuing requests in one container.
    max_instance_request_concurrency = 1

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    containers {
      image = local.image_ollama_embed

      ports {
        container_port = 11434
      }

      # Ollama's health endpoint — GET / returns "Ollama is running"
      startup_probe {
        http_get {
          path = "/"
          port = 11434
        }
        initial_delay_seconds = 5
        timeout_seconds       = 5
        period_seconds        = 5
        failure_threshold     = 20
      }
      liveness_probe {
        http_get {
          path = "/"
          port = 11434
        }
        period_seconds    = 30
        timeout_seconds   = 5
        failure_threshold = 3
      }

      resources {
        limits = {
          memory = "1Gi"
          cpu    = "1"
        }
        # Double CPU during cold start to keep model-load time inside the
        # AC-mandated <10s startup budget. Free to enable.
        startup_cpu_boost = true
      }
    }
  }

  lifecycle {
    # Deploy pipeline (CUAI-72) owns the image field after bootstrap.
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.apis["run.googleapis.com"],
    google_vpc_access_connector.connector,
    google_artifact_registry_repository.docker,
    google_project_iam_member.ollama_embed_ar_reader,
  ]
}

# ─────────────────────────────────────────────
# Invoker bindings
#
# The service is reachable only via `ingress = INGRESS_TRAFFIC_INTERNAL_ONLY`,
# so the network boundary — not IAM — is the effective security gate: only
# callers routing through the VPC connector (our Cloud Run services, which
# set vpc-access-egress = ALL_TRAFFIC) can reach this URL at all.
#
# With that perimeter in place we grant `allUsers` the invoker role so the
# HTTP clients in course-search-api and chat-service don't have to mint an
# ID token per request. The named SA bindings are kept for documentation:
# they declare the intended callers even though they're redundant with
# `allUsers` as long as the ingress setting stands.
#
# Invariant: if `ingress` ever changes to `INGRESS_TRAFFIC_ALL`, this
# `allUsers` binding MUST be removed — otherwise the embed model becomes
# an open, unauthenticated public endpoint.
# ─────────────────────────────────────────────

resource "google_cloud_run_v2_service_iam_member" "ollama_embed_invoker_all_internal" {
  name     = google_cloud_run_v2_service.ollama_embed.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "ollama_embed_invoker_course_search" {
  name     = google_cloud_run_v2_service.ollama_embed.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.course_search_api.email}"
}

resource "google_cloud_run_v2_service_iam_member" "ollama_embed_invoker_chat" {
  name     = google_cloud_run_v2_service.ollama_embed.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.chat_service.email}"
}
