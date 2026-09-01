#!/usr/bin/env bash
# Staging deploy: build, push, migrate, deploy, smoke test. THE implementation,
# for both paths - a human runs it by hand, and .github/workflows/deploy.yml
# calls this same file on every merge to main. It used to say it "mirrors" that
# workflow step for step; two implementations promising to match is exactly how
# they drifted, so the workflow now holds only when-and-who and calls this.
#
# It does not authenticate. It uses whatever gcloud is already logged in as:
# a human locally, the deployer service account via Workload Identity in CI.
# Keep it that way - auth is the one thing that legitimately differs.
#
#   bash infra/deploy-staging.sh

set -euo pipefail

# Names are data, not code. Two files, in this order so the more specific wins:
#   1. the environment file - project, region, instance. Untracked, per deploy.
#   2. infra/config.env - the names the app uses in EVERY environment.
# config.env is all ${VAR:-default}, so anything step 1 set survives step 2.
# Deploying a second environment means another environment file, no edits here.
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
SERVICE="$BACKEND_SERVICE"
AR_HOST="$REGION-docker.pkg.dev"
RUNTIME_SA="${GCP_RUNTIME_SA:-$RUNTIME_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com}"
CLOUDSQL_INSTANCE="${GCP_SQL_CONNECTION_NAME:-}"

# DATABASE_URL alone selects the target (app/db/engine.py). Cloud SQL is the
# only one that also needs its instance attached to the revision; set
# DB_TARGET=external for a hosted Postgres reached over TCP.
DB_TARGET="${DB_TARGET:-cloudsql}"
if [[ "$DB_TARGET" == cloudsql ]]; then
  [[ -n "$CLOUDSQL_INSTANCE" ]] || {
    echo "DB_TARGET is cloudsql but GCP_SQL_CONNECTION_NAME is unset." >&2
    echo "Set it in $ENV_FILE to project:region:instance." >&2
    exit 1
  }
  JOB_DB_FLAGS=(--set-cloudsql-instances "$CLOUDSQL_INSTANCE")
  RUN_DB_FLAGS=(--add-cloudsql-instances "$CLOUDSQL_INSTANCE")
else
  # Clear rather than omit: an omitted flag keeps whatever the previous
  # revision had attached. Jobs have no --clear-, so pass an empty list.
  JOB_DB_FLAGS=(--set-cloudsql-instances "")
  RUN_DB_FLAGS=(--clear-cloudsql-instances)
fi

# Say where, before anything mutates. The project can come from the env file or
# from ambient gcloud config, and an ambient value is otherwise invisible at the
# call site - which is how you deploy into the wrong project without noticing.
echo "== Target: project $PROJECT_ID / $REGION / db $DB_TARGET ${CLOUDSQL_INSTANCE:+($CLOUDSQL_INSTANCE)} =="

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
SHA=$(git -C "$REPO_ROOT" rev-parse --short HEAD)
IMAGE="$AR_HOST/$PROJECT_ID/$AR_REPO/$BACKEND_IMAGE_NAME:$SHA"

# Built from a pristine export of HEAD, so the :$SHA tag names exactly what
# is inside and work in progress never ships. Set DEPLOY_FROM_WORKTREE=1 to
# build the live tree instead; that image is tagged -dirty so it cannot be
# mistaken for the commit.
if [[ "${DEPLOY_FROM_WORKTREE:-0}" == 1 ]]; then
  IMAGE="$IMAGE-dirty"
  BUILD_CONTEXT="$REPO_ROOT/backend"
else
  BUILD_DIR=$(mktemp -d)
  trap 'rm -rf "$BUILD_DIR"' EXIT
  git -C "$REPO_ROOT" archive HEAD backend | tar -x -C "$BUILD_DIR"
  BUILD_CONTEXT="$BUILD_DIR/backend"
fi

echo "== Build $IMAGE =="
docker build -t "$IMAGE" --build-arg COMMIT_SHA="$SHA" "$BUILD_CONTEXT"

echo "== Push =="
gcloud auth configure-docker "$AR_HOST" --quiet
docker push "$IMAGE"

