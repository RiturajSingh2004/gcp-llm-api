# gcp-llm-api

A small FastAPI service that calls the Gemini API, built to be deployed on Cloud Run
and operated through MCP servers. See `plan.md` for the full plan, architecture and phases.

## API

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/healthz` | none | `{"status": "ok"}` |
| POST | `/v1/chat` | `{"prompt": str, "max_output_tokens": int?}` | `{"text", "model", "usage": {"input_tokens", "output_tokens"}, "latency_ms"}` |

Guards: prompt length capped (default 4000 chars), `max_output_tokens` clamped server-side
(default 512, cap 1024), 30 s model timeout. Errors map to 422 (bad input), 429 (upstream
rate limit), 502 (upstream error), 503 (no API key configured), 504 (timeout).
Prompts are never logged.

## Run locally (Phase A)

This project uses [uv](https://docs.astral.sh/uv/) for everything Python.

```bash
uv sync                     # creates .venv and uv.lock (commit uv.lock)

cp .env.example .env        # then put your key from AI Studio in GEMINI_API_KEY
uv run uvicorn app.main:app --reload --port 8080

curl localhost:8080/healthz
curl -s localhost:8080/v1/chat -H 'Content-Type: application/json' \
  -d '{"prompt": "Explain Cloud Run in one sentence."}'
```

`GEMINI_MODEL` defaults to `gemini-3.5-flash-lite`. Check AI Studio for the current free-tier
model and override it in `.env` if needed. `/healthz` works without a key; `/v1/chat`
returns 503 until one is set.

## Test and lint

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Add a dependency with `uv add <package>` (or `uv add --dev <package>`); it updates
`pyproject.toml` and `uv.lock`.

Tests use fakes, so they need no API key and no network.

## Container (Phase B)

The Dockerfile installs with `uv sync --locked`, so `uv.lock` must exist and be committed
(run `uv lock` once). The same applies to Cloud Build in Phase C onward.

```bash
docker build -t llm-api .
docker run --rm -p 8080:8080 -e GEMINI_API_KEY=... llm-api
curl localhost:8080/healthz
```

## GCP (Phases C to F)

```bash
export PROJECT_ID=your-dedicated-project REGION=us-central1

./scripts/setup_gcp.sh      # APIs, Artifact Registry, service account, secret, grants
./scripts/deploy.sh         # Cloud Build + Cloud Run (private, max 2 instances)
./scripts/smoke_test.sh     # authenticated call works, anonymous call is rejected
```

Create a billing budget alert before running anything. Then repeat the deploy step through
the gcloud and Cloud Run MCP servers (Phases D and E) and log it in `docs/mcp-session-log.md`.

## Layout

```
app/
  main.py          app factory, request-logging middleware
  config.py        env-driven settings
  schemas.py       request/response models
  api/             health.py, chat.py, deps.py (dependency wiring)
  services/llm.py  Gemini wrapper: timeout, error mapping, token counts
  core/logging.py  JSON logs for Cloud Logging
pyproject.toml     dependencies (uv), pytest and ruff config
tests/             fakes only; no network
scripts/           setup_gcp.sh, deploy.sh, smoke_test.sh
docs/              commands-runbook.md, mcp-session-log.md, iam-notes.md
```
