# TravelWell Architecture

TravelWell is a proactive travel wellness agent: a React PWA over a FastAPI
backend and PostgreSQL, with an agent layer that activates around trips. This
document describes the system as built; the API surface is defined in
[openapi.yaml](./openapi.yaml) and the data model in [schema.sql](./schema.sql)
and [ERD.md](./ERD.md).

---

## System shape

```mermaid
graph TB
    subgraph Client [React 19 PWA]
        Screens[Feature screens: Today, Trip, Explore, Agent, Profile]
        Router[TanStack Router - typed routes and search params]
        Query[TanStack Query - server cache]
        GenClient[Generated OpenAPI client - schema.d.ts]
        Screens --> Router --> Query --> GenClient
    end

    subgraph Backend [FastAPI - /api/v1]
        GenClient -->|session cookie| Auth[Auth: email-code, signed twl_session]
        GenClient --> Trips[Trips: list, detail, today, timeline, confirm, create]
        GenClient --> Profile[Profile: preferences, connected sources]
        Trips --> ORM[SQLAlchemy 2.0 async]
        Profile --> ORM
    end

    subgraph Data [PostgreSQL 16]
        ORM --> DB[("users, trips, plans, plan_items, wellness_windows,<br/>calendar_events, pending_actions, agent_events")]
        Alembic[Alembic migrations] --> DB
    end

    subgraph Legacy [Hackathon-era concierge - slated for retirement]
        RecRoute[POST /api/recommend - ADK pipeline]
    end
```

The legacy concierge endpoints (`/api/recommend`, `/resolve_location`) remain
mounted for reference and retire as the v1 surface replaces them.

## Contract-first workflow

`docs/openapi.yaml` is the single interface between frontend and backend:

1. The contract is edited first (endpoint shapes, enums, derived fields).
2. `npm run generate:api` regenerates the TypeScript client
   (`frontend/src/api/schema.d.ts`); status enums are never re-declared by
   hand.
3. Backend Pydantic schemas mirror the contract explicitly; derived fields
   (`destination_name`, `state_line`, `needs_you_count`) are computed
   server-side, never client-side.
4. CI regenerates the client and fails on drift.

The same discipline applies to the schema: `backend/migrations/` is
operational truth, the SQLAlchemy models are the authored description, and
`docs/schema.sql` is generated from them. CI regenerates it, applies it and
the migration chain to scratch databases, and diffs the results.

## API conventions

- **Auth**: email one-time code exchanges for a signed `twl_session` cookie
  (HttpOnly; no tokens in JavaScript). Google OAuth terminates in the same
  session mechanics.
- **Errors**: RFC 9457 `application/problem+json` with a stable machine
  `code` on every non-2xx, including validation errors.
- **Concurrency**: mutating requests carry the entity's `updated_at` as an
  optimistic-lock token; a mismatch is a 409 telling the client to refetch.
  Retries of an already-applied mutation get the success postcondition, not
  a conflict.
- **Idempotency**: action-creating POSTs require a client-generated
  `Idempotency-Key` UUID header.

## Trip lifecycle

The trip, not the chat session, owns agent state. A trip is one contiguous
period of displacement from home; every planning, action, and event row
carries `trip_id`.

```mermaid
stateDiagram-v2
    [*] --> detected: calendar detection
    [*] --> confirmed: manual create
    detected --> confirmed: user confirms
    detected --> dismissed: user dismisses
    confirmed --> preparing: agent activates near departure
    preparing --> active: plan ready, trip underway
    active --> completed: return home
    completed --> archived
```

Design rules the schema encodes:

- **Reasoning is separated from execution.** Recommendations live in
  `plan_items`/`plan_item_options` (ranked, with explanations and rejection
  reasons). Anything with a real-world side effect flows through
  `pending_actions` with an explicit propose, approve, execute, verify
  pipeline; user approval gates are data, not code paths.
- **Plans are versioned, never mutated in place.** A schedule change produces
  a superseding plan version, so "what changed and why" is always answerable.
- **Detection proposes, never assumes.** Detected trips carry evidence rows
  and a confidence score; only the user promotes them.
- **Privacy**: ingestion stores derived fields from calendar and email
  sources, not raw payloads.

## Frontend structure

Feature-first layout with lint-enforced boundaries (features never import
each other; UI primitives never import application layers; hex colors exist
only in the token layer):

```
frontend/src/
  routes/         thin URL layer: params, ?sheet= and ?trip= search params,
                  guards, code-split points
  features/       vertical slices: onboarding, today, trip, explore, profile
  components/ui/  primitives (Button, Card, Sheet, ...)
  api/            generated client + typed query options
  styles/         design tokens
  lib/            runtime config, date and trip helpers
```

Configuration is runtime, not build time: the container entrypoint writes
`/config.json` at start and the app reads it before mounting, so one image
serves every environment.

## Agent layer (in design)

The proactive layer (calendar ingestion, trip detection, planning runs on an
event spine, notifications) is designed but not yet implemented; the
database tables it will drive (`agent_events`, `agent_runs`,
`pending_actions`, `notifications`) ship with the schema above so the
reactive app is already built against the final shapes.

## Places provider (Google Maps Platform)

`app/services/places/google.py` is the only code that talks to Google Maps
Platform. Two decisions there are worth stating, because both are easy to
undo by accident.

**Credentials are ADC, not an API key** (decided 2026-08-31). The provider
authenticates with Application Default Credentials and sends a bearer token,
so no Maps API key exists to leak, scope or rotate. Two consequences:

- **A development machine needs `gcloud auth application-default login`**
  before any Places call works. There is nothing to paste into `.env`, and
  the first symptom otherwise is a 503 from `GET /api/v1/geocode`.
- Free text resolves through **Places text search**, not the Geocoding API.
  Geocoding v3 (`maps.googleapis.com/maps/api/geocode/json`) accepts an API
  key and nothing else; v4 lives on a different host and is a separate
  service to enable, so text search on the host we already call keeps this to
  one credential and one service.

Three places still call Geocoding v3 with `GOOGLE_MAPS_API_KEY`, all of them
prototype surface that dies with the rest of that layer:
`app/services/google_maps.py`, `app/tools/facility_tools.py`, and the two
prototype routes in `app/fast_api_app.py`. None has had a key since the GCP
migration, so all three were already failing before the seam moved; the seam's
move did not break them and does not fix them. Do not "tidy up" that env var
while they still exist.

**The field mask keeps `editorialSummary`, deferred 2026-08-31** for the
hackathon demo, to revisit after. Requesting that one field prices *every*
Nearby Search at the Enterprise+Atmosphere tier: 1,000 free calls a month
instead of Pro's 5,000. The per-area cache TTL (14 days) should keep real
volume well under that in the meantime.

Removing it is not a free five-fold increase, and anyone attempting the trim
should know it costs three changes, not one:

1. Drop the field from `_FIELD_MASK`.
2. Drop the hardcoded summaries from the demo fixture
   (`app/services/demo_user/data.py`). Otherwise seeded places keep rich
   summaries while live ones come back blank in the same table, and the
   planner reads provenance as quality - the summary is an *input to the
   model* at `app/agent/context.py`'s candidate build, not decoration.
3. Rework `PlaceCard.tsx`, where the price badge renders only when the
   summary is absent.

**Revisit when** the hackathon is over, or Places usage approaches 1,000
calls a month - whichever comes first. Nothing fires automatically.