# Migrations run as a Cloud Run job from the exact image being deployed,
# before the new revision serves: a failed migration stops the deploy here
# instead of crash-looping instances at startup.
echo "== Migrate =="
gcloud run jobs deploy "$MIGRATE_JOB" \
  --image "$IMAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --service-account "$RUNTIME_SA" \
  "${JOB_DB_FLAGS[@]}" \
  --update-secrets "DATABASE_URL=$SECRET_DATABASE_URL:latest" \
  --command uv \
  --args run,--no-sync,alembic,upgrade,head \
  --max-retries 0
gcloud run jobs execute "$MIGRATE_JOB" --region "$REGION" --project "$PROJECT_ID" --wait

# No --[no-]allow-unauthenticated flag on purpose: our account cannot change
# the service's IAM policy, and passing --no-... on an already-public service
# would try to remove the admin's allUsers binding. Answer N if gcloud asks
# on the very first deploy; the admin makes the URL public separately.
# The SPA is the browser-facing origin (nginx proxies /api to us), so OAuth
# redirects must point there, not at this service.
# Cloud Run answers on two hostnames and status.url reports only one; the guard
# below 403s the other, so take the full set from the urls annotation.
# Fail closed: a failed describe and a service that does not exist both used to
# read as the empty string, and only one of them is safe. The fallback writes
# localhost into PUBLIC_BASE_URL and CORS on the LIVE service, so an unreadable
# lookup refuses; only a frontend that does not exist yet takes the fallback.
FRONTEND_MISSING=0
if ! FRONTEND_DESC=$(gcloud run services describe "$FRONTEND_SERVICE" --region "$REGION" \
    --project "$PROJECT_ID" \
    --format='value(status.url, metadata.annotations["run.googleapis.com/urls"])' 2>&1); then
  if [[ "$FRONTEND_DESC" != *"Cannot find service"* ]]; then
    echo "Could not read the frontend URL, so PUBLIC_BASE_URL cannot be trusted:" >&2
    echo "$FRONTEND_DESC" >&2
    exit 1
  fi
  FRONTEND_MISSING=1
  FRONTEND_DESC=""
  echo "No $FRONTEND_SERVICE service yet; falling back to localhost." >&2
fi
IFS=$'\t' read -r FRONTEND_URL FRONTEND_URLS <<<"$FRONTEND_DESC" || true
FRONTEND_URLS=$(printf '%s' "${FRONTEND_URLS:-}" | tr -d '[]"')

# A zero exit with no URL is the other half of the same trap: the service is
# there but reported nothing, and the localhost fallback would then be written
# onto the live revision. Only a service known to be absent may fall back.
if [[ -z "$FRONTEND_URL" && "$FRONTEND_MISSING" == 0 ]]; then
  echo "$FRONTEND_SERVICE returned no URL, so PUBLIC_BASE_URL cannot be trusted." >&2
  exit 1
fi
PUBLIC_BASE_URL="${FRONTEND_URL:-http://localhost:5173}"

# ADK wraps the WHOLE app in an origin guard (google/adk/cli/api_server.py):
# any non-GET carrying an Origin not on this list gets a bare 403, our own
# /api/v1 routes included. Browsers send Origin on every POST, same-origin
# ones too, so an empty list locks every real user out while curl still works.
# localhost stays listed for the local-frontend -> deployed-backend workflow.
ALLOWED_ORIGINS="${FRONTEND_URLS:-$PUBLIC_BASE_URL},$DEV_ORIGINS"

# Secrets the service carries, DECLARED rather than inherited. The two below are
# created by staging-bootstrap.sh, so they are always present.
SECRETS="DATABASE_URL=$SECRET_DATABASE_URL:latest,SESSION_SECRET=$SECRET_SESSION:latest"

# These two are not created by bootstrap: the token key was made by hand and the
# OAuth secret can only come from a human with the console value. A fresh
# environment has neither, and naming a secret that does not exist fails the
# whole deploy - so attach each only when it is actually there.
#
# Until now they survived purely because this call says --update-secrets rather
# than --set-secrets: no script mentioned TOKEN_ENCRYPTION_KEY at all, so a
# future edit to that one flag would have dropped it silently. Listing them
# turns "survives by grace" into "survives by statement".
#
# If describe fails for a reason other than absence, we skip the entry and
# --update- semantics preserve whatever the service already has. That degrades
# to the previous behaviour, never to a loss.
for pair in "TOKEN_ENCRYPTION_KEY=$SECRET_TOKEN_KEY" \
            "GOOGLE_CLIENT_SECRET=$SECRET_GOOGLE_CLIENT_SECRET"; do
  secret_name="${pair#*=}"
  if gcloud secrets describe "$secret_name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    SECRETS="$SECRETS,$pair:latest"
  else
    echo "NOTE: secret $secret_name not found; ${pair%%=*} left as-is." >&2
  fi
