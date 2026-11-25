#!/usr/bin/env bash
# One-time GCP setup for the llm-api lab (Phase C of plan.md).
# Run it yourself, and read each step the first time: this is what the MCP agent
# will automate later, so you should know what every command does.
#
#   PROJECT_ID=my-dedicated-project REGION=us-central1 ./scripts/setup_gcp.sh
#
# Check the current Cloud Run free-tier page for which regions qualify before
# choosing REGION.
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID to a dedicated project with billing linked}"
: "${REGION:?Set REGION, e.g. us-central1}"

SERVICE_ACCOUNT="llm-api-sa"
SECRET_NAME="gemini-api-key"
AR_REPO="llm-api"
SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

# Guardrail: budgets are created in the console (Billing > Budgets & alerts).
read -r -p "Have you created a billing budget alert for ${PROJECT_ID}? [y/N] " answer
[[ "${answer}" =~ ^[Yy]$ ]] || { echo "Create the budget alert first, then re-run."; exit 1; }

gcloud config set project "${PROJECT_ID}"

echo "==> Enabling APIs"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com \
  iam.googleapis.com

echo "==> Artifact Registry repo (${AR_REPO} in ${REGION})"
gcloud artifacts repositories describe "${AR_REPO}" --location "${REGION}" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "${AR_REPO}" \
       --repository-format=docker \
       --location="${REGION}" \
       --description="llm-api container images"

echo "==> Runtime service account (${SA_EMAIL})"
gcloud iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "${SERVICE_ACCOUNT}" \
       --display-name="llm-api runtime"

echo "==> Secret (${SECRET_NAME})"
if ! gcloud secrets describe "${SECRET_NAME}" >/dev/null 2>&1; then
  gcloud secrets create "${SECRET_NAME}" --replication-policy=automatic
  read -r -s -p "Paste Gemini API key (input hidden): " GEMINI_KEY
  echo
  printf '%s' "${GEMINI_KEY}" | gcloud secrets versions add "${SECRET_NAME}" --data-file=-
  unset GEMINI_KEY
fi

echo "==> Least-privilege grants for ${SERVICE_ACCOUNT}"
# Read only this one secret, not every secret in the project.
gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"
# Write logs.
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/logging.logWriter" \
  --condition=None

echo
echo "Done. Record each grant and why in docs/iam-notes.md."
