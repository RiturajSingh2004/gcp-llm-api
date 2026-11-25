#!/usr/bin/env bash
# Manual build + deploy (the path the MCP agent will later do for you).
#
#   PROJECT_ID=my-project REGION=us-central1 TAG=v1 ./scripts/deploy.sh
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
: "${REGION:?Set REGION}"
TAG="${TAG:-v1}"
SERVICE="${SERVICE:-llm-api}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.5-flash-lite}"

SA_EMAIL="llm-api-sa@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/llm-api/llm-api:${TAG}"

cd "$(dirname "$0")/.."

echo "==> Building ${IMAGE} with Cloud Build"
gcloud builds submit --project "${PROJECT_ID}" --tag "${IMAGE}" .

echo "==> Deploying ${SERVICE} to Cloud Run (private, max 2 instances)"
gcloud run deploy "${SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE}" \
  --service-account "${SA_EMAIL}" \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --cpu 1 \
  --memory 512Mi \
  --set-env-vars "GEMINI_MODEL=${GEMINI_MODEL}" \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest"

echo "==> Service URL"
gcloud run services describe "${SERVICE}" \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --format='value(status.url)'
