#!/usr/bin/env bash
# Calls the private Cloud Run service with an identity token, then proves that an
# anonymous call is rejected.
#
#   SERVICE_URL=https://llm-api-xxxx.a.run.app ./scripts/smoke_test.sh
#   or: PROJECT_ID=my-project REGION=us-central1 ./scripts/smoke_test.sh
#
# Your user needs roles/run.invoker on the service.
set -euo pipefail

SERVICE="${SERVICE:-llm-api}"

if [[ -z "${SERVICE_URL:-}" ]]; then
  : "${PROJECT_ID:?Set SERVICE_URL, or PROJECT_ID and REGION}"
  : "${REGION:?Set SERVICE_URL, or PROJECT_ID and REGION}"
  SERVICE_URL="$(gcloud run services describe "${SERVICE}" \
    --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
fi

TOKEN="$(gcloud auth print-identity-token)"

echo "-- GET /healthz (authenticated)"
curl -sS -w '\nHTTP %{http_code}\n' \
  -H "Authorization: Bearer ${TOKEN}" \
  "${SERVICE_URL}/healthz"

echo "-- POST /v1/chat (authenticated)"
curl -sS -w '\nHTTP %{http_code}\n' \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Say hello in five words.", "max_output_tokens": 64}' \
  "${SERVICE_URL}/v1/chat"

echo "-- GET /healthz (anonymous, expect 401 or 403)"
code="$(curl -s -o /dev/null -w '%{http_code}' "${SERVICE_URL}/healthz")"
echo "HTTP ${code}"
if [[ "${code}" != "401" && "${code}" != "403" ]]; then
  echo "FAIL: the service answered an unauthenticated request" >&2
  exit 1
fi
echo "OK: anonymous access is rejected"
