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

# ─────────────────────────────────────────────
# Workload Identity Federation  (DEPLOY-006 / CUAI-89)
# OIDC trust between GitHub Actions and GCP — no long-lived SA keys.
# ─────────────────────────────────────────────

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  description               = "OIDC pool for GitHub Actions deploy pipeline"
  depends_on                = [google_project_service.apis["iam.googleapis.com"]]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions-provider"
  display_name                       = "GitHub Actions OIDC"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # Restrict to this repo on main only — PR tokens are rejected at the pool level.
  attribute_condition = "attribute.repository == 'Andrewcook08/cu-student-ai-assistant' && attribute.ref == 'refs/heads/main'"
  depends_on          = [google_project_service.apis["iam.googleapis.com"]]
}

# ── deploy-sa — used by GitHub Actions to push images and deploy revisions ────

resource "google_service_account" "deploy" {
  account_id   = "deploy-sa"
  display_name = "Deploy"
  description  = "GitHub Actions deploy pipeline — authenticated via WIF, no long-lived keys"
}

resource "google_project_iam_member" "deploy_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_project_iam_member" "deploy_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# deploy-sa must actAs each runtime SA when deploying new Cloud Run revisions.
resource "google_service_account_iam_member" "deploy_act_as_course_search_api" {
  service_account_id = google_service_account.course_search_api.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_service_account_iam_member" "deploy_act_as_chat_service" {
  service_account_id = google_service_account.chat_service.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_service_account_iam_member" "deploy_act_as_frontend" {
  service_account_id = google_service_account.frontend.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

# ollama_embed SA is defined in ollama-embed.tf — bind here alongside the
# other deploy_act_as_* so the full list of SAs deploy-sa can impersonate
# lives in one place.
resource "google_service_account_iam_member" "deploy_act_as_ollama_embed" {
  service_account_id = google_service_account.ollama_embed.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

# Bind the WIF pool to deploy-sa — only tokens from this repo can impersonate it.
resource "google_service_account_iam_member" "deploy_wif_binding" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.ref/refs/heads/main"
}
