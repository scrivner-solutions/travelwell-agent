# TravelWell Frontend

Production PWA for TravelWell.
React 19 + TypeScript (strict) + Vite, TanStack Router (file-based, typed) and
TanStack Query, Tailwind v4 over design tokens, `vite-plugin-pwa`.

## Layout

```
src/
  app/            providers, shell, service-worker registration
  routes/         thin URL layer: params + ?sheet= search params, guards,
                  loaders, code-split points; each composes a feature screen
  styles/         tokens.css (design tokens + globals), tokens.ts mirror
  components/ui/  primitives: Button, Card, Sheet, StatusBadge, ProgressState
  api/            generated OpenAPI client (schema.d.ts) + typed query options
  features/       vertical slices: onboarding/ today/ trip/ explore/ agent/ ...
  lib/            runtime config, trip-timezone helpers
  test/           test setup (test-scoped; never bundled)
```

Import boundaries are enforced by ESLint (`import/no-restricted-paths`):
features never import each other; `components/ui` never imports application
layers; hex colors exist only in `src/styles/`.

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Dev server; proxies `/api` to `http://localhost:8000` |
| `npm run build` | Typecheck + production build |
| `npm run lint` | ESLint incl. boundary rules |
| `npm test` | Vitest unit tests |
| `npm run typecheck` | `tsc -b` only |
| `npm run generate:api` | Regenerate `src/api/schema.d.ts` from `docs/openapi.yaml` |

## Configuration

Configuration is runtime, not build time: the container's `entrypoint.sh`
writes `/config.json` at start, and the app reads it before mounting. In dev,
Vite serves `public/config.json` (empty base URL = same origin, which the dev
proxy forwards to the local backend). There is no `.env` for the frontend.

## Contract-first API

`docs/openapi.yaml` is the only interface the frontend knows. After editing
the spec, run `npm run generate:api` and commit the regenerated
`src/api/schema.d.ts`. Status enums (`item_status`, `trip_state`, ...) come
from the generated types and are never re-declared by hand.

## Design source

`TravelWellPlan.dc.html` is the UX, flow and palette source of truth: a Claude
Design canvas that renders standalone in a browser. Comments across `src/` cite
it **by name only**, and this is the one place that says where it is —
currently `travel_schema/design/`, imported from the Claude Design project.

Both filesystem copies are snapshots of that project, so neither is canonical
and both go stale. The copy that used to live in this repo was deleted for
exactly that reason; do not restore it. Re-import instead, and if the file
moves, change this paragraph rather than hunting the comments.
