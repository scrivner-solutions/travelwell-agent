#!/usr/bin/env bash
# Run a command against the STAGING database instead of the local container.
#
# Run from backend/, since the command usually is a uv invocation there:
#   cd backend
#   bash ../infra/with-staging-db.sh uv run uvicorn app.fast_api_app:app --reload
#   bash ../infra/with-staging-db.sh uv run alembic current
#
# The URL lives outside the repo and is never printed. An explicit DATABASE_URL
# beats .env, which load_dotenv() reads with override=False, so this wins over
# whatever .env says and reaches alembic too (alembic never loads .env).

set -euo pipefail

URL_FILE="${STAGING_DB_URL_FILE:-$HOME/.travelwell-staging-db-url}"

if [[ ! -r "$URL_FILE" ]]; then
  echo "No staging database URL at $URL_FILE" >&2
  echo "Create it (mode 600) with a URL that reaches the staging database, or" >&2
  echo "set STAGING_DB_URL_FILE to point elsewhere. Staging is Cloud SQL, so" >&2
  echo "from a laptop that means running the Cloud SQL Auth Proxy and writing a" >&2
  echo "TCP URL against 127.0.0.1 - the /cloudsql socket path only exists inside" >&2
  echo "Cloud Run." >&2
  exit 1
fi

DATABASE_URL="$(tr -d '\n' < "$URL_FILE")"
export DATABASE_URL
[[ -n "$DATABASE_URL" ]] || { echo "$URL_FILE is empty." >&2; exit 1; }

if (($# == 0)); then
  echo "Usage: bash ../infra/with-staging-db.sh <command> [args...]" >&2
  exit 2
fi

# Loud on stderr: this writes to the database the demo runs on.
echo "==> STAGING database (not your local container)" >&2
exec "$@"
