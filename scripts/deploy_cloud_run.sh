#!/usr/bin/env bash
# Stage only against isolated storage or after an observed writer drain.
# Deployment flags cannot prevent invocation from starting a replica writer.
# The release operator supplies drain evidence; this script cannot prove a drain.
# ISOLATED_CANDIDATE_CONFIRMED attests fresh, nonshared storage with no existing
# writer, including revisions of the isolated service itself.
# PROJECT=... SERVICE=superteacher-overhaul-staging REPLICA_PREFIX=overhaul-staging/RELEASE \
#   ISOLATED_CANDIDATE_CONFIRMED=yes RUNTIME_SERVICE_ACCOUNT=... scripts/deploy_cloud_run.sh [IMAGE_TAG]
# PROJECT=... SERVICE=... REPLICA_PREFIX=... DRAINED_WRITER_CONFIRMED=yes DRAINED_WRITER_REVISION=OLD \
#   scripts/deploy_cloud_run.sh --promote CANDIDATE_REVISION
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:?set the explicit target SERVICE}"
BUCKET="${BUCKET:-${PROJECT}-superteacher-litestream}"
REPLICA_PREFIX="${REPLICA_PREFIX:?set the explicit storage REPLICA_PREFIX}"

fail() { printf '%s\n' "$1" >&2; exit 1; }

[[ "$SERVICE" =~ ^[a-z]([a-z0-9-]{0,47}[a-z0-9])?$ ]] || fail 'Invalid service name.'
[[ "$BUCKET" =~ ^[a-z0-9][a-z0-9._-]+$ && "$REPLICA_PREFIX" =~ ^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$ ]] || \
  fail 'Invalid replica bucket or prefix; use nonempty path segments without dots.'

require_observed_drain() {
  [[ "${DRAINED_WRITER_CONFIRMED:-}" == yes && -n "${DRAINED_WRITER_REVISION:-}" ]] || \
    fail 'Staging or promotion against shared storage requires DRAINED_WRITER_CONFIRMED=yes and the observed DRAINED_WRITER_REVISION; verify quiescence, closed sessions and final replica sync first.'
  status_json="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format='json(status)')"
  previous="$(python3 -c 'import json,sys; s=json.load(sys.stdin)["status"]; t=[x for x in s.get("traffic",[]) if x.get("percent",0)>0]; assert len(t)==1 and t[0]["percent"]==100, "Expected one serving revision at 100%"; print(t[0]["revisionName"])' <<< "$status_json")"
  [[ "$previous" == "$DRAINED_WRITER_REVISION" ]] || fail 'Serving revision changed or differs from the recorded drained writer.'
}

if [[ "${1:-}" == --promote ]]; then
  [[ $# -eq 2 ]] || fail 'Usage: --promote CANDIDATE_REVISION'
  candidate="$2"
  [[ "$candidate" == "$SERVICE"-* ]] || fail 'Candidate must belong to SERVICE.'
  require_observed_drain
  # Keep revision metadata private; print neither environment values nor references.
  candidate_json="$(gcloud run revisions describe "$candidate" --project "$PROJECT" --region "$REGION" --format='json(spec.containers)')"
  python3 -c 'import json,sys
revision=json.load(sys.stdin)
env=[entry for container in revision.get("spec",{}).get("containers",[]) for entry in container.get("env",[]) if entry.get("name")=="LITESTREAM_REPLICA_URL"]
if len(env)!=1 or "valueFrom" in env[0] or "valueSource" in env[0] or env[0].get("value")!=sys.argv[1]:
    raise SystemExit("Candidate must have exactly one literal replica URL matching the explicit bucket and prefix.")
' "gs://${BUCKET}/${REPLICA_PREFIX}" <<< "$candidate_json"
  unset candidate_json
  printf 'Promoting %s after operator-confirmed drain of %s.\n' "$candidate" "$previous"
  gcloud run services update-traffic "$SERVICE" --project "$PROJECT" --region "$REGION" --to-revisions "${candidate}=100"
  printf 'Verify health/version, authenticated workflows and persistence now. Previous revision: %s.\n' "$previous"
  printf '%s\n' 'No automatic rollback: first verify schema compatibility and drain the candidate writer before another traffic shift.'
  exit 0
fi

[[ $# -le 1 ]] || fail 'Usage: [IMAGE_TAG] or --promote CANDIDATE_REVISION'
RUNTIME_SERVICE_ACCOUNT="${RUNTIME_SERVICE_ACCOUNT:?set the verified existing RUNTIME_SERVICE_ACCOUNT}"
TAG="${1:-$(git rev-parse HEAD)}"
[[ "$TAG" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]] || fail 'Invalid image tag.'
isolated_stage=no
if [[ "$SERVICE" == superteacher-overhaul-staging && "$REPLICA_PREFIX" == overhaul-staging/* && "${ISOLATED_CANDIDATE_CONFIRMED:-}" == yes ]]; then
  isolated_stage=yes
else
  require_observed_drain
fi
IMAGE="gcr.io/${PROJECT}/superteacher:${TAG}"
AUTH_SECRET_VERSION="${AUTH_SECRET_VERSION:-1}"
SESSION_SECRET_VERSION="${SESSION_SECRET_VERSION:-1}"
AI_SECRET_VERSION="${AI_SECRET_VERSION:-1}"
SCHOOL_TIMEZONE="${SCHOOL_TIMEZONE:-UTC}"

printf 'Building %s.\n' "$IMAGE"
gcloud builds submit --project "$PROJECT" --tag "$IMAGE" .
[[ "$isolated_stage" == yes ]] || require_observed_drain
printf 'Staging %s; replica gs://%s/%s. Deployment flags do not prevent later invocation.\n' "$SERVICE" "$BUCKET" "$REPLICA_PREFIX"
gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --platform managed --image "$IMAGE" \
  --service-account "$RUNTIME_SERVICE_ACCOUNT" \
  --no-traffic --no-deploy-health-check --allow-unauthenticated \
  --max-instances 1 --min-instances 0 --min 0 --memory 512Mi --cpu-boost \
  --set-secrets "AUTH_PASSWORD=superteacher-auth-password:${AUTH_SECRET_VERSION},SESSION_SECRET=superteacher-session-secret:${SESSION_SECRET_VERSION},ANTHROPIC_API_KEY=anthropic-api-key:${AI_SECRET_VERSION}" \
  --set-env-vars "SEED_DEMO_DATA=false,VERSION=${TAG},FORWARDED_ALLOW_IPS=*,SCHOOL_TIMEZONE=${SCHOOL_TIMEZONE},LITESTREAM_REPLICA_URL=gs://${BUCKET}/${REPLICA_PREFIX}"
candidate="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format='value(status.latestCreatedRevisionName)')"
printf 'Staged revision: %s. Traffic has not been promoted.\n' "$candidate"
printf '%s\n' 'Do not invoke this revision while another writer uses its replica. Validate an isolated service/prefix, preserve a backup, then observe the serving writer drain before --promote.'
