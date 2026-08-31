#!/usr/bin/env bash
# One-time staging provisioning for the TravelWell backend. Idempotent:
# every resource is created only if missing, and re-runs never rotate the
# database password or session secret.
#
#   bash infra/staging-bootstrap.sh
#
# Written for the scoped-role model: run as the account holding Cloud SQL
# Admin + Secret Manager Admin + Artifact Registry Admin + Service Account
# Admin. Steps needing more power (enabling APIs, project-level IAM) degrade
# to printed asks for the project admin instead of failing the run.
#
# GitHub-Actions keyless deploy (WIF + deployer SA) is parked while deploys
# are manual; run with SETUP_GITHUB_DEPLOY=1 to provision that too.

set -euo pipefail

# Environment identifiers are config, not code. This file used to hardcode the
# EMPLOYER's project, and this script PROVISIONS - it creates a Cloud SQL
# instance, secrets, a service account and IAM bindings. A wrong project here
# spends money in someone else's account, so it is the worst of the three to
# leave pinned.
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


# Creates billable resources, so say where before doing any of it.
echo "== Provisioning into project: $PROJECT_ID ($REGION) =="
SETUP_GITHUB_DEPLOY="${SETUP_GITHUB_DEPLOY:-0}"

# DATABASE_URL alone selects the target (app/db/engine.py). cloudsql provisions
# an instance here; any other value means the database already exists elsewhere
# (Supabase, Neon, ...) and this script only stores its URL.
DB_TARGET="${DB_TARGET:-cloudsql}"
STAGING_DB_URL_FILE="${STAGING_DB_URL_FILE:-$HOME/.travelwell-staging-db-url}"

# The instance is environment-specific, so it is NOT defaulted here: this script
# CREATES it when missing, and a default would quietly create the wrong one. It
# must be named in the environment file, next to GCP_SQL_CONNECTION_NAME whose
# last component it is.
SQL_INSTANCE="${GCP_SQL_INSTANCE:-}"
if [[ "$DB_TARGET" == cloudsql && -z "$SQL_INSTANCE" ]]; then
  echo "DB_TARGET is cloudsql but GCP_SQL_INSTANCE is unset." >&2
  echo "Set it in $ENV_FILE to the instance name alone, e.g. the third field of" >&2
  echo "GCP_SQL_CONNECTION_NAME (project:region:INSTANCE)." >&2
  echo "This script CREATES the instance when it is missing, so an unset name" >&2
  echo "must refuse rather than guess - guessing here costs money." >&2
  exit 1
fi

# Everything below comes from config.env; these are names, not identifiers.
RUNTIME_SA="$RUNTIME_SA_NAME"
DEPLOYER_SA="$DEPLOYER_SA_NAME"

RUNTIME_SA_EMAIL="$RUNTIME_SA@$PROJECT_ID.iam.gserviceaccount.com"
DEPLOYER_SA_EMAIL="$DEPLOYER_SA@$PROJECT_ID.iam.gserviceaccount.com"
ADMIN_CMDS=()

# --- Guard rails ------------------------------------------------------------
# Wrong-account protection: set BOOTSTRAP_GCLOUD_ACCOUNT to enforce a specific
# account non-interactively; otherwise confirm the active one by hand.
ACTIVE_ACCOUNT=$(gcloud config get-value account 2>/dev/null)
if [[ -n "${BOOTSTRAP_GCLOUD_ACCOUNT:-}" ]]; then
  if [[ "$ACTIVE_ACCOUNT" != "$BOOTSTRAP_GCLOUD_ACCOUNT" ]]; then
    echo "Active gcloud account is '$ACTIVE_ACCOUNT', expected '$BOOTSTRAP_GCLOUD_ACCOUNT'." >&2
    echo "Run: gcloud config set account $BOOTSTRAP_GCLOUD_ACCOUNT" >&2
    exit 1
  fi
else
  read -r -p "Provision '$PROJECT_ID' as '$ACTIVE_ACCOUNT'? [y/N] " reply
  [[ "$reply" == [yY]* ]] || exit 1
