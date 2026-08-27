#!/usr/bin/env bash
# Schema drift checks (ADR-001 point 5). Two gates, both load-bearing:
#   1. docs/schema.sql and the Alembic migration chain must produce identical
#      schemas: both are applied to scratch databases and their pg_dump
#      --schema-only outputs are diffed (pg_dump normalizes both sides).
#   2. SQLAlchemy models must match the migrated database: `alembic check`
#      asserts an empty autogenerate diff (limited to modeled tables by
#      migrations/env.py).
#
# Requires: psql/createdb/dropdb/pg_dump matching the server major version,
# uv, and a reachable Postgres superuser via the standard PG* env vars.
# Local run from backend/: PGUSER=travelwell PGPASSWORD=travelwell ./scripts/check_schema_drift.sh
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

dropdb --if-exists "$REF_DB"
dropdb --if-exists "$MIG_DB"
createdb "$REF_DB"
createdb "$MIG_DB"

echo "Applying docs/schema.sql to $REF_DB"
psql -q -v ON_ERROR_STOP=1 -d "$REF_DB" -f "$SCHEMA_SQL"

echo "Applying Alembic migrations to $MIG_DB"
(cd "$BACKEND_DIR" && DATABASE_URL="postgresql+asyncpg://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$MIG_DB" uv run alembic upgrade head)

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
(cd "$BACKEND_DIR" && DATABASE_URL="postgresql+asyncpg://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$MIG_DB" uv run alembic check)

echo "Schema drift checks passed."
