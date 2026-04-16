# ─────────────────────────────────────────────
# Cloud Run Service Accounts  (DEPLOY-004 / CUAI-67)
# Least-privilege service accounts for each Cloud Run service.
# Note: data-vm-sa is defined in data-vm.tf — not duplicated here.
# ─────────────────────────────────────────────

# ── course-search-api ────────────────────────────────────────────────────────

resource "google_service_account" "course_search_api" {
  account_id   = "course-search-api-sa"
  display_name = "Course Search API"
  description  = "Cloud Run: pulls images from Artifact Registry, accesses private VPC via connector"
}

# ── chat-service ─────────────────────────────────────────────────────────────

resource "google_service_account" "chat_service" {
  account_id   = "chat-service-sa"
  display_name = "Chat Service"
  description  = "Cloud Run: pulls images, accesses VPC, reads ANTHROPIC_API_KEY and runtime secrets from Secret Manager"
}

# ── frontend ──────────────────────────────────────────────────────────────────

resource "google_service_account" "frontend" {
  account_id   = "frontend-sa"
  display_name = "Frontend"
  description  = "Cloud Run: pulls nginx+static image from Artifact Registry"
}

# ── Artifact Registry reader — all three services pull images at revision deploy ──

resource "google_project_iam_member" "course_search_api_ar_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.course_search_api.email}"
}

resource "google_project_iam_member" "chat_service_ar_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.chat_service.email}"
}

resource "google_project_iam_member" "frontend_ar_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.frontend.email}"
}
