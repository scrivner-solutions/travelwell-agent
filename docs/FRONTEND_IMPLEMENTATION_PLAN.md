# TravelWell Frontend Implementation Plan (Production PWA)

**Deliverable: a production Progressive Web App - not a re-hosted demo.** The Claude Design
canvas ([`design/TravelWellPlan.dc.html`](../design/TravelWellPlan.dc.html)) is the *visual and
interaction specification*. **Implementation happens inside the `travelwell-agent` monorepo,
on the `frontend-redesign` branch** - building on its structure, tooling, and deploy path, not
rebooting it - on top of
the system of record ([`schema.sql`](./schema.sql), [`DATA_ARCHITECTURE.md`](./DATA_ARCHITECTURE.md))
and the agent backend ([architecture guide](./AGENT_ARCHITECTURE_GUIDE.md)),
to the standards in the [design brief](./UX_DESIGN_BRIEF.md).

---

## 1. The prime directive: the design canvas is a spec, not a codebase

The `.dc.html` file is an interactive prototype built for design review. It contains two very
different kinds of material, and every implementer must be able to tell them apart.

### 1.1 What to EXTRACT from the canvas (product truth)

| Category | Where it lives in the canvas | What to do with it |
|---|---|---|
| **Design tokens** | Inline styles + "Style & aesthetic" sidebar: ink `#042C53`, primary `#185FA5`, agent violet `#5B52B8`/`#7F77DD`, surface `#F4F7FB`, borders `#E1E7F0`/`#EDF1F7`, muted `#5A6B80`/`#8A97A8`; Newsreader (display) + Public Sans (UI, tabular numerals); radii 22/16/14px; 50px button height | Codify as versioned tokens in code (`frontend/src/styles/tokens.css` + TS export). The sidebar itself is a demo annotation - the *values* are the deliverable |
| **Screen inventory** | `screen: 'today' \| 'trip' \| 'explore' \| 'agent'` | The four primary routes + profile |
| **Sheet/overlay inventory** | `sheet: 'item' \| 'place' \| 'reserve' \| 'alt' \| 'filters' \| 'voice' \| 'profile' \| 'trips'` + review-plan, provenance ("How I got here"), manual-trip, onboarding/auth, notification banner, toast | Reusable bottom-sheet system with these instances |
| **Component patterns** | Recommendation cards, status badges (Suggested / Needs you / In plan / Confirmed / Working / Changed), timeline rows, provenance chips, map callouts, empty/idle cards, purposeful-progress states | The component library (§6) |
| **Copy voice** | "Fits between your workshop and dinner", "Nothing is booked. I go active when you land on Aug 18.", "I read them, I do not store them" | Copy guidelines: human, specific, provenance-first. Keep the real strings where they are state-independent; regenerate the state-dependent ones from data |
| **Flow choreography** | The numbered flow scenarios (onboarding, trip detection, plan review, reserve, voice change, schedule conflict…) | Acceptance-test scripts. Each demo flow becomes a Playwright end-to-end scenario against the real API |

### 1.2 What to NEVER port (demo-only scaffolding)

- **The "User flows" launcher panel and numbered scenario buttons** - design-review navigation,
  not product UI.
- **The "Style & aesthetic" sidebar** (palette swatches, type specimens, principles, avoided list)
  - annotation for reviewers.
- **`resetDemo` / "Reset to day 2, nothing booked"** and the canvas prop editors
  (`agentState`, `tripDay`, `showFlowPanel`).
- **The phone bezel, fake status bar, and hardcoded `5:12` clock.**
- **loremflickr placeholder images** - production photos come from the Places provider via the
  `places.photo_url` cache, with owned fallbacks.
- **The single client-side state object and its instant transitions.** In the demo,
  `acceptPlan` flips every item to confirmed in one tick and `Reserve 7:30` succeeds by
  definition. In production those are server-driven state machines that take real time and can
  fail. No UI may simulate a transition the server has not persisted.