done

# The client id is public (Google shows it in the redirect URL) but per
# environment, so it comes from the environment file. Omit it when unset rather
# than writing an empty value: empty reads as unconfigured to auth.py and
# sources.py, which would turn a working sign-in into a 503.
OAUTH_ENV=""
if [[ -n "${GOOGLE_CLIENT_ID:-}" ]]; then
  OAUTH_ENV="@GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID"
else
  echo "NOTE: GOOGLE_CLIENT_ID unset; leaving whatever the service has." >&2
fi

# The worker that calls the model is off unless asked for (worker.py), so an
# environment that wants the real agent running has to say so here. Off stays
# the right default for an environment that only serves the UI.
AGENT_WORKER="${AGENT_WORKER:-on}"
# An argumentless genai.Client() (gemini.py) reads these three to pick Vertex
# over the public Gemini API and resolves credentials through ADC, which on
# Cloud Run is the runtime service account. Location is global because a wrong
# one surfaces as a model 404, not as a location error (backend/GEMINI.md).
VERTEX_LOCATION="${GOOGLE_CLOUD_LOCATION:-global}"
AGENT_ENV="@AGENT_WORKER=$AGENT_WORKER"
AGENT_ENV="$AGENT_ENV@GOOGLE_GENAI_USE_VERTEXAI=true"
AGENT_ENV="$AGENT_ENV@GOOGLE_CLOUD_PROJECT=$PROJECT_ID"
AGENT_ENV="$AGENT_ENV@GOOGLE_CLOUD_LOCATION=$VERTEX_LOCATION"
# AGENT_MODEL is deliberately unset: the default is gemini-3.5-flash
# (gemini.py), the model the Vertex response-schema work was settled against.

echo "== Deploy (public base: $PUBLIC_BASE_URL) =="
# update- rather than set-: set- replaces the whole set, so anything the service
# carries that is not listed here is deleted. TOKEN_ENCRYPTION_KEY is exactly
# that, and losing it fails silently until the first calendar operation.
# --no-cpu-throttling and a warm instance are what let the agent worker run:
# Cloud Run otherwise throttles CPU outside requests and reclaims idle
# instances, which stalls an in-process polling loop between clicks.
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --service-account "$RUNTIME_SA" \
  "${RUN_DB_FLAGS[@]}" \
  --update-secrets "$SECRETS" \
  --update-env-vars "^@^APP_ENV=staging@SESSION_COOKIE_SECURE=1@DEMO_LOGIN_ENABLED=1@PUBLIC_BASE_URL=$PUBLIC_BASE_URL@CORS_ALLOWED_ORIGINS=$ALLOWED_ORIGINS$OAUTH_ENV$AGENT_ENV" \
  --cpu-boost \
  --no-cpu-throttling \
  --min-instances "$BACKEND_MIN_INSTANCES" \
  --max-instances "$MAX_INSTANCES" \
  --memory "$BACKEND_MEMORY" \
  --cpu 1

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --project "$PROJECT_ID" --format 'value(status.url)')
echo "== Smoke test $URL/readyz =="
# Authenticated first (works before the URL is public), then anonymous.
AUTH_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$URL/readyz" || true)
ANON_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$URL/readyz" || true)
echo "authenticated: $AUTH_CODE, anonymous: $ANON_CODE"
if [[ "$ANON_CODE" == 200 ]]; then
  echo "Deployed and public: $URL"
elif [[ "$AUTH_CODE" == 200 ]]; then
  echo "Deployed; URL not public yet. Ask the admin to run:"
  echo "  gcloud run services add-iam-policy-binding $SERVICE --region $REGION --member=allUsers --role=roles/run.invoker"
else
  # Reading logs from the terminal needs roles/logging.viewer, which this
  # account does not hold; the console works without it.
  echo "readyz not answering (auth $AUTH_CODE / anon $ANON_CODE). Logs:" >&2
  echo "  https://console.cloud.google.com/run/detail/$REGION/$SERVICE/logs?project=$PROJECT_ID" >&2
  exit 1
fi