fi
gcloud config set project "$PROJECT_ID" --quiet
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

echo "== APIs =="
APIS=(run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com)
[[ "$DB_TARGET" == cloudsql ]] && APIS+=(sqladmin.googleapis.com)
[[ "$SETUP_GITHUB_DEPLOY" == 1 ]] && APIS+=(iamcredentials.googleapis.com sts.googleapis.com)
if ! gcloud services enable "${APIS[@]}" >/dev/null 2>&1; then
  echo "  could not enable APIs from this account; make sure these are on: ${APIS[*]}"
fi

echo "== Artifact Registry repo =="
if ! gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPO" \
    --repository-format=docker --location="$REGION" \
    --description="TravelWell images"
fi

if [[ "$DB_TARGET" == cloudsql ]]; then
  echo "== Cloud SQL (Postgres 17, smallest tier) =="
  if ! gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
    gcloud sql instances create "$SQL_INSTANCE" \
      --database-version=POSTGRES_17 \
      --edition=enterprise \
      --tier=db-f1-micro \
      --region="$REGION" \
      --storage-size=10GB
  fi
  if ! gcloud sql databases describe "$DB_NAME" --instance="$SQL_INSTANCE" >/dev/null 2>&1; then
    gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE"
  fi
else
  echo "== Database: $DB_TARGET, provisioned outside this script =="
fi

echo "== Secrets =="
if gcloud secrets describe $SECRET_DATABASE_URL >/dev/null 2>&1; then
  # Idempotent by contract: re-runs never rotate a stored credential.
  echo "  $SECRET_DATABASE_URL exists, left alone. To retarget it:"
  echo "  gcloud secrets versions add $SECRET_DATABASE_URL --data-file=PATH"
elif [[ "$DB_TARGET" == cloudsql ]]; then
  CONNECTION_NAME="$PROJECT_ID:$REGION:$SQL_INSTANCE"
  # hex password: URL-safe inside DATABASE_URL, no encoding pitfalls
  DB_PASSWORD=$(openssl rand -hex 24)
  if gcloud sql users list --instance="$SQL_INSTANCE" --format='value(name)' | grep -qx "$DB_USER"; then
    gcloud sql users set-password "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD"
  else
    gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="$DB_PASSWORD"
  fi
  # psycopg reads host=/dir as a unix socket; app/db/engine.py owns the driver
  printf 'postgresql+psycopg://%s:%s@/%s?host=/cloudsql/%s' \
    "$DB_USER" "$DB_PASSWORD" "$DB_NAME" "$CONNECTION_NAME" |
    gcloud secrets create $SECRET_DATABASE_URL --data-file=-
else
  # Piped from the file so the URL is never a shell argument or script output.
  [[ -r "$STAGING_DB_URL_FILE" ]] || {
    echo "DB_TARGET=$DB_TARGET needs a database URL at $STAGING_DB_URL_FILE" >&2
    exit 1
  }
  tr -d '\n' < "$STAGING_DB_URL_FILE" |
    gcloud secrets create $SECRET_DATABASE_URL --data-file=-
fi
if ! gcloud secrets describe $SECRET_SESSION >/dev/null 2>&1; then
  openssl rand -hex 32 | tr -d '\n' |
    gcloud secrets create $SECRET_SESSION --data-file=-
fi

echo "== Service accounts =="
SAS=("$RUNTIME_SA")
[[ "$SETUP_GITHUB_DEPLOY" == 1 ]] && SAS+=("$DEPLOYER_SA")
for sa in "${SAS[@]}"; do
  if ! gcloud iam service-accounts describe "$sa@$PROJECT_ID.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$sa" --display-name="TravelWell $sa"
  fi
done

echo "== IAM bindings (resource-level) =="
# A new service account is describable before IAM accepts it as a member on
# another resource, so a first run races that propagation and 400s. Retry.
retry_binding() {
  for _ in 1 2 3 4 5; do
    "$@" >/dev/null 2>&1 && return 0
    sleep 5
  done
  "$@" >/dev/null  # last try unmuted, so a real failure still stops the script
}

