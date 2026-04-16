# ─────────────────────────────────────────────
# Cloud Run Services  (DEPLOY-004 / CUAI-67)
# Three services: course-search-api, chat-service, frontend.
# All connect to the data-services VM via the Serverless VPC Connector.
# Sensitive env vars are sourced from Secret Manager — Terraform creates the
# secret shells; operators populate the values before running terraform apply:
#
#   # Database connection string (embed the data VM internal IP 10.0.0.10)
#   gcloud secrets versions add cloud-run-database-url \
#     --data-file=<(echo -n "postgresql+psycopg://postgres:STRONG_PW@10.0.0.10:5432/cu_assistant")
#
#   gcloud secrets versions add cloud-run-neo4j-password \
#     --data-file=<(echo -n "STRONG_NEO4J_PW")
#
#   gcloud secrets versions add cloud-run-redis-url \
#     --data-file=<(echo -n "redis://:STRONG_REDIS_PW@10.0.0.10:6379")
#
#   gcloud secrets versions add cloud-run-jwt-secret-key \
#     --data-file=<(openssl rand -hex 32)
#
#   # ANTHROPIC_API_KEY — Andrew populates this; do NOT share the value.
#   # Only chat-service-sa has secretAccessor on this secret.
#   gcloud secrets versions add anthropic-api-key \
#     --data-file=<(echo -n "sk-ant-…")
# ─────────────────────────────────────────────

locals {
  # Artifact Registry image base path — all services share the same repo
  image_base = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"

  # Data VM internal IP — resolved from the static address resource in data-vm.tf
  data_vm_ip = google_compute_address.data_vm.address

  # Placeholder image used on first apply before real images are pushed to Artifact Registry.
  # CI replaces this by running `gcloud run deploy --image=...` after pushing to AR.
  placeholder_image = "us-docker.pkg.dev/cloudrun/container/hello:latest"

  # Per-service image: use real image if image_tag is set, otherwise placeholder
  image_course_search_api = var.image_tag != "" ? "${local.image_base}/course-search-api:${var.image_tag}" : local.placeholder_image
  image_chat_service      = var.image_tag != "" ? "${local.image_base}/chat-service:${var.image_tag}" : local.placeholder_image
  image_frontend          = var.image_tag != "" ? "${local.image_base}/frontend:${var.image_tag}" : local.placeholder_image
}

# ─────────────────────────────────────────────
# Secret Manager — runtime secrets
# Shells only. Values must be populated by the operator before services boot.
# ─────────────────────────────────────────────

locals {
  cloud_run_secret_names = [
    "cloud-run-database-url",
    "cloud-run-neo4j-password",
    "cloud-run-redis-url",
    "cloud-run-jwt-secret-key",
  ]
}

resource "google_secret_manager_secret" "cloud_run" {
  for_each  = toset(local.cloud_run_secret_names)
  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis["secretmanager.googleapis.com"]]
}

# ANTHROPIC_API_KEY — separate resource so IAM binding is scoped only to
# chat-service-sa. Andrew's personal billing key; team members must not have
# secretAccessor on this secret. See Jira comment 11205.
resource "google_secret_manager_secret" "anthropic_key" {
  secret_id = "anthropic-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis["secretmanager.googleapis.com"]]
}

# ── Secret Manager IAM ───────────────────────────────────────────────────────
# Both app service accounts need the runtime secrets (DB URL, Neo4j pw, Redis URL, JWT).
# Bindings are listed explicitly — for_each on SA emails would fail because those
# resource attributes are not known until apply time.

resource "google_secret_manager_secret_iam_member" "course_search_api_database_url" {
  secret_id = google_secret_manager_secret.cloud_run["cloud-run-database-url"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.course_search_api.email}"
}

resource "google_secret_manager_secret_iam_member" "course_search_api_neo4j_password" {
  secret_id = google_secret_manager_secret.cloud_run["cloud-run-neo4j-password"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.course_search_api.email}"
}

resource "google_secret_manager_secret_iam_member" "course_search_api_redis_url" {
  secret_id = google_secret_manager_secret.cloud_run["cloud-run-redis-url"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.course_search_api.email}"
}

