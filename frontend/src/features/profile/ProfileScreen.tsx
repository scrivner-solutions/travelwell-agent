import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter, useSearch } from '@tanstack/react-router'
import { useMemo, useState } from 'react'
import {
  disconnectSource,
  logout,
  meQueryOptions,
  preferencesQueryOptions,
  sourcesQueryOptions,
  syncSource,
  tripsQueryOptions,
  updatePreferences,
  type Preferences,
  type PreferencesUpdate,
} from '@/api/queries'
import { Button } from '@/components/ui/Button'
import { LoadingState, DegradedState } from '@/components/ui/ScreenState'
import { apiUrl } from '@/lib/config'
import { formatAgo } from '@/lib/time'
import {
  CONNECT_ERROR_COPY,
  SOURCE_ACTION_LABEL,
  SOURCE_META,
  SOURCE_STATE,
  canGoBackInApp,
  sourceAction,
  sourceName,
  syncFailureMessage,
  syncOutcomeMessage,
} from '@/lib/sources'
import { travelStats } from '@/lib/trips'

/**
 * Profile screen (design prototype's profile sheet): standing preferences as
 * toggleable chips, day-pass budget, autonomy toggles, connected sources.
 * Chips are UI groupings over typed columns - "$$ or less" IS
 * price_level_max=2, "45–90 min" IS the session bounds - so the provenance
 * chips on plan options ("Matched from your profile") stay honest.
 */

type ArrayField = Extract<
  keyof Preferences,
  'dietary' | 'activities' | 'amenities' | 'memberships' | 'preferred_times'
>

interface Chip {
  label: string
  isOn: (p: Preferences) => boolean
  patch: (p: Preferences, on: boolean) => PreferencesUpdate
}

function slugChip(label: string, field: ArrayField, slug: string): Chip {
  return {
    label,
    isOn: (p) => p[field].includes(slug),
    patch: (p, on) => ({
      [field]: on ? [...p[field], slug] : p[field].filter((s) => s !== slug),
    }),
  }
}

// "What TravelWell plans around": the prototype's mixed chip row, decomposed
// onto the typed preference columns behind it.
const PREF_CHIPS: Chip[] = [
  slugChip('Vegetarian', 'dietary', 'vegetarian'),
  slugChip('Swim', 'activities', 'swim'),
  slugChip('Running', 'activities', 'running'),
  slugChip('Strength', 'activities', 'strength'),
  {
    label: '$$ or less',
    isOn: (p) => p.price_level_max != null && p.price_level_max <= 2,
    patch: (_p, on) => ({ price_level_max: on ? 2 : null }),
  },
  {
    label: '45–90 min',
    isOn: (p) => p.session_min_minutes === 45 && p.session_max_minutes === 90,
    patch: (_p, on) => ({
      session_min_minutes: on ? 45 : null,
      session_max_minutes: on ? 90 : null,
    }),
  },
  slugChip('Mornings', 'preferred_times', 'mornings'),
]

const MEMBERSHIP_CHIPS: Chip[] = [
  slugChip('YMCA reciprocity', 'memberships', 'ymca_reciprocity'),
  slugChip('Hotel gym access', 'memberships', 'hotel_gym'),
  slugChip('ClassPass', 'memberships', 'classpass'),
  slugChip('Equinox', 'memberships', 'equinox'),
]

const AMENITY_CHIPS: Chip[] = [
  slugChip('Pool', 'amenities', 'pool'),
  slugChip('Treadmill', 'amenities', 'treadmill'),
  slugChip('Weights', 'amenities', 'weights'),
  slugChip('Sauna', 'amenities', 'sauna'),
  slugChip('Showers', 'amenities', 'showers'),
]

const BUDGETS = [
  { label: 'Free only', cents: 0 },
  { label: '$20', cents: 2000 },
  { label: '$40', cents: 4000 },
  { label: '$75', cents: 7500 },
]

interface Perm {
  field: Extract<
    keyof Preferences,
    'allow_calendar_write' | 'allow_auto_book' | 'watch_schedule'
  >
  label: string
  sub: (on: boolean) => string
}

const PERMS: Perm[] = [
  {
    field: 'allow_calendar_write',
    label: 'Add approved plans to my calendar',
    sub: () => 'Only what you have approved',
  },
  {
    field: 'allow_auto_book',
    label: 'Book tables under $40 without asking',
    // Person-free voice rule; the on state must not claim it is off.
    sub: (on) =>
      on
        ? 'Reservations in budget are booked for you'
        : 'Currently off. Every reservation is confirmed with you',
  },
  {
    field: 'watch_schedule',
    label: 'Watch my schedule and warn me',
    sub: () => 'Nudges when a plan stops fitting',
  },
]

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join('')
}

