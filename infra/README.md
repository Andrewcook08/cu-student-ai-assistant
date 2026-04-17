# Infra Runbook

Terraform + a thin shell wrapper (`infra.sh`) that provisions the full GCP stack for cu-student-ai-assistant. Designed to be **fully ephemeral**: `./infra.sh down` leaves zero paid resources behind, `./infra.sh up` brings everything back from scratch.

## Architecture in one paragraph

One project, one region (`us-central1`). Three Cloud Run app services (`course-search-api`, `chat-service`, `frontend`) and one Cloud Run embed service (`ollama-embed`, CUAI-88), all reaching the databases on a single `data-services` Compute Engine VM through a Serverless VPC Connector. Images live in an Artifact Registry Docker repo (`cu-assistant`). Secrets live in Secret Manager — Terraform creates the shells, values are populated by the script or by hand. The GitHub Actions deploy pipeline (CUAI-72) owns all image builds, pushes, and Cloud Run revision updates via Workload Identity Federation (CUAI-89); Terraform never sees an image tag after the first apply.

## Responsibility split

| Owner | Responsibility |
|---|---|
| **Terraform (`./infra.sh up`)** | VM, VPC, connector, Cloud Run service **shells**, secret **shells**, IAM, Artifact Registry repo |
| **`./infra.sh` populate steps** | Random passwords for data-vm-*, derived connection strings for cloud-run-*, **placeholder** for anthropic-api-key |
| **Operator (one paste)** | Real `anthropic-api-key` value — overwrites the placeholder; Andrew's personal key, not in Terraform state |
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

Five steps. Takes ~20 minutes total end-to-end, most of it waiting for Cloud Run revisions and the embeddings step of ingest.

### 1. `./infra.sh up`

Creates everything: VM, VPC, connector, AR repo, Cloud Run service shells (on placeholder image), Cloud Run Job shell (ingest-pipeline, also on placeholder image), secret shells. Auto-populates `data-vm-*` and `cloud-run-*` secrets with random values and derived connection strings. Seeds `anthropic-api-key` with a placeholder string — this is required because Cloud Run refuses to create a revision that references a non-existent secret version. If any `data-vm-*` secret was newly populated this run, auto-resets the data VM so its startup script re-fires against the now-filled secrets and brings the Postgres / Neo4j / Redis docker-compose stack up.

Runs as a three-phase apply (secret shells + IP → populate versions → full apply) so Cloud Run can resolve `versions/latest` at revision-create time.

Expected end state: three Cloud Run services alive and serving the GCP hello page at their `.run.app` URLs, data VM running with all three databases healthy, `ingest-pipeline` Job provisioned with the placeholder image. `ollama-embed` fails to pull (no image yet) — that's fine, the pipeline will fix it in step 3.

### 2. Overwrite the Anthropic key placeholder

```bash
gcloud secrets versions add anthropic-api-key \
  --data-file=<(echo -n "sk-ant-…")
```

Only Andrew needs to do this. `chat-service-sa` is the only identity with `roles/secretmanager.secretAccessor` on this secret (ADR per Jira comment 11205).

**Order matters: this must run before step 3.** Cloud Run resolves `versions/latest` at revision-create time and bakes the value into the revision. If the pipeline creates a new revision while the placeholder is still `latest`, `chat-service` boot-fails at `validate_production()` and you'd need to force another revision to pick up the real key. The placeholder hello revision from step 1 is unaffected (it doesn't read `shared.config`).

### 3. Trigger the deploy pipeline

```bash
gh workflow run deploy.yml
```

The pipeline (CUAI-72) builds all five images (four services + ingest-pipeline), pushes them to `us-central1-docker.pkg.dev/PROJECT/cu-assistant`, calls `gcloud run services update --image=…` on each service, and `gcloud run jobs update --image=…` on the ingest-pipeline Job. New revisions replace the placeholder (or missing) images. This step is **required** on every fresh spin-up — a teardown destroys the Artifact Registry repo along with every image.

Typical wall-clock: ~5–8 minutes for the full pipeline.

### 4. `./infra.sh ingest`

```bash
./infra.sh ingest
```

Executes the `ingest-pipeline` Cloud Run Job in `--mode=upsert` and streams to completion. Loads the CU course catalog (3410 courses, 203 programs, prereq graph, embeddings) into Postgres + Neo4j. Pre-flight check bails out if the Job is still on the placeholder image, so you'll get a clear error if step 3 hasn't finished yet.

Typical wall-clock: ~5 minutes (embeddings dominate; one Ollama call per course).

