#!/usr/bin/env bash
# Build and roll out Super Teacher to Cloud Run WITHOUT ever running two writers against the Litestream replica.
#
# Why this order: with --max-instances 1 and --min-instances 0 a revision only has an instance once it gets traffic.
# So we deploy with --no-traffic (no instance starts), then move 100% of traffic (the new revision restores the DB
# and starts replicating; the old instance gets no requests, so it writes nothing), then verify, and roll back to the
# previous revision if verification fails. Never hit the --no-traffic candidate URL: that would start a second writer.
#
# Usage:  PROJECT=... [REGION=us-central1] [SERVICE=superteacher] [AUTH_PASSWORD=...] scripts/deploy_cloud_run.sh [TAG]
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-superteacher}"
BUCKET="${BUCKET:-${PROJECT}-superteacher-litestream}"
TAG="${1:-$(git rev-parse --short HEAD)}"
IMAGE="gcr.io/${PROJECT}/superteacher:${TAG}"

echo ">> build ${IMAGE}"
gcloud builds submit --project "$PROJECT" --tag "$IMAGE" .

PREVIOUS="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)"
echo ">> previous revision: ${PREVIOUS:-none}"

echo ">> deploy (no traffic)"
gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --platform managed --image "$IMAGE" \
  --no-traffic --allow-unauthenticated --max-instances 1 --min-instances 0 --memory 512Mi --cpu-boost \
  --set-secrets 'AUTH_PASSWORD=superteacher-auth-password:latest,SESSION_SECRET=superteacher-session-secret:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest' \
  --set-env-vars "SEED_DEMO_DATA=false,VERSION=${TAG},LITESTREAM_REPLICA_URL=gcs://${BUCKET}/${SERVICE}"

echo ">> move traffic to the new revision"
gcloud run services update-traffic "$SERVICE" --project "$PROJECT" --region "$REGION" --to-latest

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format='value(status.url)')"
echo ">> verify ${URL}"
ok=1
for _ in 1 2 3 4 5 6; do
  if curl -fsS --max-time 60 "${URL}/api/health" | grep -q '"healthy"'; then ok=0; break; fi
  sleep 5
done
if [[ $ok -eq 0 && -n "${AUTH_PASSWORD:-}" ]]; then
  python deployment_tests.py "$URL" || ok=1
fi

if [[ $ok -ne 0 ]]; then
  echo "!! verification failed"
  if [[ -n "$PREVIOUS" ]]; then
    echo "!! rolling back to ${PREVIOUS}"
    gcloud run services update-traffic "$SERVICE" --project "$PROJECT" --region "$REGION" --to-revisions "${PREVIOUS}=100"
  fi
  exit 1
fi
echo ">> done: ${URL} (${TAG})"