// Optimistic cache merge: null in a patch clears the (optional) field.
function applyPatch(prev: Preferences, patch: PreferencesUpdate): Preferences {
  const next: Record<string, unknown> = { ...prev }
  for (const [key, value] of Object.entries(patch)) {
    next[key] = value === null ? undefined : value
  }
  return next as unknown as Preferences
}

function SectionLabel({ children }: { children: string }) {
  return (
    <p className="mb-2.5 mt-6 text-label font-medium uppercase tracking-wide text-muted-soft">
      {children}
    </p>
  )
}

function ChipRow({
  chips,
  prefs,
  onPatch,
}: {
  chips: Chip[]
  prefs: Preferences
  onPatch: (patch: PreferencesUpdate) => void
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {chips.map((chip) => {
        const on = chip.isOn(prefs)
        return (
          <button
            key={chip.label}
            aria-pressed={on}
            onClick={() => onPatch(chip.patch(prefs, !on))}
            className={`h-[38px] rounded-[11px] border px-3.5 text-caption font-medium ${
              on
                ? 'border-primary bg-state-confirmed-soft text-primary-deep'
                : 'border-border bg-card text-muted'
            }`}
          >
            {chip.label}
          </button>
        )
      })}
    </div>
  )
}

function Toggle({ on, label, onChange }: { on: boolean; label: string; onChange: () => void }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onChange}
      className={`flex h-[30px] w-[50px] flex-none rounded-full p-[3px] transition-colors ${
        on ? 'justify-end bg-primary' : 'justify-start bg-track-off'
      }`}
    >
      <span className="block size-6 rounded-full bg-card shadow-[0_1px_3px_rgba(4,44,83,0.35)]" />
    </button>
  )
}