See [Data Ingestion](#data-ingestion-cuai-69) below for other modes (`embeddings`, `validate`), logging queries, and the destructive `--mode=full` escape hatch.

### 5. Verify

```bash
terraform output frontend_url
curl -sI "$(terraform output -raw frontend_url)"

gcloud run services describe chat-service --region=us-central1 \
  --format="value(status.url)"
# Visit the frontend URL — you should hit the real login page, not the GCP hello page.

# Confirm ingest counts match expectations
./infra.sh ingest validate
```

## Teardown

```bash
./infra.sh down
```

Destroys everything, including:

- The Artifact Registry repo and all images in it
- All Secret Manager secret shells **and their values** (including the Anthropic key)
- The data VM, its persistent disk, **and every snapshot of that disk** (the snapshot policy would normally keep snapshots after disk delete; `./infra.sh down` explicitly purges them after `terraform destroy` so nothing billable survives)
- All Cloud Run services and their revision history

After this runs, the GCP project has no paid resources. The drift check at the end of the script catches anything Terraform missed and fails loudly.

The GCS Terraform state bucket is not managed by this module — it lives separately so state survives teardowns. If you're truly done forever: `gsutil rm -r gs://<state-bucket>`.

## Manual steps, in one place

These cannot be scripted away by design — they're the only things between the checked-in code and a fully provisioned stack.

1. **First-time setup only** — `gcloud auth application-default login` and point `backend.tf` at your Terraform state bucket.
2. **Every fresh spin-up** — paste the Anthropic key (step 2 above).
3. **Every fresh spin-up** — trigger `deploy.yml` (step 3 above).
4. **Every fresh spin-up** — run `./infra.sh ingest` (step 4 above). Required because `./infra.sh down` wipes the data VM's disks along with everything else, so the databases come back empty.

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
| `outputs.tf` | `frontend_url`, `ollama_embed_url`, `data_vm_internal_ip`, `workload_identity_provider` (CUAI-89), `deploy_sa_email` (CUAI-89) |
| `apis.tf` | Enables required Google APIs |
| `network.tf` | VPC + subnet + serverless VPC connector + firewall policy |
| `data-vm.tf` | Compute Engine VM + persistent disk + snapshot policy + startup script |
| `scripts/data-vm-startup.sh` | Runs on VM boot; pulls secrets, brings up docker-compose stack |
| `artifact-registry.tf` | `cu-assistant` Docker repo |
| `cloud-run.tf` | Three app Cloud Run services (frontend, course-search-api, chat-service) + Secret Manager shells + IAM bindings |
| `ollama-embed.tf` | Prebaked Ollama embed Cloud Run service + SA + scoped invoker IAM (CUAI-88) |
| `ingest-job.tf` | Cloud Run Job for data ingestion pipeline + SA + Secret Manager bindings (CUAI-69) |
| `iam.tf` | Runtime service accounts + AR reader + (CUAI-89) WIF pool/provider + `deploy-sa` |
| `infra.sh` | `plan` / `up` / `down` / `status` / `secrets` / `ingest` wrapper |
| `terraform.tfvars.example` | Copy to `terraform.tfvars` and fill in `project_id` + secret-population commands |

## Data Ingestion (CUAI-69)

The `ingest-pipeline` Cloud Run Job loads the CU course catalog (courses, prereq graph, degree programs, embeddings) into the GCP databases. It must be run once after a fresh `./infra.sh up` before the app is usable — step 4 of the spin-up runbook.

### Trigger

The `./infra.sh ingest` wrapper is the preferred path — it pre-flights that the Job is on a real image (not the placeholder) and uses the correct `gcloud` invocation:

```bash
./infra.sh ingest             # default: --mode=upsert
./infra.sh ingest upsert      # same as above — idempotent, safe to re-run
./infra.sh ingest embeddings  # re-run only Step 4 (e.g. after embed service redeploy)
./infra.sh ingest validate    # count-based validators only, no writes
```

For the destructive reload path, use raw gcloud — the wrapper intentionally doesn't expose `--mode=full` to keep the confirmation flag from becoming muscle memory:

```bash
gcloud run jobs execute ingest-pipeline \
  --args="--mode=full,--i-understand-this-wipes-prod" \
  --region=us-central1 \
  --wait
```

### Dry run (local)

Preview row counts without touching the databases:

```bash
uv run --package data-ingest python -m data.ingest run --mode=upsert --dry-run
```

### Diagnose failures

Each execution emits structured JSON logs to Cloud Logging. Filter by `run_id` (printed in the first log line of every execution):

```
resource.type="cloud_run_job"
resource.labels.job_name="ingest-pipeline"
jsonPayload.run_id="<run_id>"
```

Or stream live during an execution:

```bash
gcloud logging tail 'resource.type="cloud_run_job" AND resource.labels.job_name="ingest-pipeline"' \
  --format='value(jsonPayload)'
```

### Re-run safely

- **`--mode=upsert`** — always safe to re-run. Uses `MERGE` (Neo4j) and `ON CONFLICT DO UPDATE` (Postgres). Running it twice produces identical state.
- **`--mode=embeddings`** — only processes courses with no embedding yet. Safe to re-run; already-embedded courses are skipped.
- **`--mode=full`** — destructive. Wipes all tables and nodes before reloading. Requires `--i-understand-this-wipes-prod`. Use only to recover from corrupt state.

### Expected validation counts (post-ingest)

| Check | Expected |
|-------|----------|
| Postgres courses | 3410 |
| Postgres sections | 9470 |
| Neo4j Course nodes | 3410 |
| Neo4j Program nodes | 203 |
| Neo4j HAS_PREREQUISITE edges | > 2000 |
| Courses with embeddings | 3410 |
| Vector index `course-embeddings` | exists (768-dim cosine) |
