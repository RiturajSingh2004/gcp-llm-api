# Commands Runbook (Start to Finish)

Complete PowerShell command log for setting up, testing, deploying, observing, and cleaning up `gcp-llm-api` on GCP free tier using `uv`, `gcloud`, and the `gcloud` MCP server. All API keys and tokens are redacted.

---

## 1. Local Setup & Verification (Phase A)

```powershell
# Create .venv and install all dependencies (including dev tools)
uv sync

# Run unit tests, linter, and formatter checks
uv run pytest
uv run ruff check .
uv run ruff format --check .

# Configure local environment (set GEMINI_API_KEY=<YOUR_GEMINI_API_KEY> inside .env)
Copy-Item .env.example .env

# Verify available Flash models for your API key (without printing the key)
uv run python -c "from google import genai; from app.config import get_settings; s = get_settings(); c = genai.Client(api_key=s.gemini_api_key.get_secret_value()); models = [m.name for m in c.models.list() if 'generateContent' in (m.supported_actions or []) and 'flash' in m.name]; print(models)"

# Start local FastAPI server (Terminal 1)
uv run uvicorn app.main:app --reload --port 8080

# Call local endpoints (Terminal 2)
Invoke-RestMethod http://localhost:8080/healthz
Invoke-RestMethod -Method Post -Uri http://localhost:8080/v1/chat `
  -ContentType "application/json" `
  -Body '{"prompt": "Explain Cloud Run in one sentence."}'
```

---

## 2. Install & Authenticate `gcloud` CLI (Phase C)

```powershell
# Install Google Cloud SDK (or run GoogleCloudSDKInstaller.exe directly)
winget install Google.CloudSDK

# Reload PATH in the current PowerShell session
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")

# Authenticate CLI and Application Default Credentials
gcloud init
gcloud config set run/region us-central1
gcloud auth application-default login
```

---

## 3. One-Time GCP Foundation Setup (Phase C)

*(Prerequisite: link billing to `llm-api-lab` and create a billing budget alert in the GCP Console.)*

```powershell
$PROJECT_ID = "llm-api-lab"
$REGION = "us-central1"
$SA_EMAIL = "llm-api-sa@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable `
  run.googleapis.com `
  cloudbuild.googleapis.com `
  artifactregistry.googleapis.com `
  secretmanager.googleapis.com `
  logging.googleapis.com `
  iam.googleapis.com

# Create Artifact Registry Docker repository
gcloud artifacts repositories create llm-api `
  --repository-format=docker `
  --location=$REGION `
  --description="llm-api container images"

# Create dedicated runtime service account
gcloud iam service-accounts create llm-api-sa `
  --display-name="llm-api runtime"

# Create Secret Manager secret and store GEMINI_API_KEY without a trailing newline
gcloud secrets create gemini-api-key --replication-policy=automatic
[System.IO.File]::WriteAllText("$env:TEMP\gemini_key.txt", "<YOUR_GEMINI_API_KEY>")
gcloud secrets versions add gemini-api-key --data-file="$env:TEMP\gemini_key.txt"
Remove-Item "$env:TEMP\gemini_key.txt"

# Verify secret version exists
gcloud secrets versions list gemini-api-key

# Grant least-privilege IAM roles to llm-api-sa
gcloud secrets add-iam-policy-binding gemini-api-key `
  --member="serviceAccount:$SA_EMAIL" `
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$SA_EMAIL" `
  --role="roles/logging.logWriter" `
  --condition=None
```

---

## 4. Connect `gcloud` MCP Server (Phase D)

Added to `C:\Users\<USER>\.gemini\config\mcp_config.json` (then restarted Antigravity):

```json
{
  "mcpServers": {
    "gcloud": {
      "command": "cmd",
      "args": ["/c", "npx", "-y", "@google-cloud/gcloud-mcp"]
    }
  }
}
```

---

## 5. Build & Deploy to Cloud Run (Phase E)

```powershell
# Generate lockfile required by Dockerfile (uv sync --locked)
uv lock

$PROJECT_ID = "llm-api-lab"
$REGION = "us-central1"
$IMAGE = "$REGION-docker.pkg.dev/$PROJECT_ID/llm-api/llm-api:v1"

# Build container with Cloud Build and push to Artifact Registry
gcloud builds submit --project $PROJECT_ID --tag $IMAGE .

# Deploy privately to Cloud Run with free-tier limits
gcloud run deploy llm-api `
  --project $PROJECT_ID `
  --region $REGION `
  --image $IMAGE `
  --service-account "llm-api-sa@$PROJECT_ID.iam.gserviceaccount.com" `
  --no-allow-unauthenticated `
  --min-instances 0 `
  --max-instances 2 `
  --cpu 1 `
  --memory 512Mi `
  --set-env-vars "GEMINI_MODEL=gemini-3.5-flash-lite" `
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest"
```

Updates performed via the `gcloud` MCP during troubleshooting:

```text
gcloud run services get-iam-policy llm-api --project=llm-api-lab --region=us-central1
gcloud logging read resource.type=cloud_run_revision --project=llm-api-lab --limit=15 --format=json(...)
gcloud run services update llm-api --project=llm-api-lab --region=us-central1 --update-secrets=GEMINI_API_KEY=gemini-api-key:latest
gcloud run services update llm-api --project=llm-api-lab --region=us-central1 --update-env-vars=GEMINI_MODEL=gemini-3.5-flash-lite
```

---

## 6. Smoke Test Private Service (Phase F)

```powershell
$URL = "https://llm-api-550048078275.us-central1.run.app"
$TOKEN = gcloud auth print-identity-token   # never print or commit <IDENTITY_TOKEN>