- **The `sc-if`/`sc-for`/`{{ binding }}` template runtime** - Claude Design's renderer, not ours.

### 1.3 The rule that makes "no mock data" enforceable

> **Every dynamic value on screen must trace to a typed API response, and every API response
> must trace to a table or derivation in `schema.sql`.** If a binding in the canvas (e.g.
> `planPreview`, `evidence`, `stateWord`, `calloutName`) has no home in the contract, that is a
> contract gap to fix *before* building the screen - not a value to hardcode.

Concretely: PR review rejects any literal that belongs to the domain (venue names, times,
distances, statuses, counts). The demo's Chicago/YMCA/Beatrix material may appear only in test
fixtures and seed scripts, clearly labeled as such.

---

## 2. The starting point: the `travelwell-agent` repo

`travelwell-agent` is the codebase we implement in (branch: `frontend-redesign`). It is a clean
re-initialization of the `travelwell-ai` prototype - identical code, fresh history, README
already re-scoped to the proactive-agent vision - so everything below describes what actually
sits on the branch today. Its current product is a **one-shot gym-search concierge** (single
page: constraints in → SSE progress → ranked facility cards + map). The new product is a
four-screen trip agent - a different UI, but a lot of the repo is worth keeping. The rule:
**evolve the repo's structure; replace only what is structurally wrong, and say so.**

### 2.1 Keep and build on

| Asset | Why it stays |
|---|---|
| **Monorepo layout** `backend/ · frontend/ · docs/ · skills/ · .github/` | New frontend work lands in `frontend/`, backend work in `backend/` - no new repo, no split |
| **Deploy path**: frontend Dockerfile + nginx + `entrypoint.sh` writing runtime `config.json`; Cloud Run via `.github/workflows/deploy.yml` | Runtime config injection beats build-time env baking (one image, any environment). Extend `config.json` with new keys (push public key, API base) rather than inventing a new mechanism. Same for backend's `GET /api/config` serving the Maps key at runtime (with proper key referrer restrictions) |
| **Vite + TypeScript + ESLint toolchain** in `frontend/` | Matches the plan's stack; Phase 0 tightens it (strict TS, Prettier, import boundaries) and adds `vite-plugin-pwa`, TanStack Router/Query, Vitest, Playwright. React 18 → 19 as part of the same restructure |
| **The SSE progress channel** (`POST /api/recommend` → `GET /api/events/{session_id}` with `trace` / `error` / `result` events) | The repo already proved the exact transport the design's purposeful-progress states need ("Checking reservation availability…"). The new contract adopts it as `GET /runs/{run_id}/events` for agent-run and action progress - **SSE first, polling as fallback** (this supersedes the poll-only approach in earlier drafts of this plan) |
| **Maps experience** in `App.tsx` + `services/google_maps.py` | Marker ⇄ card selection sync, info windows, landmark/geocode fallback (`/resolve_location`) - port as `features/explore/` + `lib/maps/` modules; this is exactly the Explore screen's core |
| **Explainable-validation UX** (amenity three-state verification, YMCA reciprocity, budget checks with human-readable reasons) | This is the ancestor of the design's provenance chips and "Also considered" reasons - the *concept* carries straight into `plan_item_options.matched_preferences` / `rejection_reason` rendering |
| **`docs/` convention** (`API_CONTRACTS.md`, `ARCHITECTURE.md`, `PROJECT_CHARTER.md`) | `API_CONTRACTS.md` grows into (or links) the OpenAPI 3.1 spec - same home, higher rigor. ADRs land in `docs/adr/` |
| **Backend agent pipeline + `skills/`** (Research → Ranking → Policy agents, pytest/ruff setup) | Outside frontend scope, but the new UI consumes it through the event spine: today's pipeline becomes the inside of an `agent_run` |

### 2.2 Replace or discard - flagged, with reasons

