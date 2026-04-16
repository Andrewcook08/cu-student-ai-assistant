# Infra Runbook

Terraform + a thin shell wrapper (`infra.sh`) that provisions the full GCP stack for cu-student-ai-assistant. Designed to be **fully ephemeral**: `./infra.sh down` leaves zero paid resources behind, `./infra.sh up` brings everything back from scratch.

## Architecture in one paragraph

One project, one region (`us-central1`). Three Cloud Run app services (`course-search-api`, `chat-service`, `frontend`) and one Cloud Run embed service (`ollama-embed`, CUAI-88), all reaching the databases on a single `data-services` Compute Engine VM through a Serverless VPC Connector. Images live in an Artifact Registry Docker repo (`cu-assistant`). Secrets live in Secret Manager — Terraform creates the shells, values are populated by the script or by hand. The GitHub Actions deploy pipeline (CUAI-72) owns all image builds, pushes, and Cloud Run revision updates via Workload Identity Federation (CUAI-89); Terraform never sees an image tag after the first apply.

## Responsibility split

| Owner | Responsibility |
|---|---|
| **Terraform (`./infra.sh up`)** | VM, VPC, connector, Cloud Run service **shells**, secret **shells**, IAM, Artifact Registry repo |
| **`./infra.sh` populate steps** | Random passwords for data-vm-*, derived connection strings for cloud-run-* |
| **Operator (one paste)** | `anthropic-api-key` value — Andrew's personal key, not in Terraform state |
| **Deploy pipeline (CUAI-72)** | Build Docker images, push to Artifact Registry, update Cloud Run revisions with real image tags |

Images are deliberately **not** Terraform's concern after bootstrap. Every Cloud Run service uses a lifecycle rule to ignore changes to the image field:

```hcl
resource "google_cloud_run_v2_service" "chat_service" {
  # ...
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}
```

Without that rule, running `./infra.sh up` after a pipeline deploy reverts every service back to the placeholder image. The placeholder (`us-docker.pkg.dev/cloudrun/container/hello`) is what Cloud Run serves **only** between `terraform apply` and the first pipeline run.

## Fresh spin-up runbook

Five steps. Takes ~8 minutes total, most of it waiting for Cloud Run revisions.

### 1. `./infra.sh up`

Creates everything: VM, VPC, connector, AR repo, Cloud Run service shells (on placeholder image), secret shells. Auto-populates `data-vm-*` and `cloud-run-*` secrets with random values and derived connection strings. Prints a reminder about the Anthropic key.

Expected end state: three Cloud Run services alive and serving the GCP hello page at their `.run.app` URLs. `ollama-embed` fails to pull (no image yet) — that's fine, the pipeline will fix it in step 4.

### 2. Paste the Anthropic key

```bash
gcloud secrets versions add anthropic-api-key \
  --data-file=<(echo -n "sk-ant-…")
```

Only Andrew needs to do this. `chat-service-sa` is the only identity with `roles/secretmanager.secretAccessor` on this secret (ADR per Jira comment 11205).

Until this step runs, the pipeline's real `chat-service` revision will boot-fail at `validate_production()`. The placeholder hello revision is unaffected (it doesn't read `shared.config`).

### 3. Reset the data VM so it re-fetches its secrets

```bash
gcloud compute instances reset data-services --zone=us-central1-a
```

Only needed on the **first** spin-up of a new GCP project, or after rotating `data-vm-*` secrets. Subsequent teardown/up cycles reuse the same VM image so the startup script re-fetches on every boot anyway.

### 4. Trigger the deploy pipeline

```bash
gh workflow run deploy.yml
```

The pipeline (CUAI-72) builds the four images, pushes them to `us-central1-docker.pkg.dev/PROJECT/cu-assistant`, and calls `gcloud run services update --image=…` on each service. New revisions replace the placeholder (or missing) images. This step is **required** on every fresh spin-up — a teardown destroys the Artifact Registry repo along with every image.

Typical wall-clock: ~4 minutes for the full pipeline.

### 5. Verify

```bash
terraform output frontend_url
curl -sI "$(terraform output -raw frontend_url)"

gcloud run services describe chat-service --region=us-central1 \
  --format="value(status.url)"
# Visit the frontend URL — you should hit the real login page, not the GCP hello page.
```

## Teardown

```bash
./infra.sh down
```

Destroys everything, including:

- The Artifact Registry repo and all images in it
- All Secret Manager secret shells **and their values** (including the Anthropic key)
- The data VM (but its persistent disk is snapshotted daily — see `data-vm.tf`; snapshots survive destroy)
- All Cloud Run services and their revision history

After this runs, the GCP project has no paid resources. The drift check at the end of the script catches anything Terraform missed and fails loudly.

**Before tearing down for the last time**, note:

- Snapshots of the data VM disk persist by design. If you truly want zero residual cost, delete them manually: `gcloud compute snapshots list --filter="sourceDisk~data-services-data" --format="value(name)" | xargs -r gcloud compute snapshots delete --quiet`.
- The GCS Terraform state bucket is not managed by this module. If you're done forever, `gsutil rm -r gs://<state-bucket>`.

## Manual steps, in one place

These cannot be scripted away by design — they're the only things between the checked-in code and a fully provisioned stack.

1. **First-time setup only** — `gcloud auth application-default login` and point `backend.tf` at your Terraform state bucket.
2. **Every fresh spin-up** — paste the Anthropic key (step 2 above).
3. **Every fresh spin-up** — trigger `deploy.yml` (step 4 above).

## Drift, state, and the image field

Two Terraform-vs-reality conflicts can happen. Both are resolved by `ignore_changes` + the ephemeral model:

| Field | Managed by | Why Terraform ignores it |
|---|---|---|
| `template[0].containers[0].image` | Deploy pipeline | The pipeline is the only thing that knows which image tag is current. Terraform's view is always "whatever was set at last apply" and will drift from reality the moment the pipeline runs. |
| Secret **values** | `populate_*_secrets` + operator | Terraform only manages the secret resource; versions are created out-of-band so values never enter state. |

Any other drift (env vars, concurrency, probes, IAM) should round-trip through Terraform — don't edit Cloud Run services in the console.

## File map

| File | Purpose |
|---|---|
| `main.tf` | Provider + backend config |
| `variables.tf` | `project_id`, `region`, `image_tag`, `ollama_embed_url`, etc. |
| `outputs.tf` | `frontend_url`, `data_vm_internal_ip`, `workload_identity_provider` (CUAI-89), `deploy_sa_email` (CUAI-89) |
| `apis.tf` | Enables required Google APIs |
| `network.tf` | VPC + subnet + serverless VPC connector + firewall policy |
| `data-vm.tf` | Compute Engine VM + persistent disk + snapshot policy + startup script |
| `scripts/data-vm-startup.sh` | Runs on VM boot; pulls secrets, brings up docker-compose stack |
| `artifact-registry.tf` | `cu-assistant` Docker repo |
| `cloud-run.tf` | Three Cloud Run services + Secret Manager shells + IAM bindings |
| `iam.tf` | Runtime service accounts + AR reader + (CUAI-89) WIF pool/provider + `deploy-sa` |
| `infra.sh` | `plan` / `up` / `down` / `status` / `secrets` wrapper |
| `terraform.tfvars.example` | Copy to `terraform.tfvars` and fill in `project_id` + secret-population commands |
