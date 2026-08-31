#!/usr/bin/env bash
# Schema drift checks (ADR-005). Three gates, each load-bearing:
#   1. docs/schema.sql is generated, so the committed copy must match what the
#      models render right now.
#   2. That file and the Alembic migration chain must produce identical
#      schemas: both are applied to scratch databases and their pg_dump
#      --schema-only outputs are diffed (pg_dump normalizes both sides). This
#      is the gate that sees what autogenerate cannot.
#   3. SQLAlchemy models must match the migrated database: `alembic check`
#      asserts an empty autogenerate diff, unfiltered, over every table.
#
# Requires: psql/createdb/dropdb/pg_dump matching the server major version,
# uv, and a reachable Postgres superuser via the standard PG* env vars.
# Local run from backend/: PGUSER=travelwell PGPASSWORD=travelwell ./scripts/check_schema_drift.sh
#
# That line assumes the Postgres client binaries are on PATH, and on a dev box
# running Postgres in docker they are not there at all - which made this the one
# gate nobody could run before pushing. Four shims that route into the container
# fix it. The only subtlety: `psql -f <hostfile>` must become stdin, because the
# container cannot see host paths.
#
#   SHIM=$(mktemp -d)
#   for c in psql pg_dump createdb dropdb; do
#     cat > "$SHIM/$c" <<EOF
#   #!/usr/bin/env bash
#   set -euo pipefail
#   a=(); f=""
#   while [ \$# -gt 0 ]; do
#     case "\$1" in -f) f="\$2"; shift 2;; *) a+=("\$1"); shift;; esac
#   done
#   if [ -n "\$f" ]; then
#     docker exec -i -e PGPASSWORD=travelwell backend-db-1 $c -h 127.0.0.1 -U travelwell "\${a[@]}" < "\$f"
#   else
#     docker exec -i -e PGPASSWORD=travelwell backend-db-1 $c -h 127.0.0.1 -U travelwell "\${a[@]}"
#   fi
#   EOF
#     chmod +x "$SHIM/$c"
#   done
#   PATH="$SHIM:$PATH" PGUSER=travelwell PGPASSWORD=travelwell ./scripts/check_schema_drift.sh
#
# `backend-db-1` is the compose container name; adjust if yours differs.
set -euo pipefail

: "${PGHOST:=localhost}"
: "${PGPORT:=5432}"
: "${PGUSER:=travelwell}"
: "${PGPASSWORD:=travelwell}"
export PGHOST PGPORT PGUSER PGPASSWORD

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEMA_SQL="$BACKEND_DIR/../docs/schema.sql"
REF_DB=twl_schema_ref
MIG_DB=twl_schema_mig

echo "Checking docs/schema.sql is current with the models"
GENERATED="$(mktemp)"
trap 'rm -f "$GENERATED"' EXIT
(cd "$BACKEND_DIR" && uv run python scripts/dump_schema.py --stdout) > "$GENERATED"
if ! diff -u "$SCHEMA_SQL" "$GENERATED"; then
  echo "STALE: docs/schema.sql is not what the models render." >&2
  echo "Run: cd backend && uv run python scripts/dump_schema.py" >&2
  exit 1
fi

dropdb --if-exists "$REF_DB"
dropdb --if-exists "$MIG_DB"
createdb "$REF_DB"
createdb "$MIG_DB"

echo "Applying docs/schema.sql to $REF_DB"
psql -q -v ON_ERROR_STOP=1 -d "$REF_DB" -f "$SCHEMA_SQL"

echo "Applying Alembic migrations to $MIG_DB"
(cd "$BACKEND_DIR" && DATABASE_URL="postgresql+psycopg://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$MIG_DB" uv run alembic upgrade head)

dump() {
  # -T alembic_version: bookkeeping table only the migrated side has.
  # \restrict/\unrestrict: random per-dump token pg_dump >= 16.10 emits.
  pg_dump --schema-only --no-owner --no-privileges -T alembic_version "$1" \
    | grep -vE '^(--|SET |SELECT pg_catalog\.set_config|\\restrict|\\unrestrict)' \
    | grep -v '^$'
}

echo "Diffing schemas (reference vs migrated)"
if ! diff -u <(dump "$REF_DB") <(dump "$MIG_DB"); then
  echo "DRIFT: docs/schema.sql and the migration chain disagree." >&2
  exit 1
fi

echo "Checking models against the migrated database (alembic check)"
(cd "$BACKEND_DIR" && DATABASE_URL="postgresql+psycopg://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$MIG_DB" uv run alembic check)

echo "Schema drift checks passed."