# Authenticated POST /v1/chat (expect 200 OK)
Invoke-RestMethod -Method Post -Uri "$URL/v1/chat" `
  -Headers @{ Authorization = "Bearer $TOKEN" } `
  -ContentType "application/json" `
  -Body '{"prompt": "Explain Cloud Run in one sentence."}'

# Anonymous GET /v1/chat (expect 403)
try {
  Invoke-WebRequest -Uri "$URL/v1/chat"
} catch {
  $_.Exception.Response.StatusCode.value__
}
```

---

## 7. Observe, Break & Rollback (Phase G)

```powershell
# Read structured request logs (status, latency, token counts)
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="llm-api"' `
  --project=llm-api-lab `
  --limit=20 `
  --format="table(timestamp,severity,jsonPayload.message,jsonPayload.status,jsonPayload.latency_ms,jsonPayload.input_tokens,jsonPayload.output_tokens)"

# Warm latency checks
Invoke-RestMethod -Method Post -Uri "$URL/v1/chat" -Headers @{ Authorization = "Bearer $TOKEN" } -ContentType "application/json" -Body '{"prompt": "Say hi"}'
Invoke-RestMethod -Method Post -Uri "$URL/v1/chat" -Headers @{ Authorization = "Bearer $TOKEN" } -ContentType "application/json" -Body '{"prompt": "Say hi"}'

# Break on purpose (invalid model -> 502) and diagnose from logs (upstream_code: 404)
gcloud run services update llm-api --project=llm-api-lab --region=us-central1 --update-env-vars="GEMINI_MODEL=nonexistent-model"
Invoke-RestMethod -Method Post -Uri "$URL/v1/chat" -Headers @{ Authorization = "Bearer $TOKEN" } -ContentType "application/json" -Body '{"prompt": "Hi"}'
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="llm-api" AND severity>=WARNING' --project=llm-api-lab --limit=5

# Fix back to working model
gcloud run services update llm-api --project=llm-api-lab --region=us-central1 --update-env-vars="GEMINI_MODEL=gemini-3.5-flash-lite"

# List revisions, split traffic 90/10, and roll back to latest
gcloud run revisions list --service=llm-api --project=llm-api-lab --region=us-central1
gcloud run services update-traffic llm-api --project=llm-api-lab --region=us-central1 --to-revisions="llm-api-00003-hsj=90,llm-api-00002-xqw=10"
gcloud run services update-traffic llm-api --project=llm-api-lab --region=us-central1 --to-latest
```

---

## 8. Clean Up (Phase H)

### Option A: Delete individual resources
```powershell
$PROJECT_ID = "llm-api-lab"
$REGION = "us-central1"

gcloud run services delete llm-api --project=$PROJECT_ID --region=$REGION --quiet
gcloud artifacts repositories delete llm-api --project=$PROJECT_ID --location=$REGION --quiet
gcloud secrets delete gemini-api-key --project=$PROJECT_ID --quiet
gcloud iam service-accounts delete "llm-api-sa@$PROJECT_ID.iam.gserviceaccount.com" --project=$PROJECT_ID --quiet
gcloud storage rm -r "gs://${PROJECT_ID}_cloudbuild"
```

### Option B: Delete the entire dedicated project
```powershell
gcloud projects delete llm-api-lab
```

---

## 9. Challenges & Troubleshooting Log

Real issues encountered during setup and deployment on Windows + GCP free tier, and how each was resolved:

### 1. `winget install Google.CloudSDK` hung waiting for UAC
- **Symptom:** `winget` downloaded the installer and stalled indefinitely at `The installer will request to run as administrator. Expect a prompt.` with no visible prompt.
- **Cause:** The UAC/GUI prompt was suppressed or hidden behind other windows.
- **Fix:** Cancel with `Ctrl+C`, download `GoogleCloudSDKInstaller.exe` directly with `Invoke-WebRequest`, and launch it with `Start-Process`.

### 2. `gcloud` not recognized after installation (PowerShell & MCP)
- **Symptom:** `gcloud : The term 'gcloud' is not recognized...` even though the installer finished and added `google-cloud-sdk\bin` to User `PATH`.
- **Cause:** Existing PowerShell windows and the IDE/MCP host process keep the `PATH` snapshot from before installation.
- **Fix:** Refresh `PATH` in the current PowerShell session (`[Environment]::GetEnvironmentVariable(...)`) and restart the IDE so the `gcloud` MCP server inherits the updated `PATH`.

### 3. `gcloud init` failed with `Compute Engine API has not been used`
- **Symptom:** `ERROR: (gcloud.compute.project-info.describe) ... Compute Engine API has not been used in project llm-api-lab before or it is disabled.`
- **Cause:** `gcloud init` probes Compute Engine to set a default VM zone/region.
- **Fix:** Ignore this warning—Cloud Run does not use Compute Engine VMs, so you do not need to enable `compute.googleapis.com`. Set the Cloud Run region explicitly with `gcloud config set run/region us-central1`.

### 4. Bash scripts (`setup_gcp.sh`, `deploy.sh`) failed in PowerShell
- **Symptom:** `PROJECT_ID=llm-api-lab : The term 'PROJECT_ID=llm-api-lab' is not recognized...`
- **Cause:** `VAR=value ./script.sh` is Bash syntax, not PowerShell.
- **Fix:** Either run the `.sh` scripts in **Git Bash / WSL**, or run the equivalent native PowerShell commands using `$VAR = "..."` and backticks (`` ` ``) for line continuations.

