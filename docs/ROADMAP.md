# TravelWell Roadmap

Status tracker and sequencing for the whole app. This doc says **what order and
why, and what is done**; the specs it points to say what each piece is:

- Product and frontend phases with exit criteria: [FRONTEND_IMPLEMENTATION_PLAN.md](./FRONTEND_IMPLEMENTATION_PLAN.md) (section 9)
- Agent/event architecture: [AGENT_ARCHITECTURE_GUIDE.md](./AGENT_ARCHITECTURE_GUIDE.md)
- Data model: [schema.sql](./schema.sql) (operational truth: `backend/migrations/`)
- API contract: [openapi.yaml](./openapi.yaml)
- Data-access decisions: [adr/001-data-access-and-migrations.md](./adr/001-data-access-and-migrations.md)

Working agreements (solo dev): vertical slices; backend-first within each slice;
the frontend integrates against the real local backend (no dev-mock layer); every
slice retires any legacy endpoint or fixture it replaces; nothing merges with a
red CI gate (frontend gates + schema drift checks).

Legend: [x] done, [~] in progress / partial, [ ] not started.

---

## 0. Foundations (DONE)

- [x] Docs, design canvas, schema, and v1 OpenAPI contract in-repo
- [x] ADR-001: SQLAlchemy 2.0 async + Alembic + asyncpg
- [x] Frontend Phase 0: feature-first layout, tokens, primitives, typed routes,
      generated client, boundary lints, CI gates (build/lint/test green)
- [x] Backend walking skeleton: Alembic + initial migration (full schema),
      models for users/trips/evidence, email-code auth with `twl_session`
      cookie, `GET /me`, `GET/POST /trips`, seed script, compose Postgres,
      schema drift checks in CI
- [~] Phase 0 leftovers: Storybook, Playwright scaffold, Lighthouse PWA pass
- [ ] Exit check: sign-in + Today trip list from the local backend in the
      browser (the walking-skeleton smoke test), then commit the branch

## 1. Near term: the reactive app

Backend slices in order; each unblocks the frontend phase named next to it.
Frontend phase exit criteria live in the plan, section 9.

### Slice 1 - Trip core read path (frontend Phase 1)
- [ ] Models: wellness_windows, plans, plan_items, plan_item_options
- [ ] `GET /trips/{id}`, `/trips/{id}/today`, `/trips/{id}/timeline`,
      `/trips/{id}/confirm` (updated_at 409 pattern starts here)
- [ ] Seed grows windows, plan versions, items, options
- [ ] Backend integration tests start here (test Postgres; drift job stops
      being the only backend gate)

### Slice 2 - Structured agent output spike (de-risks Phase 5)
- [ ] Agent run writes plan_items/plan_item_options + agent_runs row via a
      schema-constrained output; `parse_markdown_to_recommendations` retired
- [ ] Decision recorded: keep or replace the ADK pipeline shape for planning runs

### Slice 3 - Plan interaction (frontend Phase 2)
- [ ] `POST /plan-items/{id}/accept | select-option | skip`, provenance read
- [ ] Option swap = option_state flip; rejection reasons surfaced
- [ ] 409 concurrency path tested end to end

### Slice 4 - Actions and reservations (frontend Phase 3)
- [ ] pending_actions executor: proposed -> approved -> executing ->
      completed/failed, with verification step and FOR UPDATE SKIP LOCKED claim
- [ ] Idempotency-Key becomes real deduplication
- [ ] `POST /actions`, `/actions/{id}/approve`, SSE `/actions/{id}/events`
- [ ] Reservation flow with simulated provider + external_link fallback
      (real provider integration is deliberately out of scope; see Decisions)

### Slice 5 - Auth hardening (deploy prerequisite)
- [ ] Real email delivery + persistent one-time codes (multi-instance safe)
- [ ] OAuth start/callback for google/apple
- [ ] SESSION_SECRET and secure-cookie settings from Secret Manager
- [ ] Flip OpenAPI authority to generated-from-code (see Decisions): export
      `/openapi.json` to the repo, frontend codegen reads it, CI diff check
      keeps it honest, ADR written; hand-edits to openapi.yaml stop here

## 2. Mid term: the rest of the screens

### Slice 6 - Explore and map (frontend Phase 4)
- [ ] `GET /explore` over Places with the places cache table
- [ ] `GET/PUT /me/preferences` driving filters and ranking
- [ ] Reuse/port of `/resolve_location` under /api/v1

### Slice 7 - Agent screen and events-in (frontend Phase 5)
- [ ] `POST /events` (user_text, ui_action), `GET /runs/{id}` + SSE stream
- [ ] Run -> new plan version -> diff view data
- [ ] Voice capture is frontend-only on top of the same endpoint (descope
      candidate; see Decisions)

### Slice 8 - Profile surfaces
- [ ] `GET/PUT /me/preferences` complete (autonomy toggles enforced by the
      executor from Slice 4)
- [ ] `GET /me/sources` + connect/revoke flows (pairs with Slice 9 ingestion)

## 3. Long term: the proactive product

This layer is the product's premise and its name. Nothing here is optional.

### Slice 9 - Ingestion and trip detection
- [ ] Calendar (and later Gmail) OAuth grants in connected_sources; sync into
      calendar_events with content_hash change detection
- [ ] Trip detection writes trips (detection_confidence + trip_evidence);
      detect -> confirm flow live end to end
- [ ] Privacy promise enforced: derived fields only, no raw payloads stored

### Slice 10 - Event spine and scheduler
- [ ] All triggers write agent_events; classifier sets disposition
- [ ] Scheduler: trips.activation_at scan (T-7d activation) + daily check-ins
- [ ] Replan on calendar conflict: change event -> run -> superseding plan
      version -> notification

### Slice 11 - Notifications and PWA hardening (frontend Phase 6)
- [ ] Web Push end to end (VAPID keys, permission UX, deep links,
      opened tracking against /notifications)
- [ ] Conflict intervention surface; offline read cache with honest staleness

### Slice 12 - Production ops
- [ ] Cloud SQL Postgres; migrations as a deploy step (never on app startup)
- [ ] Secrets via Secret Manager; connection pooling sized for Cloud Run
- [ ] Legacy endpoints and use_mock_data fully retired
- [ ] Observability: run/action failure visibility beyond logs

## Ongoing after Slice 12

Notification inbox history, desktop responsive extension, localization
readiness (plan, section 9, "ongoing").

---

## Decisions and descope log

| Question | Status |
|---|---|
| OpenAPI authority: keep hand-written yaml vs generate from FastAPI `/openapi.json` | Decided 2026-08-26: flip to generate-from-code once the reactive surface is implemented (after Slice 4). Until then the yaml stays authoritative as the design spec. Execution details (export script, CI contract-drift check, stable operation ids for the frontend client) get their own ADR when the flip lands |
| Real reservation providers (OpenTable etc.) | Descoped to simulated provider + external_link fallback until the rest ships |
| Voice capture (Phase 5) | Descope candidate; text path ships first, voice is additive on the same `/events` endpoint |
| Apple Calendar / Gmail sources | Google Calendar first; others behind the same connected_sources shape |
| Timezone for manually created trips | Currently the user's home timezone; real destination resolution lands with Slice 6 geocoding |

## Status snapshot (2026-08-26)

Everything through the walking skeleton is built and verified but
**uncommitted** on `frontend-redesign`. Next action: run the smoke test
(compose up, migrate, seed, uvicorn, npm dev, sign in as the seeded demo
user), then commit in reviewable slices, then start Slice 1.
