# infra/

Deploy and provisioning scripts for TravelWell on Google Cloud Run.

## Status: this is one of TWO deploy paths, and which one survives is undecided

`.github/workflows/deploy.yml` describes the same deploy as a GitHub Action. It
has **never executed** (it fires on push to `main`, and the required repository
variables are unset). The scripts here are the path that has actually deployed
staging.

Do not treat either as canonical yet. Keeping both in sync by hand is what
caused the drift these scripts were repaired for: the workflow was fixed while
the scripts, being untracked, kept every defect. If you change deploy behaviour
in one, change it in the other or say plainly in your PR that you did not.

## Files

| File | What it does | How often |
|---|---|---|
| `staging-bootstrap.sh` | Creates the project's durable pieces: Cloud SQL instance, database, service accounts, IAM, secrets, Artifact Registry. | Once per environment |
| `deploy-staging.sh` | Backend: build, push, run migrations as a Cloud Run job, deploy, smoke test. | Every backend deploy |
| `deploy-frontend-staging.sh` | Frontend: build, push, deploy, smoke test. Reads the backend URL from Cloud Run rather than hardcoding it. | Every frontend deploy |
| `with-staging-db.sh` | Runs a local command against the staging database instead of your container. | Ad hoc |
| `config.env` | Names shared by every environment. Data, not logic. | Edited rarely |
| `staging.env.example` | Template for the per-environment file. Copy it outside the repo. | Read once |

Provisioning is not deployment. `staging-bootstrap.sh` creates things and can
spend money; the deploy scripts do not create infrastructure.

## Configuration

Two files, sourced in this order so the more specific wins:

1. **The environment file**, `$TRAVELWELL_STAGING_ENV` (default
   `~/.travelwell-staging.env`). Project, region, instance, OAuth client id.
   Untracked, one per environment. Start from `staging.env.example`.
2. **`config.env`**, in this directory. Service names, image names, secret
   names, sizing. Every entry is `${VAR:-default}`, so anything the environment
   file set survives.

Deploying a second environment means writing a second environment file. It
should never mean editing a script. If you find yourself editing one to change
where it deploys, that is a bug in the script.

Secrets are referenced by **name** only. Values live in Secret Manager and
appear in no file here.

## Usage

```sh
# once, per environment
bash infra/staging-bootstrap.sh

# per deploy, from a clean checkout of what you intend to ship
bash infra/deploy-staging.sh
bash infra/deploy-frontend-staging.sh
```

Both deploy scripts build from a pristine `git archive` of HEAD, so the image
tag names exactly what is inside it. `DEPLOY_FROM_WORKTREE=1` builds your live
tree instead and tags the image `-dirty` so it cannot be mistaken for a commit.

Each script prints its target project and region before anything mutates. Read
that line. An ambient `gcloud config` project is otherwise invisible at the call
site, which is how you deploy into the wrong project without noticing.

## Two traps worth knowing before you edit these

**`--set-*` replaces, `--update-*` merges.** `--set-secrets`, `--set-env-vars`
and `--set-cloudsql-instances` delete anything not listed in that same call. The
deploy scripts use `--update-*` everywhere they can, and list every secret
explicitly so the service's contents are declared rather than inherited.
`gcloud run jobs` has no `--add-cloudsql-instances`, so the migrate job still
uses `--set-`; that is a limitation of the tool, not a choice.

**A check whose safe answer is the empty string fails open.** `2>/dev/null ||
true` makes "the query failed" and "there is nothing there" identical, and a
zero exit with empty output does the same thing one layer down. The frontend URL
lookup in `deploy-staging.sh` guards both, because its fallback would otherwise
write `localhost` into `PUBLIC_BASE_URL` and CORS on the live service. Before
trusting any check you add here, make it fail on purpose and confirm it says so.