1. **The frontend monolith.** One 1,686-line `App.tsx`, one 548-line `App.css`, one `client.ts`.
   The old UI is a different product and cannot be refactored into the four-screen PWA; its
   *internals* are replaced by the feature-first layout (§4) **inside the same `frontend/`
   workspace**, keeping package.json lineage, Docker, nginx, and CI. What survives is extracted
   into modules (map sync, geocode UX, validation-display patterns) - not kept as scaffolding.
   The legacy UI stays reachable on a git tag (`legacy-concierge`) for reference, then main moves on.
2. **Mock data inside app code.** `BASE_RECS` templates hardcoded in `client.ts`,
   `use_mock_data: true` as the *API default*, `USE_MOCK_DATA` env, and the advertised "silent
   mock fallback" when Places/Vertex throttle. This is the lying-UI anti-pattern §§1.3/7 forbid:
   a throttled API must surface an honest degraded state, never fake data dressed as live
   results. Mocks move to contract-generated, test-scoped fixtures (§5.2); the fallback flag
   dies as a production behavior. *(Backend change required - flagged to backend scope.)*
3. **Markdown-parsing as a data pipeline.** `parse_markdown_to_recommendations()` regex-splits
   the agent's prose into cards. The architecture guide's rule ("never parse free-form model
   text to determine what happened") applies server-side too: agents must return structured
   output (`agent_runs.result` JSONB), validated against the contract. *(Backend scope; the
   frontend contract assumes structured results and will not accept prose.)*
4. **Presentation baked into the API contract.** `emoji_badges`, pre-formatted `description`
   strings, prose `reviews_summary` as load-bearing fields. The new contract serves typed data;
   rendering belongs to the frontend and the design system.
5. **Prompt-string as the primary API.** `UserRequest.prompt` free text is chat-shaped. It
   survives as *one* event kind (`user_text` / `user_voice`) in the event-spine contract; every
   intent the UI can express directly gets a structured endpoint (§5.1).
6. **Statelessness.** The backend persists nothing - no Trip, no plan, no user. The Postgres
   system of record (`schema.sql`) is new backend scope the frontend depends on via the
   contract; ephemeral SSE `session_id`s are replaced by real auth + trip-scoped resources.
7. **No frontend tests.** `frontend/` has no test runner; the testing pyramid in §8 is added in
   Phase 0 as CI gates, not retrofitted later.
8. ~~**`frontend/dist/` build artifacts in the working tree**~~ - already resolved:
   `travelwell-agent` starts without committed build output; keep it that way (build artifacts
   come from CI only).

---

## 3. Product definition: why a PWA, and what "real PWA" means here

TravelWell is a **proactive agent**. The user is walking through an airport when the plan-ready
notification lands; they open the app in a hotel lobby on flaky Wi-Fi. That makes the PWA pillars
product requirements, not checklist items:

1. **Installable**: valid web app manifest (name, icons incl. maskable, `standalone` display,
   theme `#042C53`), install prompt surfaced after first meaningful use - never on first paint.
2. **Push notifications are the product's front door.** The `notifications` table already models
   this: `kind`, `title`, `body`, `cta jsonb {label, deep_link}`, and `sent/opened` tracking.
   - Web Push via FCM; service-worker `push` handler renders exactly the server-authored
     title/body/CTA. iOS requires the app to be installed to Home Screen (16.4+) - onboarding
     must teach this on iOS.
   - **Every notification deep-links** to the surface it references (`/trip/:id/plan`,
     `/trip/:id/conflict/:eventId`…). Opening reports `opened_at` back to the API.
3. **Offline-tolerant, not offline-first.** Per `DATA_ARCHITECTURE.md`, state is server-driven
   and changes a handful of times a day; we do not build a sync engine. The standard:
   - App shell precached (Workbox via `vite-plugin-pwa`); an update banner on new SW, never a
     silent hard reload mid-task.
   - Last-fetched trip + today plan cached (stale-while-revalidate) so the plan is *readable*
     in airplane mode, with an explicit "Offline - showing your plan as of 5:12 PM" banner.
   - **Mutations are never queued offline.** Approving a reservation while offline fails fast
     with an honest error. (An offline action queue would fake the Propose→Confirm→Execute→Verify
     loop - exactly what the architecture forbids.)
4. **Performance budget on real hardware** (mid-tier Android, 4G): LCP ≤ 2.5 s, INP ≤ 200 ms,
   route JS ≤ 170 KB gz for Today; the map SDK loads only on Explore/route views. Enforced by
   Lighthouse CI + bundle-size gates (§9).

---

## 4. Stack and architecture

Chosen to extend what `travelwell-agent/frontend` already uses. Substitutions need an ADR
(architecture decision record) in `docs/adr/`, not a Slack message.

| Concern | Choice | Rationale |
|---|---|---|
| Framework | **React + TypeScript (strict) + Vite** - already the repo's toolchain; bump React 18 → 19 in Phase 0 | SPA/PWA; no SEO need behind auth; keeps existing Docker/nginx/deploy unchanged |
| Routing | TanStack Router (new), file-based routes in `src/routes/` | Typed routes/params - deep links from notifications are load-bearing; the old app had no router at all |
| Server state | **TanStack Query** (new) | Cache, refetch-on-focus, optimistic updates with rollback |
| Live progress | **SSE** (`GET /runs/{id}/events`) - the repo's proven pattern, re-homed | Purposeful progress states stream; polling is the fallback, not the default |
| Client state | Minimal - component state + one small Zustand store for UI (active sheet, voice recorder) | Server owns domain state; a big client store is how both the demo *and* the old `App.tsx` went wrong |
| API contract | **OpenAPI 3.1 spec evolving `docs/API_CONTRACTS.md`**; `openapi-typescript` + `openapi-fetch` generated client | §5 |
| Boundary validation | Zod on push payloads and any non-generated input | Trust but verify at the edges |
| Styling | CSS custom properties (tokens) + Tailwind v4 consuming them | Tokens stay the single source; replaces the monolithic `App.css` |
| Maps | Google Maps JS (vector, AdvancedMarker) - porting the existing marker/card sync + geocode fallback | Backend already uses Places/Routes; one provider, one visual language |
| Dates/times | `Intl` + `date-fns-tz`; **all trip times rendered in `trips.timezone`, never device TZ** | The schema stores `timestamptz` + IANA zone per trip; a 5:30 PM Chicago workout must read 5:30 PM from a phone still on SFO time |
| Auth | OAuth (Google/Apple) + email code via backend; **httpOnly session cookie (BFF pattern)** - no tokens in JS-readable storage | Arch guide §33; replaces the old ephemeral session ids |
| PWA plumbing | `vite-plugin-pwa` (Workbox), FCM Web Push | §3 |
| Runtime config | Keep `entrypoint.sh` → `config.json` + `GET /api/config` | Existing, correct pattern; extend with new keys |

**`frontend/src` layout after the Phase 0 restructure** (feature-first, same workspace):

```
frontend/
  src/
    app/            # providers, shell, router setup, service-worker registration
    routes/         # thin: one file per destination - URL contract (params +
                    #   ?sheet= search params), auth guards, data loaders,
                    #   code-split points; each just composes a feature screen
    styles/         # tokens.css (design tokens + globals, Tailwind @theme), tokens.ts
    components/
      ui/           # primitives: Button, Sheet, StatusBadge, Card, ProgressState…
    api/            # generated client + typed hooks (useTrip, usePlan, useActions…)
                    #   ← replaces the old hand-written client.ts + BASE_RECS
    features/
      onboarding/   today/   trip/   explore/   agent/   actions/   notifications/
    lib/            # time (trip-tz helpers), maps (ported sync/geocode), formatting
    test/           # test setup + contract-generated mock handlers (never bundled)
  e2e/              # Playwright flows mirroring the canvas scenarios
  Dockerfile · nginx.conf · entrypoint.sh   # unchanged deploy path
```

**A note on the `design/` directory**: the Claude Design canvas (and any future design assets)
is **reference material only** - it lives beside the docs, and nothing under `src/` imports
from it or is named after it. Design decisions enter the codebase exclusively as code in
conventional homes: tokens in `src/styles/`, primitives in `src/components/ui/` (the shadcn
convention), app config where the toolchain expects it. There is no `design/` or `ui/` folder
at the source root.

---

## 5. API contract layer - the replacement for mock data

**Contract-first.** The OpenAPI spec (grown from `docs/API_CONTRACTS.md`) is authored with the
backend team before each feature phase and is the *only* interface the frontend knows.

- **Types generated, enums imported, never re-declared.** `item_status`, `trip_state`,
  `action_status`, `reservation_status` etc. exist once, generated from the contract that mirrors
  the Postgres enums. The badge component switches over the generated union; adding an enum value
  fails the typecheck everywhere it matters.
- **Errors**: RFC 9457 `application/problem+json` with a stable machine `code`; the client maps
  codes to the design's honest failure states (e.g. `reservation_declined` → the "Beatrix
  declined the 7:30 hold" card with alternatives + `external_url` fallback). A throttled
  upstream (the old repo's silent-mock trigger) becomes a visible degraded state.
- **Idempotency**: every action-creating POST sends an `Idempotency-Key` (client UUID)  - 
  mirrors `pending_actions.idempotency_key`; retry on network failure is safe by construction.
- **Concurrency**: mutating requests carry the entity's `updated_at`/version; a 409 means the
  agent changed the plan under the user - the UI refetches and shows "Your plan changed", never
  silently overwrites.
- **Freshness**: SSE stream while a run/action is live (§4); refetch on focus/visibility
  otherwise. Firestore-style live listeners stay out of scope by architecture decision
  (`DATA_ARCHITECTURE.md`).

### 5.1 Screen → endpoint → schema map (the binding-to-contract map)

Derived from the query-shape table in `DATA_ARCHITECTURE.md`; this is the checklist that every
canvas binding must resolve against.

| Surface (canvas source) | Endpoint (v1) | Backing schema |
|---|---|---|
| Today (`dayLabel`, `stateWord`, window card, next-up cards) | `GET /trips/{id}/today` | `trips` ⋈ `calendar_events` ⋈ `plan_items` ⋈ selected `plan_item_options` ⋈ `reservations` |
| Trip timeline (Existing/Suggested/Confirmed rows) | `GET /trips/{id}/timeline` | `calendar_events` ∪ `plan_items` ordered by time, badged by `item_status` |
| Trips sheet (`allTrips`, "needs you" counts) | `GET /trips` | `trips` by state + derived counts from open `plan_items`/`pending_actions` |
| Trip detection card (`evidence`, "Based on") | `GET /trips?state=detected`, `POST /trips/{id}/confirm` | `trips.detection_confidence`, `trip_evidence` |
| Plan review (`planPreview`, headline, provenance) | `GET /trips/{id}/plan`, `POST /plan-items/{id}/accept` | `plans` (versioned) + `plan_items` + options |
| "How I got here" / Also considered | `GET /plan-items/{id}/provenance` | `wellness_windows.bounds` + `plan_item_options` (matched prefs, `rejection_reason`) |
| Swap option (`alts` sheet) | `POST /plan-items/{id}/select-option` | flip `option_state` - no data loss |
| Reserve flow (`reserveStep`, confirm rows, code) | `POST /actions` → `POST /actions/{id}/approve` → SSE `GET /actions/{id}/events` | `pending_actions` lifecycle + `reservations` (incl. `failed` + `external_url`) |
| Voice/text/UI intents (`voiceState`, agent cards) | `POST /events` (kind `user_voice`/`user_text`/`ui_action`) → SSE run stream | `agent_events` → `agent_runs` → structured `result` |
| Explore (`cats`, filters, `calloutName`…) | `GET /explore?category=&filters=` | Places API via backend (evolves today's Research agent + `google_maps.py`); surfaced candidates cached in `places` |
| Landmark resolution (manual trip, Explore search) | `GET /resolve_location` - **kept from the old repo** | Geocoding via backend |
| Profile & autonomy toggles | `GET/PATCH /me/preferences`, `GET /me/sources` | `user_preferences` (incl. `allow_*`), `connected_sources` |
| Notifications inbox / open tracking | `GET /notifications`, `POST /notifications/{id}/opened` | `notifications` |

### 5.2 Development without a finished backend - the honest version

"No mock data" does not mean the frontend blocks on every endpoint. It means **mocks are
contract-generated, test-scoped, and disposable** - the opposite of the old repo's approach,
where mock templates lived in `client.ts` and shipped to production:

- A dev mock server (MSW / Prism) is generated *from the OpenAPI spec* - it cannot drift from
  the contract - and seed fixtures run through the real Postgres seed script so they obey the
  schema's constraints (a `confirmed` reservation in a fixture *must* have a confirmation code,
  because the CHECK constraint says so).
- Mock handlers live under `frontend/e2e/` and `frontend/src/test/` only; the production bundle
  contains zero mock code (enforced by an import-boundary lint rule).
- Each endpoint's mock is deleted in the PR that integrates the real endpoint. A tracking table
  in `docs/` lists remaining mocked endpoints; **Definition of Done for every feature phase is
  "runs against the deployed dev backend", not "runs against MSW".**

---

## 6. Design system implementation

Build the small coherent system the brief asks for - extracted from the canvas, then owned:

1. **Tokens** (`src/styles/tokens.css` + typed TS mirror): color roles (ink, primary, agent,
   surface, borders, muted, state colors for confirmed/working/changed/failed), the two type
   families with the canvas's scale (28/26px Newsreader display, 15/14.5/13.5/12.5px Public Sans,
   tabular numerals globally), radius scale, spacing, elevation, motion durations honoring
   `prefers-reduced-motion`. Replaces the old monolithic `App.css`.
2. **Primitives** (in `src/components/ui/`): Button (50px primary/secondary from the canvas), Card, **StatusBadge**
   (driven only by the generated status enums), Sheet (focus-trapped, swipe-dismiss,
   URL-addressable so deep links can open them), Toast, Timeline row, Provenance chip,
   **ProgressState** (purposeful copy - "Checking reservation availability…" - fed by the SSE
   `trace` events, with honest terminal states; a shared component so *faking completion is
   structurally hard*).
3. **Recommendation cards** (wellness + dining): one component family answering the brief's five
   questions (what / why / how far / fits schedule / next action) with progressive disclosure;
   props typed directly against the `plan_item` + `option` API shapes. The old app's
   explainable-validation reasons inform the "why" line - served now from
   `matched_preferences`/`rejection_reason`, not parsed prose.
4. Documented in **Storybook**, with visual regression (Chromatic or Playwright screenshots) and
   axe checks per story. Storybook stories may use fixture data - that is the one sanctioned home
   for demo-flavored content.

---

## 7. State, lifecycle, and the "no lying UI" rules

These encode the architecture guide's reliability principles in frontend law:

1. **The server is the only author of domain status.** The client never invents or pre-commits
   a status. Optimistic UI is allowed only for side-effect-free operations (selecting an
   alternative option, dismissing a suggestion) and must roll back on failure.
2. **Never render `confirmed` until the API returns it** (the schema physically cannot store a
   confirmed reservation without a verified code - the UI holds the same line). While a
   `pending_action` is `executing`, show Working; on `failed`, show the failure with the
   recovery path (alternatives, `external_url`), never a retry-spinner loop.
3. **Derived lifecycle states are computed in one place.** `NEEDS_ATTENTION` etc. come from the
   API's derived fields (open items/actions), rendered by one shared selector - not recomputed
   ad hoc per screen (two sources of truth is how the demo and the product would diverge).
4. **Provenance is served, not generated.** "Why this fits" and "How I got here" render
   `wellness_windows.bounds`, `matched_preferences`, and `rejection_reason` from the API.
   The frontend never paraphrases and no screen calls a model directly.
5. **Voice, text, and taps are the same pipeline**: capture → `POST /events` → render the
   run's structured result as cards/timeline/map. No client-side NLU, no separate voice logic.
6. **Trust indicators are real**: the state line ("Active · watching your schedule"), the
   activation date, and connected-source checkmarks all come from `trips`/`connected_sources`  - 
   the canvas shows these as static text; production must not.
7. **Degraded is visible, never simulated.** When an upstream (Places, Vertex) throttles or
   fails, the UI says so and offers retry or the external path. The old repo's silent mock
   fallback is the named counter-example.

---

## 8. Cross-cutting engineering standards

- **TypeScript strict**, no `any` at API boundaries, exhaustive switches over generated enums.
- **Lint/format**: ESLint (typescript-eslint strict + jsx-a11y + import boundaries) + Prettier,
  extending the repo's existing `eslint.config.js`. Import-boundary rules: features cannot
  import each other's internals; nothing outside `src/test` imports mocks; `components/ui`
  imports nothing from `features/`; `routes/` imports from `features/`, never the reverse  - 
  features stay router-agnostic and testable without one. Components consume colors only via token custom
  properties - a lint rule bans hex/color literals outside `styles/tokens.css`, which is what
  actually keeps the design system from drifting across its two folders.
- **Testing pyramid** (new - the old frontend had none):
  - Unit (Vitest): time/tz helpers, selectors, reducers - the tz rendering rule gets a dedicated
    suite (device TZ ≠ trip TZ cases).
  - Component (Testing Library + MSW): every status permutation of the cards and flows,
    including `failed` and 409-conflict paths.
  - **E2E (Playwright, mobile viewports)**: the canvas's flow scenarios become the suite  - 
    onboarding, trip detect → confirm, plan review → accept, reserve → confirmed, reserve →
    declined → external fallback, voice "skip the gym", schedule-conflict replan. Run against
    the dev backend nightly and against the contract mock per-PR.
- **Accessibility: WCAG 2.2 AA.** ≥44px touch targets (canvas buttons already comply), visible
  focus, sheet focus trapping + `aria-modal`, timeline as a semantic list, status announced via
  live regions (a "Working → Confirmed" transition must be perceivable without sight), reduced
  motion honored, color contrast verified for the muted grays on `#F4F7FB` (several canvas
  values are borderline - audit and adjust tokens, not per-screen).
- **Security & privacy**: httpOnly cookies; strict CSP (self + maps/fonts + API origin);
  no PII in analytics or logs; the "I read them, I do not store them" promise means calendar
  detail renders only what the minimal `calendar_events` cache serves and the client persists
  none of it beyond the HTTP cache rules of §3. Maps API key stays runtime-served
  (`/api/config`) with referrer restrictions.
- **Observability**: Sentry (or GCP Error Reporting) with release tagging; web-vitals reported;
  every API call carries a request-id header so a user report can be traced to
  `event → run → action` server-side (arch guide §32). A lightweight analytics event schema
  (screen views, action approvals, notification opens) reviewed like an API contract - the
  existing `/feedback` endpoint folds into this.
- **CI gates (blocking)**, added to the existing GitHub Actions pipeline: typecheck · lint ·
  unit+component tests · Playwright smoke · bundle-size budget · Lighthouse CI (perf + PWA ≥ 90)
  · axe on key routes · OpenAPI client freshness (generated code matches spec).
- **Delivery**: trunk-based, preview deploy per PR, `dev → staging → prod` on the existing
  Cloud Run path with instant rollback; feature flags for surfaces shipping ahead of their backend.

---

## 9. Phased delivery plan

Aligned with the architecture guide's milestones (M4 mobile shell, M5 voice, M8 actions…).
Each phase ends **integrated against the real dev backend**, demo fixtures deleted for the
endpoints it consumed.

| Phase | Scope | Exit criteria |
|---|---|---|
| **0 - Foundations & repo restructure** (wk 1-2) | On `travelwell-agent` branch `frontend-redesign`: tag the init commit `legacy-concierge` for reference; restructure `frontend/src/` to the feature-first layout; remove `BASE_RECS`/in-app mocks; strict TS + new CI gates on the existing Actions pipeline; tokens + primitives in Storybook; app shell + typed routes; auth (OAuth + email code, session cookie); OpenAPI v1 agreed (evolving `docs/API_CONTRACTS.md`) & client generated | Installable shell passes Lighthouse PWA; sign-in works end-to-end; deploy pipeline still green on the restructured workspace; token file reviewed against canvas |
| **1 - Trip core, read path** (wk 3-4) | Today + Trip screens read-only: empty / upcoming / preparing / active / completed lifecycle rendering, trips sheet, trip detection + confirm, manual trip create (reusing `/resolve_location`) | All lifecycle states render from API data; detection→confirm flow E2E green on dev backend |
| **2 - Plan interaction** (wk 5-6) | Plan review, accept item / accept all, swap alternatives, "How I got here" provenance, skip/remove | Accept + swap persist and survive reload; provenance rendered fully from data; 409 conflict path handled |
| **3 - Actions & reservations** (wk 7-8) | Propose→Confirm→Execute→Verify UI over `pending_actions`: reservation flow (times, confirm sheet with what/when/where/cost, SSE-streamed working state, confirmed, **declined + external fallback**), calendar-add flow, autonomy toggles respected | No path can display success without server verification - proven by an E2E that stubs a provider failure |
| **4 - Explore & map** (wk 9-10) | Map-first Explore built on the ported marker/card sync + geocode modules; category chips + filters from `user_preferences`; plan route overlay (Hotel → YMCA → dinner); place sheet | Map lazy-loads within budget; filters round-trip through API; route reflects today's non-skipped items |
| **5 - Agent & voice** (wk 11-12) | Agent screen (structured results, suggested prompts), voice capture → `POST /events` → SSE run stream → updated-plan diff view, persistent mic affordance | The brief's "exhausted, skip the gym" scenario passes E2E with a real agent run returning structured output (no markdown parsing anywhere) |
| **6 - Proactive & PWA hardening** (wk 13-14) | Web Push end-to-end (permission UX, deep links, opened tracking), schedule-conflict intervention surface, offline read cache + banners, install education (iOS), perf pass | Conflict notification → tap → alternatives → approve works on a physical Android + installed iOS PWA; offline shows honest stale plan; budgets green |

Ongoing after 6: notification inbox history, desktop responsive extension, localization readiness.

**Backend dependencies flagged by this plan** (owned by backend scope, tracked in `docs/`):
Postgres system of record per `schema.sql`; structured agent outputs replacing
`parse_markdown_to_recommendations`; retirement of `use_mock_data`/`USE_MOCK_DATA` as production
behavior; event-spine endpoints (`/events`, `/runs/{id}/events`); auth/session issuance;
contract fields free of presentation (`emoji_badges` etc.).

---

## 10. Definition of Done (every feature, every phase)

- [ ] Data from the versioned API only; zero domain literals in `src/` (fixtures excluded)
- [ ] All states designed and implemented: loading (purposeful copy) / empty / error / success / offline / degraded
- [ ] Status rendering driven by generated enums; failure paths tested, not just happy paths
- [ ] Times rendered in trip timezone; verified by unit test
- [ ] Deep-linkable (URL restores screen + sheet state, defined in `routes/` via typed search params)
- [ ] Meets a11y checks (axe + manual keyboard/focus pass) and perf budget
- [ ] E2E scenario updated/added; runs against dev backend
- [ ] Corresponding mock handlers deleted; contract tracking table updated
- [ ] The brief's final test holds: *understandable in 5 seconds; next action in ≤2 steps; the
      user can tell what TravelWell knows, wants to do, and has actually done*