export function ProfileScreen() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const me = useQuery(meQueryOptions())
  const trips = useQuery(tripsQueryOptions())
  const prefs = useQuery(preferencesQueryOptions())
  const sources = useQuery(sourcesQueryOptions())

  const mutation = useMutation({
    mutationFn: updatePreferences,
    onMutate: async (patch) => {
      await queryClient.cancelQueries({ queryKey: ['me', 'preferences'] })
      const previous = queryClient.getQueryData<Preferences>(['me', 'preferences'])
      if (previous) {
        queryClient.setQueryData(['me', 'preferences'], applyPatch(previous, patch))
      }
      return { previous }
    },
    onError: (_error, _patch, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['me', 'preferences'], context.previous)
      }
    },
    onSettled: () =>
      void queryClient.invalidateQueries({ queryKey: ['me', 'preferences'] }),
  })
  const patch = (update: PreferencesUpdate) => mutation.mutate(update)

  const { connected, connect_error: connectError } = useSearch({ from: '/profile' })
  const [confirming, setConfirming] = useState<string | null>(null)

  const disconnect = useMutation({
    mutationFn: disconnectSource,
    onSuccess: () => {
      setConfirming(null)
      void queryClient.invalidateQueries({ queryKey: ['me', 'sources'] })
    },
  })

  // One mutation serves every row, so an outcome is keyed to `variables` - the
  // kind of the last run - and never paints onto a row that did not ask.
  const sync = useMutation({
    mutationFn: syncSource,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['me', 'sources'] })
      // A sync that created events changes what the trips read, not just the
      // freshness line above the button.
      void queryClient.invalidateQueries({ queryKey: ['trips'] })
    },
  })

  // The connect route answers with a 302 to Google, which fetch can neither
  // follow (cross-origin) nor read (opaque), so this is a navigation.
  const startConnect = async (kind: string) => {
    window.location.assign(await apiUrl(`/me/sources/${kind}/connect`))
  }

  // Every connectable kind gets a row even with no grant behind it, or there
  // is nowhere to put its Connect button.
  const sourceRows = useMemo(() => {
    const rows = sources.data?.sources ?? []
    const seen = new Set(rows.map((row) => row.kind))
    return [
      ...rows.map((row) => ({ kind: row.kind, source: row })),
      ...(sources.data?.connectable ?? [])
        .filter((kind) => !seen.has(kind))
        .map((kind) => ({ kind, source: null })),
    ]
  }, [sources.data])

  const signOut = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      // Hard navigation: the cleared cache must not be repopulated by
      // in-flight queries from this page.
      queryClient.clear()
      window.location.assign('/sign-in')
    },
  })

  const goBack = () => {
    // The OAuth landing carries one of these two params and nothing else does.
    const arrivedFromOAuth = connected !== undefined || connectError !== undefined
    if (canGoBackInApp(arrivedFromOAuth, window.history.length)) router.history.back()
    else void router.navigate({ to: '/today' })
  }

  const name = me.data?.display_name ?? me.data?.email ?? ''
  const stats = trips.data ? travelStats(trips.data) : undefined

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-lg flex-col">
      <header className="flex flex-none items-center gap-3 border-b border-border px-4 pb-3.5 pt-[max(1rem,env(safe-area-inset-top))]">
        <button
          onClick={goBack}
          aria-label="Back"
          className="grid size-10 flex-none place-items-center rounded-xl border border-border bg-card hover:bg-state-neutral-soft focus-visible:outline-2 focus-visible:outline-primary"
        >
          <svg
            width="19"
            height="19"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.9}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <h1 className="text-body font-semibold">Profile</h1>
      </header>

      <main className="flex-1 px-5 pb-10 pt-5">
        <div className="flex items-center gap-3.5">
          <div className="grid size-[52px] flex-none place-items-center rounded-full border border-border bg-state-confirmed-soft text-body font-semibold text-primary-deep">
            {initials(name)}
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-display text-display-sm leading-tight">
              {name}
            </p>
            {stats && (
              <p className="mt-1 text-caption text-muted-soft">
                {stats.tripsThisYear} {stats.tripsThisYear === 1 ? 'trip' : 'trips'}{' '}
                this year · {stats.nightsAway}{' '}
                {stats.nightsAway === 1 ? 'night' : 'nights'} away
              </p>
            )}
          </div>
        </div>

        {prefs.isPending && <LoadingState label="Loading your preferences" />}
        {prefs.isError && (
          <DegradedState
            title="Preferences are unreachable"
            detail="Nothing shown here is made up. Check your connection and retry."
            onRetry={() => void prefs.refetch()}
          />
        )}

        {prefs.data && (
          <>
            <SectionLabel>What TravelWell plans around</SectionLabel>
            <ChipRow chips={PREF_CHIPS} prefs={prefs.data} onPatch={patch} />

            <SectionLabel>Memberships I can use</SectionLabel>
            <ChipRow chips={MEMBERSHIP_CHIPS} prefs={prefs.data} onPatch={patch} />

            <SectionLabel>Day-pass budget</SectionLabel>
            <div className="flex gap-2">
              {BUDGETS.map((budget) => {
                const selected = prefs.data.day_pass_budget_cents === budget.cents
                return (
                  <button
                    key={budget.label}
                    aria-pressed={selected}
                    onClick={() =>
                      patch({
                        day_pass_budget_cents: selected ? null : budget.cents,
                      })
                    }
                    className={`h-[46px] flex-1 rounded-xl border text-body-sm font-semibold ${
                      selected
                        ? 'border border-primary bg-state-confirmed-soft text-primary'
                        : 'border-border bg-card text-ink'
                    }`}
                  >
                    {budget.label}
                  </button>
                )
              })}
            </div>

            <SectionLabel>Amenities I look for</SectionLabel>
            <ChipRow chips={AMENITY_CHIPS} prefs={prefs.data} onPatch={patch} />

            <SectionLabel>What TravelWell may do on its own</SectionLabel>
            <div className="overflow-hidden rounded-[18px] border border-border bg-card">
              {PERMS.map((perm) => {
                const on = prefs.data[perm.field]
                return (
                  <div
                    key={perm.field}
                    className="flex items-center gap-3 border-b border-border-soft p-4 last:border-b-0"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-body-sm font-semibold leading-tight">
                        {perm.label}
                      </p>
                      <p className="mt-0.5 text-caption text-muted-soft">
                        {perm.sub(on)}
                      </p>
                    </div>
                    <Toggle
                      on={on}
                      label={perm.label}
                      onChange={() => patch({ [perm.field]: !on })}
                    />
                  </div>
                )
              })}
            </div>

            <SectionLabel>Sources</SectionLabel>
            {connected !== undefined && (
              <p
                role="status"
                className="rounded-[14px] border border-border bg-card px-4 py-3 text-body-sm font-semibold text-primary-deep"
              >
                {sourceName(connected)} is connected.
              </p>
            )}
            {connectError !== undefined && (
              <p
                role="alert"
                className="rounded-[14px] border border-border bg-card px-4 py-3 text-body-sm text-state-failed"
              >
                {CONNECT_ERROR_COPY[connectError] ??
                  'The connection did not complete. Try again.'}
              </p>
            )}
            {sources.isError ? (
              <DegradedState
                title="Sources are unreachable"
                detail="Connection status can't be shown right now."
                onRetry={() => void sources.refetch()}
              />
            ) : (
              <div className="overflow-hidden rounded-[18px] border border-border bg-card">
                {sourceRows.map(({ kind, source }) => {
                  const meta = SOURCE_META[kind] ?? { tag: 'SRC', name: kind }
                  const state = source ? SOURCE_STATE[source.status] : undefined
                  const action = sourceAction(
                    source?.status ?? null,
                    (sources.data?.connectable ?? []).includes(kind),
                  )
                  const detail =
                    source?.last_synced_at != null
                      ? `synced ${formatAgo(source.last_synced_at)}`
                      : meta.sub
                  const ranHere = sync.variables === kind
                  return (
                    <div key={kind} className="border-b border-border-soft last:border-b-0">
                      <div className="flex items-center gap-3 p-4">
                        <div className="grid size-8 flex-none place-items-center rounded-[10px] bg-state-neutral-soft font-mono text-[11px] font-semibold text-muted">
                          {meta.tag}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-body-sm font-semibold leading-tight">
                            {meta.name}
                          </p>
                          {/* Each part unbreakable, the separator outside
                              both: the button leaves this column narrow
                              enough that a free break lands inside
                              "1 hr ago", and the only good break is the dot. */}
                          <p className="mt-0.5 text-caption">
                            <span className={`whitespace-nowrap ${state?.ink ?? 'text-muted'}`}>
                              {state?.text ?? 'Not connected'}
                            </span>
                            {detail !== undefined && (
                              <>
                                {' · '}
                                <span className="whitespace-nowrap text-muted-soft">
                                  {detail}
                                </span>
                              </>
                            )}
                          </p>
                        </div>
                        {action !== null && (
                          <Button
                            variant={action === 'disconnect' ? 'ghost' : 'secondary'}
                            className="h-9 flex-none px-3 text-body-sm"
                            onClick={() => {
                              if (action === 'disconnect') setConfirming(kind)
                              else void startConnect(kind)
                            }}
                          >
                            {SOURCE_ACTION_LABEL[action]}
                          </Button>
                        )}
                      </div>
                      {/* Hidden while the disconnect confirmation is open: that
                          panel is a decision, and a second button under it is
                          noise. */}
                      {source?.status === 'connected' && confirming !== kind && (
                        <div className="flex items-center gap-3 border-t border-border-soft px-4 py-3">
                          <Button
                            variant="secondary"
                            className="h-9 flex-none px-3 text-body-sm"
                            /* Every row's button, not just this one: the
                               mutation is singular, so a second run in flight
                               would silently retarget the first one's state. */
                            disabled={sync.isPending}
                            onClick={() => sync.mutate(kind)}
                          >
                            {ranHere && sync.isPending ? 'Syncing…' : 'Sync now'}
                          </Button>
                          {ranHere && sync.isError && (
                            <p role="alert" className="text-caption text-state-failed">
                              {syncFailureMessage(sync.error)}
                            </p>
                          )}
                          {ranHere && sync.isSuccess && (
                            <p role="status" className="text-caption text-muted">
                              {syncOutcomeMessage(sync.data)}
                            </p>
                          )}
                        </div>
                      )}
                      {confirming === kind && (
                        <div className="border-t border-border-soft bg-state-neutral-soft px-4 py-3">
                          <p className="text-caption text-muted">
                            Disconnecting deletes the access TravelWell stores for
                            this account. Events already synced stay on your trips.
                            Removing TravelWell from the account itself is done on
                            Google&rsquo;s permissions page.
                          </p>
                          {disconnect.isError && (
                            <p role="alert" className="mt-2 text-caption text-state-failed">
                              Could not disconnect. Check your connection and retry.
                            </p>
                          )}
                          <div className="mt-3 flex gap-2">
                            <Button
                              className="h-9 px-3 text-body-sm"
                              disabled={disconnect.isPending}
                              onClick={() => disconnect.mutate(kind)}
                            >
                              {disconnect.isPending ? 'Disconnecting…' : 'Disconnect'}
                            </Button>
                            <Button
                              variant="ghost"
                              className="h-9 px-3 text-body-sm"
                              onClick={() => setConfirming(null)}
                            >
                              Cancel
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
                {sources.isPending && <LoadingState label="Loading your sources" />}
                {/* Gated on the query having answered: an unresolved query and
                    a genuinely empty one both give zero rows, and only one of
                    them can be told the user as a fact. */}
                {!sources.isPending && sourceRows.length === 0 && (
                  <p className="p-4 text-caption text-muted">
                    No sources can be connected in this build.
                  </p>
                )}
              </div>
            )}

            <button
              onClick={goBack}
              className="mt-5 h-[52px] w-full rounded-control bg-ink text-body font-semibold text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              Done
            </button>
          </>
        )}

        {signOut.isError && (
          <p className="mt-4 text-caption font-semibold text-state-attention">
            Could not sign out. Check your connection and retry.
          </p>
        )}
        <button
          onClick={() => signOut.mutate()}
          disabled={signOut.isPending}
          className="mt-3 h-[52px] w-full rounded-control border border-border bg-card text-body font-semibold text-state-attention focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-60"
        >
          {signOut.isPending ? 'Signing out…' : 'Sign out'}
        </button>
      </main>
    </div>
  )
}
