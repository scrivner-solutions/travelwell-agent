# GitHub Actions: CI and Deployment

## CI

[.github/workflows/ci.yml](../.github/workflows/ci.yml) runs on every pull
request, on pushes to non-main branches, and as a reusable workflow called by
the deploy workflow. Three independent jobs.

### Frontend gates

Node 20, `working-directory: frontend`:

1. **Generated client sync**: regenerates `src/api/schema.d.ts` from
   `backend/openapi.json` and fails on any diff. Types come from the contract
   the server actually serves rather than the hand-written design artifact
   (see docs/adr/004, which is local-only).
2. **Typecheck** (`tsc -b`), **lint** (ESLint including the import-boundary
   rules), **unit tests** (Vitest), **build** (Vite production build).

### Backend schema drift checks

Runs `backend/scripts/check_schema_drift.sh` against a `postgres:16` service.
Three gates: `docs/schema.sql` is regenerated from the models and must match the
committed copy; that file and the Alembic migration chain are applied to
separate scratch databases and their `pg_dump` output diffed; and `alembic
check` asserts the models match the migrated database. Together they hold the
generated reference, the models and operational truth in step.

Then two contract links neither the frontend job nor the schema check can see.
`scripts/dump_openapi.py` must reproduce the committed `backend/openapi.json`
exactly, which proves that file is what the routers serve; and
`scripts/check_openapi_drift.py` compares `docs/openapi.yaml` against that same
API, so the design document cannot decay into decoration.

### Backend tests

Runs `pytest tests/api tests/unit` against a `postgres:16` service. The suite
creates and migrates its own `travelwell_test` database (the `_test` suffix is
enforced by the test setup) and isolates tests by truncation. `tests/integration`
is excluded on purpose: it needs Vertex AI credentials the runner has no way to
hold, and a permanently red gate gates nothing.

All of these run locally with the same commands; see the backend and frontend
READMEs.

## Deployment

[.github/workflows/deploy.yml](../.github/workflows/deploy.yml) runs on merge to
main, and on manual dispatch for redeploying a chosen ref.

### Why the gates run again on main

Merges to main are merge commits, never squashes. A `pull_request` check runs
against a preview merge that GitHub computes at the time, not against the commit
that ends up on main, so on its own it never tests the tree that would deploy.
The deploy workflow therefore calls `ci.yml` as its `gates` job and every deploy
job depends on it. `ci.yml` keeps `branches-ignore: main` so this call is the
only run on main rather than a second one.

### What it does

`gates` and `preflight` run first, then the backend, then the frontend.

Neither deploy job contains a single `gcloud` command. Both run the same
scripts a human runs by hand, [infra/deploy-staging.sh](../infra/deploy-staging.sh)
and [infra/deploy-frontend-staging.sh](../infra/deploy-frontend-staging.sh), so
there is one implementation with two callers rather than two that promise to
match. This workflow holds only when and who deploys; everything described
below is what those scripts do.

The backend job builds `backend/`, pushes to Artifact Registry tagged with the
short commit SHA, runs migrations, deploys the service and smoke tests
`/readyz`, the one path the auth gate leaves open. Migrations run as a Cloud Run
job from the exact image being deployed, before the new revision serves, so a
failed migration fails the deploy instead of crash-looping instances at startup.

The frontend job then builds and deploys the nginx image with `BACKEND_URL` read
from the backend service that was just deployed, so it cannot drift from it, and
smoke tests the SPA shell, `/config.json` and `POST /api/v1/auth/demo` through
the nginx proxy. `VITE_API_BASE_URL` stays unset: an empty base keeps the SPA
calling `/api/v1` on its own origin, which is what keeps the session cookie
first-party.

Neither deploy passes `--allow-unauthenticated`. The IAM policy lives on the
service rather than the revision, so public access survives a redeploy untouched
and the deployer never needs permission to change it.

`CORS_ALLOWED_ORIGINS` is computed from the frontend service rather than
hardcoded. Cloud Run answers on two hostnames and `status.url` reports only one,
so the full set comes from the `run.googleapis.com/urls` annotation; ADK wraps
the whole app in an origin guard, and an origin missing from that list gets a
bare 403 on every non-GET, our own `/api/v1` routes included.

