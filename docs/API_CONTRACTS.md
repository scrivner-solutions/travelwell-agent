# API Contracts

The TravelWell API contract is [openapi.yaml](./openapi.yaml). It is the only
interface the frontend knows: the TypeScript client and every status enum are
generated from it (`npm run generate:api` in `frontend/`), and CI fails if the
generated client drifts from the spec.

This file summarizes the conventions; the spec itself is authoritative.

## Conventions

| Concern | Convention |
|---|---|
| Base path | `/api/v1`, session-cookie auth (`twl_session`, HttpOnly signed cookie) |
| Enums | Defined once in the spec, mirroring the Postgres enums in [schema.sql](./schema.sql); never re-declared by hand on either side |
| Errors | RFC 9457 `application/problem+json` with a stable machine `code`, including validation errors |
| Concurrency | Mutating requests carry the entity's `updated_at` as an optimistic-lock token; mismatch is a 409 and the client refetches. Retrying an already-applied mutation returns the success postcondition, not a conflict |
| Idempotency | Action-creating POSTs require a client-generated `Idempotency-Key` UUID header |
| Derived fields | `destination_name`, `state_line`, `needs_you_count` and friends are computed server-side, never client-side |
| Nullability | Nullable fields are omitted from `required`; update schemas accept explicit `null` to clear a value |

## Legacy endpoints

The hackathon-era concierge surface predates the contract and remains mounted
until the v1 surface fully replaces it:

| Endpoint | Status |
|---|---|
| `POST /api/recommend` | Legacy gym-finder pipeline; slated for retirement |
| `GET /resolve_location` | Legacy geocoding helper; a v1 equivalent lands with the Explore surface |

New work goes through `openapi.yaml` only.
