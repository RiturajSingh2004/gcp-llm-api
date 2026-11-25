# IAM notes

Every role granted, to whom, on what, and why. Fill in the "Actually granted" column as you go.

## Expected grants

| Identity | Role | Scope | Why | Actually granted? |
|---|---|---|---|---|
| `llm-api-sa` | `roles/secretmanager.secretAccessor` | the one secret `gemini-api-key` | Runtime reads the Gemini key | Yes |
| `llm-api-sa` | `roles/logging.logWriter` | project | Runtime writes logs | Yes |
| Your user | `roles/run.invoker` | the Cloud Run service | Call the private service with an identity token | Covered by project `roles/owner` (no explicit service binding; `get-iam-policy` returned `etag: ACAB`) |
| Your user (deployer) | `roles/iam.serviceAccountUser` | `llm-api-sa` | Deploying a service that runs as another service account requires permission to "act as" it | Covered by project `roles/owner` |
| Your user | MCP Tool User | project | Only if you use Google's remote Cloud Run MCP server | Not needed (used local `@google-cloud/gcloud-mcp`) |

## Likely to bite you (good deliberate-failure material)

- **Cloud Build permissions.** On newer projects, builds may run as the Compute Engine default
  service account, which can lack permission to write logs, read the uploaded source, or push to
  Artifact Registry. If `gcloud builds submit` fails with a permission error, read the message,
  find which identity and which permission, and grant the narrowest role that fixes it. Record it here.
- **Missing act-as permission** on `llm-api-sa` makes `gcloud run deploy` fail.
- **Secret access.** Deploy succeeds but the revision fails to start if `llm-api-sa` cannot read the secret.

## Grants I made and why

| Date | Identity | Role | Scope | Reason |
|---|---|---|---|---|
| 2026-11-26 | `llm-api-sa@llm-api-lab.iam.gserviceaccount.com` | `roles/secretmanager.secretAccessor` | Secret `gemini-api-key` (only) | Allow Cloud Run runtime to read `GEMINI_API_KEY` without access to any other secrets. |
| 2026-11-26 | `llm-api-sa@llm-api-lab.iam.gserviceaccount.com` | `roles/logging.logWriter` | Project `llm-api-lab` | Allow Cloud Run runtime to write structured JSON logs to Cloud Logging. |

## Rule for the agent

Never give the agent broader access than you would be comfortable granting a person.
Do not give it Owner on any project you care about.