resource "google_secret_manager_secret_iam_member" "course_search_api_jwt_secret" {
  secret_id = google_secret_manager_secret.cloud_run["cloud-run-jwt-secret-key"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.course_search_api.email}"
}

resource "google_secret_manager_secret_iam_member" "chat_service_database_url" {
  secret_id = google_secret_manager_secret.cloud_run["cloud-run-database-url"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.chat_service.email}"
}

resource "google_secret_manager_secret_iam_member" "chat_service_neo4j_password" {
  secret_id = google_secret_manager_secret.cloud_run["cloud-run-neo4j-password"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.chat_service.email}"
}

resource "google_secret_manager_secret_iam_member" "chat_service_redis_url" {
  secret_id = google_secret_manager_secret.cloud_run["cloud-run-redis-url"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.chat_service.email}"
}

resource "google_secret_manager_secret_iam_member" "chat_service_jwt_secret" {
  secret_id = google_secret_manager_secret.cloud_run["cloud-run-jwt-secret-key"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.chat_service.email}"
}

# ANTHROPIC_API_KEY — chat-service-sa ONLY (ADR per Jira comment 11205)
# course-search-api imports shared.config which also has anthropic_api_key as a required
# field — if that causes a boot failure the fix is to make the field Optional in shared/config.py.
# The Anthropic key itself is only needed at runtime by chat-service.
resource "google_secret_manager_secret_iam_member" "chat_service_anthropic" {
  secret_id = google_secret_manager_secret.anthropic_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.chat_service.email}"
}

# ─────────────────────────────────────────────
# Cloud Run — frontend
# Nginx serving the compiled Vue static files.
# Public ingress (INGRESS_TRAFFIC_ALL) — user browsers connect directly.
# Port 8080: nginx runs as non-root (USER nginx, per PR #119 container hardening).
# ─────────────────────────────────────────────

resource "google_cloud_run_v2_service" "frontend" {
  name     = "frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account                  = google_service_account.frontend.email
    max_instance_request_concurrency = 200

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = local.image_frontend

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          memory = "256Mi"
          cpu    = "1"
        }
        # cpu_idle = true: throttle CPU when not handling requests.
        # Required to use 256Mi — Cloud Run enforces ≥512Mi when CPU is always allocated.
        cpu_idle = true
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.apis["run.googleapis.com"],
    google_artifact_registry_repository.docker,
    google_project_iam_member.frontend_ar_reader,
  ]
}

# Allow unauthenticated browser access to the frontend
resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  name     = google_cloud_run_v2_service.frontend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ─────────────────────────────────────────────
# Cloud Run — course-search-api
# Stateless REST API. Public ingress (login/register are public endpoints).
# VPC connector routes private-range traffic to the data-services VM.
# Port 8000, concurrency 80, scale-to-zero.
# ─────────────────────────────────────────────

resource "google_cloud_run_v2_service" "course_search_api" {
  name     = "course-search-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account                  = google_service_account.course_search_api.email
    max_instance_request_concurrency = 80

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = local.image_course_search_api

      ports {
        container_port = 8000
      }

      startup_probe {
        http_get {
          path = "/api/health"
          port = 8000
        }
        initial_delay_seconds = 5
        timeout_seconds       = 5
        period_seconds        = 5
        failure_threshold     = 20
      }
      liveness_probe {
        http_get {
          path = "/api/health"
          port = 8000
        }
        period_seconds    = 30
        timeout_seconds   = 5
        failure_threshold = 3
      }

      resources {
        limits = {
          memory = "512Mi"
          cpu    = "1"
        }
      }

      # ── Non-sensitive config ──────────────────────────────────────────────
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
        value = var.ollama_embed_url
      }
      env {
        name  = "OLLAMA_EMBED_MODEL"
        value = "nomic-embed-text"
      }
      env {
        name  = "CORS_ORIGINS"
        value = google_cloud_run_v2_service.frontend.uri
      }
      env {
        name  = "ANTHROPIC_MODEL"
        value = var.anthropic_model
      }

      # ── Sensitive config — sourced from Secret Manager ────────────────────
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
      env {
        name = "REDIS_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.cloud_run["cloud-run-redis-url"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "JWT_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.cloud_run["cloud-run-jwt-secret-key"].secret_id
            version = "latest"
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.apis["run.googleapis.com"],
    google_vpc_access_connector.connector,
    google_artifact_registry_repository.docker,
    google_project_iam_member.course_search_api_ar_reader,
    google_secret_manager_secret_iam_member.course_search_api_database_url,
    google_secret_manager_secret_iam_member.course_search_api_neo4j_password,
    google_secret_manager_secret_iam_member.course_search_api_redis_url,
    google_secret_manager_secret_iam_member.course_search_api_jwt_secret,
  ]
}