### 5. PowerShell `|` pipe adds `\r\n` to Secret Manager secrets
- **Symptom:** Piping a secret in PowerShell (`"key" | gcloud secrets versions add ... --data-file=-`) appends a trailing newline (`\r\n`), which can break HTTP header / API key validation.
- **Fix:** Write the key with `[System.IO.File]::WriteAllText(...)` (no trailing newline), upload via `--data-file`, and immediately `Remove-Item` the temporary file.

### 6. Configuring `@google-cloud/gcloud-mcp` on Windows
- **Symptom:** MCP clients on Windows can fail to spawn `npx` directly.
- **Fix:** Wrap `npx` with `"command": "cmd"` and `"args": ["/c", "npx", "-y", "@google-cloud/gcloud-mcp"]` in `mcp_config.json`.

### 7. Gemini API errors masked behind `502 LLM upstream error`
- **Symptom:** `app/services/llm.py` intentionally hides upstream errors from HTTP clients and returns `502 LLM upstream error`, making it unclear why calls failed.
- **Cause & Fixes (diagnosed via direct `genai.Client` check and Cloud Logging):**
  - **`400 API_KEY_INVALID`:** Invalid/placeholder key or stray quotes/spaces in `.env`. Fixed by pasting a valid AI Studio key (`AIza...`).
  - **`402 RESOURCE_EXHAUSTED` (`Your prepayment credits are depleted`):** Key belonged to an AI Studio project on a Prepay billing plan with \$0 balance instead of the Free tier. Fixed by using a Free-tier AI Studio project/key.
  - **`503 UNAVAILABLE` on `gemini-3.8-flash` / `gemini-3.7-flash`:** Temporary high demand on those models.
  - **`504` (30s timeout) on `gemini-3.5-flash`:** `gemini-3.5-flash` took `16.42s` locally and exceeded the `30s` timeout on Cloud Run. Benchmarked `gemini-3.5-flash-lite` (`4.61s` locally) and updated the default model across the project.
  - **Truncated output with small `max_output_tokens`:** Setting `max_output_tokens: 128` on thinking-capable Flash models can spend most of the budget on thinking tokens; leaving the default `512` returns full responses.

### 8. Cloud Run still returned `400` after `.env` was fixed
- **Symptom:** Local `/v1/chat` worked, but Cloud Run kept returning `502` with `upstream_code: 400` in Cloud Logging.
- **Cause:** Cloud Run reads `GEMINI_API_KEY` from **Secret Manager** (`gemini-api-key:latest`), which still held the old invalid key (version `1`), not `.env`.
- **Fix:** Added secret version `3` with the working key and rolled a new Cloud Run revision (`--update-secrets=GEMINI_API_KEY=gemini-api-key:latest`).

### 9. `/healthz` returned `404` on Cloud Run `.run.app`
- **Symptom:** `GET /healthz` returned `200 OK` locally, but `404 Not Found` on `https://llm-api-550048078275.us-central1.run.app/healthz` (without reaching the container logs).
- **Cause:** Google Front End (GFE) reserves `/healthz` on `.run.app` URLs.
- **Fix:** Expected platform behavior on `.run.app`; `/v1/chat` routes normally to the FastAPI app (or use `/health` if you want a Cloud Run-reachable liveness route).

### 10. `gcloud` MCP (`run_gcloud_command`) syntax constraints
- **Symptom:** `UnrecognizedArgumentsError` when passing `AND` in `gcloud logging read` filter arguments, or errors on shell operators.
- **Cause:** The `gcloud` MCP tool executes single `gcloud` commands directly without a shell and rejects pipes (`|`), chaining (`&&`), subshells (`$()`), and multi-token filter strings with spaces.
- **Fix:** Pass single-token filters (e.g., `resource.type=cloud_run_revision`) and one `gcloud` command per tool call.