### Configuration

Repository variables, under Settings > Secrets and variables > Actions:

| Variable | Required | Meaning |
| --- | --- | --- |
| `GCP_PROJECT_ID` | yes | Google Cloud project |
| `GCP_WIF_PROVIDER` | yes | Full resource name of the Workload Identity provider |
| `GCP_DEPLOYER_SA` | yes | Deployer service account email |
| `GCP_REGION` | no | Cloud Run region; defaults to `us-central1` |
| `DB_TARGET` | no | `cloudsql` or `external`; defaults to `cloudsql` |
| `GCP_SQL_CONNECTION_NAME` | when `DB_TARGET` is `cloudsql` | Instance connection name, `project:region:instance` |
| `GOOGLE_CLIENT_ID` | no | Google OAuth client id; when unset the service keeps whatever it has |
| `AGENT_WORKER` | no | `on` runs the in-process loop that claims planning work and calls Gemini; defaults to `off`, which deploys the API only |

An unset repository variable arrives as an empty string, not as an absent one.
Every value in the scripts is `${VAR:-default}` and `:-` treats empty as unset,
so an unset variable falls through to the default above rather than blanking
the setting.

No secrets are stored. Authentication is Workload Identity Federation, so the
runner exchanges its own OIDC token for short-lived credentials and there is no
service account key to leak or rotate.

`DB_TARGET` exists because `DATABASE_URL` alone selects the database
(`app/db/engine.py`) but only Cloud SQL also needs its instance attached to the
revision. The deploy clears the attachment rather than omitting the flag, since
an omitted flag would keep whatever the previous revision had.

That makes `external` the direction that can destroy something: it detaches an
instance the service may still need.

Nothing checks the current attachment before clearing it, and nothing needs to.
**The ordering is what protects the service.** Migrations run first, as a Cloud
Run job built from the same image and handed the same emptied attachment
(`deploy-staging.sh:91`, `--max-retries 0` at `:100`, executed with `--wait` at
`:101`). A socket-form `DATABASE_URL` then has no `/cloudsql` socket to reach,
Alembic cannot connect, the job fails, and `set -euo pipefail` aborts the script
well before the `gcloud run deploy` at `:208`. The live service keeps its
attachment and keeps serving. A mismatched `DB_TARGET` costs you a red deploy,
not a detached database.

The smoke test is the second net: `/readyz` opens a connection and runs
`select 1` (`fast_api_app.py:158`), so the smoke test at `:225` fails on an unreachable database
even if the job execution does not surface one. That second net is worth
keeping, because `gcloud run jobs execute --wait` exiting non-zero on a failed
execution is implied by the documentation rather than stated, and has not been
measured here.

An earlier version of this section said the deploy reads the current attachment
and refuses to clear one it was not told about. That described the previous
`deploy.yml`, which did exactly that. The script both paths now run does not,
and that is deliberate: a guard cannot tell a mistake from an intended
migration, so it would refuse the one legitimate detach in this project's life
to buy a marginally earlier failure in a case the ordering already catches.

### Setup still required

The three required variables are unset (`gh variable list` and `gh secret list`
were both empty on 2026-09-01), so **the deploy jobs skip while the gates still
run**. Merges stay green and the run summary says why. Nothing in the workflow
changes when the variables are filled in; the deploys simply start happening.

Turning deploys on needs a Workload Identity pool and an OIDC provider
restricted to this repository, a deployer service account, and that account
granted Cloud Run Admin, Artifact Registry Writer, Service Account User on
`travelwell-runtime`, and Workload Identity User for the repository's
principal.

Whether the pool already exists, and who holds the project-level IAM to create
it, is a question about the live Google Cloud project and is deliberately not
answered here. An earlier version of this section stated that the pool did not
exist and that a project admin was required; that described a different Google
Cloud project than the one staging runs on today. Ask before assuming either
that the pool is missing or that this repository's owner cannot create it.