# Allow unauthenticated invocations (auth is handled by JWT middleware in the app)
resource "google_cloud_run_v2_service_iam_member" "course_search_api_public" {
  name     = google_cloud_run_v2_service.course_search_api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ─────────────────────────────────────────────
# Cloud Run — chat-service
# Chat engine (LangGraph + Anthropic API). WebSocket + REST.
# Ingress: INGRESS_TRAFFIC_ALL — browser connects directly (no BFF in this project).
# ADR-33 AC: "internal-and-cloud-load-balancing if a BFF fronts it — otherwise
# document why public is acceptable." Since this project has no BFF and the browser
# must reach the chat WebSocket directly, INGRESS_TRAFFIC_ALL is required.
# JWT authentication in the app provides the access control layer.
# min_instance_count = 1 to avoid cold-start latency on WebSocket connections.
# ─────────────────────────────────────────────

resource "google_cloud_run_v2_service" "chat_service" {
  name     = "chat-service"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account                  = google_service_account.chat_service.email
    max_instance_request_concurrency = 15
    timeout                          = "3600s" # 60 min — max for Cloud Run; WebSocket lifetime cap

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    scaling {
      min_instance_count = 1
      max_instance_count = 5
    }

    containers {
      image = local.image_chat_service

      ports {
        container_port = 8001
      }

      startup_probe {
        http_get {
          path = "/api/chat/health"
          port = 8001
        }
        initial_delay_seconds = 5
        timeout_seconds       = 5
        period_seconds        = 5
        failure_threshold     = 20
      }
      liveness_probe {
        http_get {
          path = "/api/chat/health"
          port = 8001
        }
        period_seconds    = 30
        timeout_seconds   = 5
        failure_threshold = 3
      }

      resources {
        limits = {
          memory = "512Mi"
          cpu    = "1"
        }
      }

      # ── Non-sensitive config ──────────────────────────────────────────────
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
        value = var.ollama_embed_url
      }
      env {
        name  = "OLLAMA_EMBED_MODEL"
        value = "nomic-embed-text"
      }
      env {
        name  = "ANTHROPIC_MODEL"
        value = var.anthropic_model
      }
      env {
        name  = "CORS_ORIGINS"
        value = google_cloud_run_v2_service.frontend.uri
      }

      # ── Sensitive config — sourced from Secret Manager ────────────────────
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
      env {
        name = "REDIS_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.cloud_run["cloud-run-redis-url"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "JWT_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.cloud_run["cloud-run-jwt-secret-key"].secret_id
            version = "latest"
          }
        }
      }
      # ANTHROPIC_API_KEY — injected from Secret Manager (Andrew's key, not shared with team)
      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.anthropic_key.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.apis["run.googleapis.com"],
    google_vpc_access_connector.connector,
    google_artifact_registry_repository.docker,
    google_project_iam_member.chat_service_ar_reader,
    google_secret_manager_secret_iam_member.chat_service_database_url,
    google_secret_manager_secret_iam_member.chat_service_neo4j_password,
    google_secret_manager_secret_iam_member.chat_service_redis_url,
    google_secret_manager_secret_iam_member.chat_service_jwt_secret,
    google_secret_manager_secret_iam_member.chat_service_anthropic,
  ]
}

# Browser WebSocket connections need unauthenticated Cloud Run invocation (no GCP-level auth).
# App-level JWT (SEC-005 / ADR-33) is the access control layer on every route.
resource "google_cloud_run_v2_service_iam_member" "chat_service_public" {
  name     = google_cloud_run_v2_service.chat_service.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
