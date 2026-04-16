# ─────────────────────────────────────────────
# Artifact Registry  (DEPLOY-005)
# Docker repository for all Cloud Run service images.
# Images are pushed here by CI (deploy.yml) and pulled by Cloud Run at boot.
# ─────────────────────────────────────────────

resource "google_artifact_registry_repository" "docker" {
  repository_id = "cu-assistant"
  location      = var.region
  format        = "DOCKER"
  description   = "Docker images for Cloud Run services (course-search-api, chat-service, frontend)"

  depends_on = [google_project_service.apis["artifactregistry.googleapis.com"]]
}
