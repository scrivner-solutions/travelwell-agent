# TravelWell Data Architecture

**Decision: PostgreSQL (Cloud SQL, or AlloyDB if we outgrow it) as the single system of record, with JSONB columns for the genuinely fluid agent data.** No NoSQL system of record. The full DDL is in [`schema.sql`](./schema.sql).

## Why SQL, concretely

The choice falls out of four properties of this product, all visible in the demo design and the architecture guide:

### 1. The domain is a small, strongly-related graph with one center

Everything hangs off a **Trip**: windows, plan versions, plan items, options, reservations, actions, events, runs, notifications. Every screen in the demo is a join:

| Screen | Query shape |
|---|---|
| Today | trip ⋈ today's calendar_events ⋈ plan_items ⋈ selected option ⋈ reservation |
| Trip timeline | calendar_events ∪ plan_items, ordered by time, badged by `status` |
| "How I got here" | window.bounds + item options (matched prefs, rejection reasons) |
| Trips sheet | trips by user + state, with derived "needs you" counts |
| Route on the map | today's non-skipped plan_items → places (walk legs) |

In a document store each of these either becomes N sequential reads or forces denormalization - and denormalized status has to be fan-out-updated every time an item moves through `suggested → planned → confirmed`. Relational joins make the read side trivial and the write side single-row.

### 2. The agent's core loop is a set of transactional state machines

Trip lifecycle (`detected → … → archived`), plan item status (`suggested → awaiting_user → confirmed / changed / skipped`), reservation flow (`pending → holding → confirmed | failed`), and the durable **PendingAction** (`proposed → approved → executing → completed | failed`). The guide's reliability rule - *never claim success because a tool was called* - needs:

- **Atomic multi-row transitions**: "action approved + reservation created + plan item marked working" must commit or roll back together.
- **Safe concurrent execution**: the action executor claims work with `SELECT … FOR UPDATE SKIP LOCKED`; an idempotency key makes retries harmless.
- **CHECK-enforced invariants**: a reservation can't be `confirmed` without a confirmation code; a rejected option must carry its rejection reason; one selected option per slot (partial unique index).

Firestore transactions exist but are limited and awkward across collections; none of the invariants can live in the database itself.

### 3. The event-driven architecture is powered by indexed range scans

The parts that make TravelWell feel "persistent without a running LLM" are queries:

- Scheduler tick: `trips WHERE state IN ('confirmed','upcoming') AND activation_at <= now()` - a partial index scan.
- Trigger classification: "is there an active trip for this user whose window overlaps this changed calendar event?" - indexed time-range join between `calendar_events` and `plan_items`.
- Conflict detection after a calendar sync: compare `content_hash`, then join changed events against confirmed plan items.

These cross-entity, time-range queries are exactly where document stores are weakest.

### 4. Observability is a first-class requirement

The guide asks that any activation be traceable: `event → run → plan/action → notification`, all sharing `trip_id`. With SQL the trace is one query, and ad-hoc questions ("how many replans fired last week? which reservations failed and why?") don't require building anything.

## Where the NoSQL instinct is right - and how we keep it

The genuinely schema-fluid data is the agent's own material: the TripContext snapshot handed to the model, structured outputs, event payloads, action payloads, window provenance. That data goes in **JSONB columns** (`agent_runs.context_snapshot`, `agent_runs.result`, `agent_events.payload`, `pending_actions.proposed_payload/execution_result`, `wellness_windows.bounds`). We get document-store flexibility exactly where shapes evolve, without giving up integrity where they don't. The rule in the DDL: *anything the UI or the scheduler queries by is a typed column; everything else may be JSONB.*

What would make Firestore attractive - realtime listeners and offline mobile sync - isn't the bottleneck for an agent whose state changes a handful of times per day and is server-driven. Push notifications + fetch-on-open covers the demo's UX. If we later want live in-app updates, Firestore can be added as a **read-side projection** (publish trip-state changes to it from the same Pub/Sub events), never as the system of record.

Scale is not an argument for NoSQL here: this is per-user planning data - hundreds of rows per trip, not telemetry. A single Postgres instance carries this to millions of users; the heavy geo/discovery work stays in the Places API (our `places` table is only a cache of surfaced candidates).

## Entity map

```
IDENTITY                    TRIP CORE                     PLANNING
users ──┬─ user_preferences trips ─┬─ trip_evidence       wellness_windows ◄─┐
        └─ connected_sources       ├─ calendar_events     plans ─ plan_items ─┴─ plan_item_options
                                   │      (cache)                    │              (selected /
places (venue cache) ◄─────────────┘                                 │               alternative /
                                                                     │               rejected+reason)
EXECUTION                              EVENT SPINE                   │
pending_actions (propose→confirm→      agent_events → agent_runs ────┘ (generated plans)
  execute→verify, audit JSONB)              │            │
reservations (incl. failed holds,           └────────────┴─→ notifications
  external fallback URL)
```

Sixteen tables in five groups. Key modeling decisions:

- **Trip is the tenant key.** Every planning/execution/event row carries `trip_id`; agent state never lives in a chat session.
- **Plans are versioned, items are slots, options keep the losers.** Re-planning writes a new plan version; a slot's rejected candidates stay with their `rejection_reason` - that's the "Also considered" screen, served from data instead of re-asking a model.
- **Secondary lifecycle states are derived, not stored.** `NEEDS_USER_INPUT` / `NEEDS_APPROVAL` / `ACTION_IN_PROGRESS` fall out of open `plan_items` and `pending_actions`; storing them would create two sources of truth.
- **Calendar data is a minimal cache, not a mirror.** Derived display fields + a content hash for change detection, pruned at archive time - keeping the design's promise: *"I read them, I do not store them."* Raw payloads and email bodies are never persisted.
- **Reasoning and execution are different tables.** Recommendations (plan_items/options) have no side effects; anything that touches the world goes through `pending_actions` with payload, result, and verification recorded.

## Operational notes

- **Postgres 15+ on Cloud SQL**; move to AlloyDB only on measured need. Cloud Run connects via the connector; runtime service account gets `cloudsql.client` only.
- **Migrations** with any standard tool (e.g. Atlas, Flyway, or `golang-migrate`); `schema.sql` is the reviewed baseline.
- **Retention**: prune `calendar_events` on trip archive; `agent_events`/`agent_runs` get a TTL policy (e.g. 90 days) once volumes matter.
- **Later, without re-architecture**: `pgvector` for preference/personalization embeddings; PostGIS if we ever do our own geo queries; read replicas for analytics.
