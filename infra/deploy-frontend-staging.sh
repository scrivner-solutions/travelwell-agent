#!/usr/bin/env bash
# Manual staging deploy for the TravelWell frontend: build, push, deploy, smoke.
# Mirrors infra/deploy-staging.sh (backend) so the two stay recognisable.
#
#   bash infra/deploy-frontend-staging.sh
#
# The backend URL is read from Cloud Run rather than hardcoded, so this cannot
# drift from whatever the backend service actually is.

set -euo pipefail

# Environment identifiers are config, not code: they come from the environment
# or from a file outside the repo, so this deploys a second environment without
# being edited. Same precedent as with-staging-db.sh.
ENV_FILE="${TRAVELWELL_STAGING_ENV:-$HOME/.travelwell-staging.env}"
# shellcheck source=/dev/null
[[ -r "$ENV_FILE" ]] && source "$ENV_FILE"
# shellcheck source=/dev/null
source "$(cd "$(dirname "$0")" && pwd)/config.env"

PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
[[ -n "$PROJECT_ID" ]] || {
  echo "No project. Set GCP_PROJECT_ID in $ENV_FILE, or gcloud config set project." >&2
  exit 1
}
REGION="${GCP_REGION:-us-central1}"
SERVICE="$FRONTEND_SERVICE"

AR_HOST="$REGION-docker.pkg.dev"
RUNTIME_SA="${GCP_RUNTIME_SA:-$RUNTIME_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com}"

# Say where, before anything mutates - an ambient gcloud project is otherwise
# invisible at the call site.
echo "== Target: project $PROJECT_ID / $REGION =="

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
SHA=$(git -C "$REPO_ROOT" rev-parse --short HEAD)
IMAGE="$AR_HOST/$PROJECT_ID/$AR_REPO/$FRONTEND_IMAGE_NAME:$SHA"

BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE" --region "$REGION" \
  --project "$PROJECT_ID" --format 'value(status.url)')
[[ -n "$BACKEND_URL" ]] || { echo "No $BACKEND_SERVICE service found in $REGION" >&2; exit 1; }
echo "== Backend: $BACKEND_URL =="

# Same rule as the backend: build a pristine export of HEAD so the :$SHA tag
# names exactly what is inside. DEPLOY_FROM_WORKTREE=1 builds the live tree and
# tags -dirty, which is required while nginx.conf.template is still uncommitted.
if [[ "${DEPLOY_FROM_WORKTREE:-0}" == 1 ]]; then
  IMAGE="$IMAGE-dirty"
  BUILD_CONTEXT="$REPO_ROOT/frontend"
else
  BUILD_DIR=$(mktemp -d)
  trap 'rm -rf "$BUILD_DIR"' EXIT
  git -C "$REPO_ROOT" archive HEAD frontend | tar -x -C "$BUILD_DIR"
  BUILD_CONTEXT="$BUILD_DIR/frontend"
fi

echo "== Build $IMAGE =="
docker build -t "$IMAGE" "$BUILD_CONTEXT"

echo "== Push =="
gcloud auth configure-docker "$AR_HOST" --quiet
docker push "$IMAGE"

# VITE_API_BASE_URL is deliberately unset: an empty base keeps the SPA calling
# /api/v1 on its own origin, which is what keeps the session cookie first-party.
echo "== Deploy =="
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --service-account "$RUNTIME_SA" \
  --update-env-vars "BACKEND_URL=$BACKEND_URL" \
  --cpu-boost \
  --min-instances 0 \
  --max-instances "$MAX_INSTANCES" \
  --memory "$FRONTEND_MEMORY" \
  --cpu 1

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --project "$PROJECT_ID" --format 'value(status.url)')
TOKEN=$(gcloud auth print-identity-token)

echo "== Smoke test $URL =="
SHELL_CODE=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$URL/" || true)
CONF_CODE=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$URL/config.json" || true)
API_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $TOKEN" "$URL/api/v1/auth/demo" || true)
ANON_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$URL/" || true)
echo "  SPA shell        : $SHELL_CODE"
echo "  /config.json     : $CONF_CODE"
echo "  /api via nginx   : $API_CODE"
echo "  anonymous shell  : $ANON_CODE"

if [[ "$SHELL_CODE" != 200 ]]; then
  echo "Frontend is not serving. Logs:" >&2
  echo "  https://console.cloud.google.com/run/detail/$REGION/$SERVICE/logs?project=$PROJECT_ID" >&2
  exit 1
fi

echo
echo "Deployed: $URL"
if [[ "$API_CODE" != 200 ]]; then
  # nginx reaches the backend over the public internet, so a private backend
  # rejects it exactly as a browser would. Nothing to fix in the image.
  echo "NOTE: /api returns $API_CODE because the BACKEND is still private. Ask the admin:"
  echo "  gcloud run services add-iam-policy-binding $BACKEND_SERVICE --region $REGION --member=allUsers --role=roles/run.invoker"
fi
if [[ "$ANON_CODE" != 200 ]]; then
  echo "NOTE: the frontend itself is private, so no browser can load it. Ask the admin:"
  echo "  gcloud run services add-iam-policy-binding $SERVICE --region $REGION --member=allUsers --role=roles/run.invoker"
fi