# Runtime reads its two secrets and nothing else in Secret Manager.
for secret in $SECRET_DATABASE_URL $SECRET_SESSION; do
  retry_binding gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:$RUNTIME_SA_EMAIL" --role=roles/secretmanager.secretAccessor --quiet
done

# Deploying with --service-account needs actAs on that account. No project-level
# Service Account User is held, but this SA's own policy is ours to set.
retry_binding gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA_EMAIL" \
  --member="user:$ACTIVE_ACCOUNT" --role=roles/iam.serviceAccountUser --quiet

# Project-level grants need the admin; attempted so an admin-run completes
# alone, denials collected and printed at the end.
try_project_binding() {
  if ! gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$1" --role="$2" --quiet >/dev/null 2>&1; then
    ADMIN_CMDS+=("gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$1 --role=$2")
  fi
}
if [[ "$DB_TARGET" == cloudsql ]]; then
  # Cloud SQL has no resource-level IAM, so connect rights are project-only.
  try_project_binding "$RUNTIME_SA_EMAIL" roles/cloudsql.client
fi
try_project_binding "$RUNTIME_SA_EMAIL" roles/logging.logWriter

if [[ "$SETUP_GITHUB_DEPLOY" == 1 ]]; then
  echo "== GitHub deploy: deployer SA bindings + WIF =="
  retry_binding gcloud artifacts repositories add-iam-policy-binding "$AR_REPO" --location="$REGION" \
    --member="serviceAccount:$DEPLOYER_SA_EMAIL" --role=roles/artifactregistry.writer --quiet
  retry_binding gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA_EMAIL" \
    --member="serviceAccount:$DEPLOYER_SA_EMAIL" --role=roles/iam.serviceAccountUser --quiet
  try_project_binding "$DEPLOYER_SA_EMAIL" roles/run.admin

  if ! gcloud iam workload-identity-pools describe "$WIF_POOL" --location=global >/dev/null 2>&1; then
    gcloud iam workload-identity-pools create "$WIF_POOL" \
      --location=global --display-name="GitHub Actions"
  fi
  if ! gcloud iam workload-identity-pools providers describe "$WIF_PROVIDER" \
    --workload-identity-pool="$WIF_POOL" --location=global >/dev/null 2>&1; then
    gcloud iam workload-identity-pools providers create-oidc "$WIF_PROVIDER" \
      --workload-identity-pool="$WIF_POOL" --location=global \
      --issuer-uri="https://token.actions.githubusercontent.com" \
      --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
      --attribute-condition="assertion.repository=='$GITHUB_REPO'"
  fi
  gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_SA_EMAIL" \
    --role=roles/iam.workloadIdentityUser \
    --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$WIF_POOL/attribute.repository/$GITHUB_REPO" \
    --quiet >/dev/null
fi

echo
if ((${#ADMIN_CMDS[@]})); then
  echo "== ACTION NEEDED: ask the project admin to run =="
  printf '%s\n' "${ADMIN_CMDS[@]}"
  echo
fi
echo "== After the first deploy, the service URL goes public with (admin) =="
echo "gcloud run services add-iam-policy-binding $BACKEND_SERVICE --region $REGION --member=allUsers --role=roles/run.invoker"
echo
echo "== Optional, to read deploy logs from the terminal (admin) =="
echo "gcloud projects add-iam-policy-binding $PROJECT_ID --member=user:$ACTIVE_ACCOUNT --role=roles/logging.viewer"
echo
if [[ "$SETUP_GITHUB_DEPLOY" == 1 ]]; then
  echo "== Set these GitHub Actions repository VARIABLES =="
  echo "GCP_PROJECT_ID   = $PROJECT_ID"
  echo "GCP_DEPLOYER_SA  = $DEPLOYER_SA_EMAIL"
  echo "GCP_WIF_PROVIDER = projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$WIF_POOL/providers/$WIF_PROVIDER"
else
  echo "== Done. Deploy with: bash infra/deploy-staging.sh =="
fi
