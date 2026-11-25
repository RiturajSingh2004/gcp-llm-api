# MCP session log

Record every session where an agent operated GCP for you. The goal is to learn what
each gcloud command does, so read the command before approving it.

| Date | Prompt I gave the agent | Command(s) it ran | What I learned / what surprised me |
|---|---|---|---|
| 2026-11-26 | Diagnose why Cloud Run `/v1/chat` failed (`502`) | `gcloud run services get-iam-policy llm-api --project=llm-api-lab --region=us-central1`<br>`gcloud logging read resource.type=cloud_run_revision --project=llm-api-lab --limit=15 --format=json(...)` | Structured logs showed `upstream_code: 400` from Gemini because Secret Manager `gemini-api-key` v1 still held an old invalid key, and anonymous requests to `/` & `/favicon.ico` were rejected with `403`. |
| 2026-11-26 | Roll a new Cloud Run revision to pick up Secret Manager v3 | `gcloud run services update llm-api --project=llm-api-lab --region=us-central1 --update-secrets=GEMINI_API_KEY=gemini-api-key:latest` | Updating secret bindings creates a new revision (`llm-api-00002-xqw`) without rebuilding the Docker image. Anonymous `GET /v1/chat` returned `403`; authenticated `POST /v1/chat` hit `504` (30s `llm timeout`) with `gemini-3.5-flash`. |
| 2026-11-26 | Switch Cloud Run to `gemini-3.5-flash-lite` and re-test | `gcloud run services update llm-api --project=llm-api-lab --region=us-central1 --update-env-vars=GEMINI_MODEL=gemini-3.5-flash-lite` | Updating `GEMINI_MODEL` rolled revision `llm-api-00003-hsj`. `POST /v1/chat` succeeded (`200 OK`, `latency_ms: 5692`, `input_tokens: 8`, `output_tokens: 36`). Also noticed `/healthz` returns `404` on `.run.app` because Google Front End reserves `/healthz`. |
| 2026-11-26 | Phase G: warm latency, deliberate failure, traffic split & rollback (run in PowerShell) | `gcloud run services update ... --update-env-vars="GEMINI_MODEL=nonexistent-model"`<br>`gcloud logging read ... AND severity>=WARNING`<br>`gcloud run services update-traffic ... --to-revisions="llm-api-00003-hsj=90,llm-api-00002-xqw=10"`<br>`gcloud run services update-traffic ... --to-latest` | Warm `/v1/chat` calls took `2704 ms` and `4633 ms`. Breaking `GEMINI_MODEL` returned `502` to the client while Cloud Logging recorded `upstream_code: 404` on `llm-api-00004-b68`. Traffic split (90/10) and `--to-latest` rollback (`llm-api-00007-gr8`) both worked cleanly. |

## Flags or commands I did not recognize

| Command / flag | What it does (after I asked or read the docs) |
|---|---|
| `--no-allow-unauthenticated` | Blocks anonymous HTTP traffic at Cloud Run (`403`); callers must send a valid `Authorization: Bearer $(gcloud auth print-identity-token)` header and have `run.invoker`. |
| `--update-secrets=GEMINI_API_KEY=gemini-api-key:latest` | Mounts the `:latest` version of a Secret Manager secret as an env var on a new Cloud Run revision without rebuilding the image. |
| `--update-env-vars=GEMINI_MODEL=...` | Updates a plain environment variable on a new Cloud Run revision while preserving existing env vars and secrets. |
| `--to-revisions` / `--to-latest` | Splits traffic percentages across named revisions or routes 100% of traffic back to the latest revision. |
| `gcloud logging read` | Queries Cloud Logging entries; supports filtering by `resource.type`, `resource.labels.service_name`, and `severity>=WARNING`. |

## Commands the agent refused or could not run

- `run_gcloud_command` rejects shell operators (chaining `&&`, pipes `|`, redirections `>`) and subshells (`$(...)`).
- Passing `AND` inside a positional filter argument to `gcloud logging read` failed with `UnrecognizedArgumentsError` in the MCP tool wrapper; using a single-token filter (`resource.type=cloud_run_revision`) worked.
