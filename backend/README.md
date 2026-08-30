# TravelWell backend

FastAPI (async) + SQLAlchemy 2.0 + Alembic on PostgreSQL. The v1 API lives
under `/api/v1` (contract: [docs/openapi.yaml](../docs/openapi.yaml)); the
legacy hackathon concierge (`app/agent.py`, `POST /api/recommend`) is still
mounted and retires as the v1 surface replaces it.

## Structure

```
backend/
├── app/
│   ├── api/         # /api/v1: auth, trips, profile; problem+json errors
│   ├── db/          # SQLAlchemy models + async engine
│   ├── agent.py     # legacy ADK concierge pipeline
│   └── fast_api_app.py
├── migrations/      # Alembic; operational schema truth
├── scripts/         # seed, schema drift check, dev session helper
└── tests/api/       # integration tests against a real Postgres
```

## Requirements

- **uv**: Python package manager, used for everything here -
  [install](https://docs.astral.sh/uv/getting-started/installation/)
- **Docker**: for the local Postgres (`compose.yaml`)

## Local development

```bash
docker compose up -d               # Postgres 16 on localhost:5432
uv run alembic upgrade head        # apply migrations
uv run python scripts/seed.py      # demo user + trips (idempotent)
uv run uvicorn app.fast_api_app:app --port 8000
```

Connection comes from `DATABASE_URL` (defaults to the compose credentials).
Sign in with `demo@travelwell.dev` and read the one-time code from the server
log.

## Database

Operational schema truth is `migrations/`; the models in `app/db/models.py`
are the authored description of the schema, and
[docs/schema.sql](../docs/schema.sql) is generated from them by
`scripts/dump_schema.py`. Change process: edit the models, write a migration,
then regenerate `schema.sql`. `scripts/check_schema_drift.sh` holds the three
together in CI.

Drift checks run locally with
`PGUSER=travelwell PGPASSWORD=travelwell ./scripts/check_schema_drift.sh`.

## Tests

With the compose Postgres running:

```bash
uv run pytest tests/api
```

The suite creates and migrates its own `travelwell_test` database on the same
instance (the `_test` suffix is enforced) and isolates tests by truncation.
The same suite runs in CI against a `postgres:16` service.
