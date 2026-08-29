# GitHub Actions: CI and Deployment

## CI

[.github/workflows/ci.yml](../.github/workflows/ci.yml) runs on every pull
request and on pushes to non-main branches. Three independent jobs:

### Frontend gates

Node 20, `working-directory: frontend`:

1. **Generated client sync**: regenerates `src/api/schema.d.ts` from
   `docs/openapi.yaml` and fails on any diff, so the contract and the client
   cannot drift apart.
2. **Typecheck** (`tsc -b`), **lint** (ESLint including the import-boundary
   rules), **unit tests** (Vitest), **build** (Vite production build).

### Backend schema drift checks

Runs `backend/scripts/check_schema_drift.sh` against a `postgres:16` service:
applies `docs/schema.sql` and the Alembic migration chain to separate scratch
databases and diffs the `pg_dump` output, then runs `alembic check` so the
SQLAlchemy models match the migrated database. Either difference fails the
job. This keeps the readable schema reference honest against operational
truth in `backend/migrations/`.

### Backend API integration tests

Runs `pytest tests/api` against a `postgres:16` service. The suite creates
and migrates its own `travelwell_test` database (the `_test` suffix is
enforced by the test setup) and isolates tests by truncation.

All three checks also run locally with the same commands; see the backend and
frontend READMEs.

## Deployment

Automated deployment is not configured in this repository yet. The target
platform is Google Cloud Run (backend container plus nginx-served frontend
container) with Cloud SQL Postgres; migrations run as a deploy step, never on
app startup. The deploy workflow will be documented here when it lands.
