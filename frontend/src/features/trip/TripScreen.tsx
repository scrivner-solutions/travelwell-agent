import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getRouteApi } from '@tanstack/react-router'
import { formatInTimeZone } from 'date-fns-tz'
import { Button } from '@/components/ui/Button'
import { Card, CardButton } from '@/components/ui/Card'
import { Pill, StatusBadge } from '@/components/ui/StatusBadge'
import { LoadingState, EmptyState, DegradedState } from '@/components/ui/ScreenState'
import { ProfileButton } from '@/components/ui/ProfileButton'
import {
  confirmTrip,
  dismissTrip,
  timelineQueryOptions,
  tripsQueryOptions,
  type TimelineEntry,
  type Trip,
} from '@/api/queries'
import { ApiError } from '@/api/client'
import {
  calendarSpan,
  evidenceKindSummary,
  evidenceSourceSummary,
  evidenceTag,
  focusTrip,
  isPast,
  needsYouLabel,
  sourceLabel,
  tripBadge,
  tripDays,
} from '@/lib/trips'
import { formatDateRange, formatTripTime } from '@/lib/time'
import { AddTripSheet } from './AddTripSheet'

const route = getRouteApi('/_shell/trip')

// Calendar-strip cell text: "TUE" stacked over "25".
function cellParts(iso: string): { weekday: string; dayOfMonth: number } {
  const d = new Date(`${iso}T00:00:00Z`)
  return {
    weekday: d.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' }),
    dayOfMonth: d.getUTCDate(),
  }
}

// Day-chip dots, one per entry: gray commitments, periwinkle unsettled
// suggestions, blue settled plan items.
function entryDotClass(entry: TimelineEntry): string {
  if (entry.entry_type === 'calendar_event') return 'bg-state-neutral'
  return entry.plan_item?.status === 'suggested'
    ? 'bg-state-suggested'
    : 'bg-state-confirmed'
}

function EvidenceRow({
  kind,
  summary,
  detail,
  source,
}: {
  kind: string
  summary: string
  detail?: string
  source: string
}) {
  return (
    <li className="flex items-center gap-3">
      <span className="grid size-9 flex-none place-items-center rounded-lg bg-state-neutral-soft font-mono text-label font-semibold text-state-neutral">
        {evidenceTag(kind)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-body-sm font-semibold text-ink">{summary}</span>
        {detail !== undefined && (
          <span className="block text-caption text-muted">{detail}</span>
        )}
      </span>
      <span className="flex-none text-label text-muted">{sourceLabel(source)}</span>
    </li>
  )
}

function Chevron({ open, className = '' }: { open: boolean; className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      fill="none"
      className={`size-4 flex-none transition-transform motion-reduce:transition-none ${open ? 'rotate-180' : ''} ${className}`}
    >
      <path
        d="M4 6.5l4 4 4-4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** Focused trip's provenance, collapsed to "Found in your calendar and email"
 * until tapped. Mount with key={trip.id} so it re-collapses per trip. */
function EvidenceCard({ evidence }: { evidence: NonNullable<Trip['evidence']> }) {
  const [open, setOpen] = useState(false)
  return (
    <Card>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="trip-evidence"
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <span className="min-w-0">
          <span className="block text-body-sm font-semibold text-ink">
            Found in your {evidenceSourceSummary(evidence)}
          </span>
          <span className="block text-caption text-muted">
            {evidenceKindSummary(evidence)}
          </span>
        </span>
        <Chevron open={open} className="text-muted" />
      </button>
      {open && (
        <ul
          id="trip-evidence"
          className="mt-3 flex flex-col gap-2.5 border-t border-border-soft pt-3"
        >
          {evidence.map((row, i) => (
            <EvidenceRow
              key={i}
              kind={row.kind}
              summary={row.summary}
              detail={row.detail}
              source={row.source}
            />
          ))}
        </ul>
      )}
    </Card>
  )
}

// Both detection layouts answer the same gate, so the mutations live here and
// neither layout can drift from the other.
function useDetectionGate(trip: Trip) {
  const queryClient = useQueryClient()
  const onSettled = () => queryClient.invalidateQueries({ queryKey: ['trips'] })
  const confirm = useMutation({
    mutationFn: () => confirmTrip(trip.id, trip.updated_at),
    onSettled,
  })
  // Detection is noisy, so the gate opens both ways: without this the list can
  // only ever grow.
  const dismiss = useMutation({
    mutationFn: () => dismissTrip(trip.id, trip.updated_at),
    onSettled,
  })
  const error = confirm.error ?? dismiss.error
  return {
    confirm,
    dismiss,
    error,
    pending: confirm.isPending || dismiss.isPending,
    conflicted: error instanceof ApiError && error.status === 409,
  }
}

type DetectionGate = ReturnType<typeof useDetectionGate>

function GateError({ gate }: { gate: DetectionGate }) {
  if (gate.conflicted) {
    return (
      <p className="mt-3 text-caption font-semibold text-state-attention">
        This trip changed on the server. It has been refreshed; try again.
      </p>
    )
  }
  if (gate.error === null) return null
  return (
    <p className="mt-3 text-caption font-semibold text-state-attention">
      Could not update the trip. Check your connection and retry.
    </p>
  )
}

function GateButtons({
  gate,
  compact = false,
}: {
  gate: DetectionGate
  compact?: boolean
}) {
  const height = compact ? 'h-9' : 'h-11'
  return (
    <div className={`mt-3 flex gap-2 ${compact ? 'justify-end' : ''}`}>
      <button
        onClick={() => gate.confirm.mutate()}
        disabled={gate.pending}
        className={`${height} ${compact ? 'px-4' : 'flex-1'} rounded-panel bg-primary text-body-sm font-semibold text-white disabled:opacity-60`}
      >
        {gate.confirm.isPending ? 'Confirming…' : 'Use this trip'}
      </button>
      <button
        onClick={() => gate.dismiss.mutate()}
        disabled={gate.pending}
        className={`${height} rounded-panel border border-border px-4 text-body-sm font-semibold text-muted disabled:opacity-60`}
      >
        {gate.dismiss.isPending ? 'Dismissing…' : 'Not a trip'}
      </button>
    </div>
  )
}

function EvidenceList({ trip, className = '' }: { trip: Trip; className?: string }) {
  if (trip.evidence === undefined || trip.evidence.length === 0) return null
  return (
    <ul className={`flex flex-col gap-2 ${className}`}>
      {trip.evidence.map((row, i) => (
        <EvidenceRow
          key={i}
          kind={row.kind}
          summary={row.summary}
          detail={row.detail}
          source={row.source}
        />
      ))}
    </ul>
  )
}

/** The detection gate at full size: evidence rows, confirm and dismiss. */
function DetectionCard({ trip }: { trip: Trip }) {
  const gate = useDetectionGate(trip)

  return (
    <Card>
      {/* No per-card label: the section heading above already says these were
          found for you. */}
      <p className="font-display text-display-sm">{trip.destination_name}</p>
      <p className="text-caption text-muted">
        {formatDateRange(trip.starts_on, trip.ends_on)}
      </p>
      <EvidenceList trip={trip} className="mt-3 border-t border-border-soft pt-3" />
      <GateError gate={gate} />
      <GateButtons gate={gate} />
    </Card>
  )
}

// The second detection onward. The card above already showed what evidence
// looks like, so here it sits behind a tap; the two buttons never do, because
// collapsing an action is how a decision gets lost.
function DetectionRow({ trip }: { trip: Trip }) {
  const [showEvidence, setShowEvidence] = useState(false)
  const gate = useDetectionGate(trip)
  const hasEvidence = trip.evidence !== undefined && trip.evidence.length > 0

  return (
    <Card>
      <p className="text-body font-semibold">{trip.destination_name}</p>
      <p className="text-caption text-muted">
        {formatDateRange(trip.starts_on, trip.ends_on)}
      </p>
      {hasEvidence && (
        <button
          onClick={() => setShowEvidence((open) => !open)}
          aria-expanded={showEvidence}
          className="mt-2 flex items-center gap-1 text-caption font-semibold text-muted"
        >
          Why this looks like a trip
          <Chevron open={showEvidence} className="size-4" />
        </button>
      )}
      {showEvidence && (
        <EvidenceList trip={trip} className="mt-2 border-t border-border-soft pt-3" />
      )}
      <GateError gate={gate} />
      <GateButtons gate={gate} compact />
    </Card>
  )
}

function TripRow({
  trip,
  selected,
  onSelect,
}: {
  trip: Trip
  selected: boolean
  onSelect: (id: string) => void
}) {
  const badge = tripBadge(trip)
  const needsYou = needsYouLabel(trip.needs_you_count, trip.needs_you_kind)

  return (
    <CardButton
      aria-current={selected || undefined}
      className={selected ? 'border-ink' : ''}
      onClick={() => onSelect(trip.id)}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          <span className="block text-body font-semibold">{trip.destination_name}</span>
          <span className="block text-caption text-muted">
            {formatDateRange(trip.starts_on, trip.ends_on)}
            {trip.label !== undefined && ` · ${trip.label}`}
          </span>
        </span>
        {badge !== null && <Pill {...badge} />}
      </div>
      {/* Below the badge, not beside it: the badge is the thing you cannot act
          on, so it must not outrank the thing you can. */}
      {needsYou !== null && (
        <p className="mt-2 text-caption font-semibold text-state-attention">
          {needsYou}
        </p>
      )}
    </CardButton>
  )
}

function TripSection({
  id,
  title,
  trips,
  open,
  onToggle,
  selectedId,
  onSelect,
}: {
  id: string
  title: string
  trips: Trip[]
  open: boolean
  onToggle: () => void
  selectedId?: string
  onSelect: (id: string) => void
}) {
  return (
    <>
      <button
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={id}
        className="mt-2 flex w-full items-center justify-between border-t border-border-soft pt-4 text-label font-semibold uppercase tracking-wide text-muted"
      >
        {title} · {trips.length}
        <Chevron open={open} />
      </button>
      {open && (
        <div id={id} className="flex flex-col gap-3">
          {trips.map((t) => (
            <TripRow
              key={t.id}
              trip={t}
              selected={t.id === selectedId}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </>
  )
}

export function TripScreen() {
  const { day, trip: tripId, sheet } = route.useSearch()
  const navigate = route.useNavigate()
  // Ephemeral disclosures, not URL state: they collapse again on any navigation.
  const [upcomingOpen, setUpcomingOpen] = useState(false)
  const [pastOpen, setPastOpen] = useState(false)
  const trips = useQuery(tripsQueryOptions())
  // ?trip= (a tapped card or a deep link) wins; otherwise the agent's focus.
  const trip = trips.data
    ? (trips.data.find((t) => t.id === tripId) ?? focusTrip(trips.data))
    : undefined
  const detected = trips.data?.filter((t) => t.state === 'detected') ?? []
  const [firstDetection, ...restDetections] = detected
  // Detections have their own section above; the rest split by tense, so the
  // heading carries what a per-row badge would otherwise have to repeat.
  const listedTrips = trips.data?.filter((t) => t.state !== 'detected') ?? []
  const upcomingTrips = listedTrips.filter((t) => !isPast(t))
  const pastTrips = listedTrips.filter(isPast)

  // day resets: the old selection belongs to the previous trip's range.
  const onSelectTrip = useCallback(
    (id: string) => void navigate({ search: { trip: id, day: undefined } }),
    [navigate],
  )
  const headerBadge = trip ? tripBadge(trip) : null

  const rangeDays = trip ? tripDays(trip.starts_on, trip.ends_on) : []
  const todayIso = trip
    ? formatInTimeZone(new Date(), trip.timezone, 'yyyy-MM-dd')
    : ''

  // One unfiltered fetch: the same entries drive the day-chip dots and the
  // selected day's timeline, so switching days never refetches.
  const timeline = useQuery({
    ...timelineQueryOptions(trip?.id ?? ''),
    enabled: trip !== undefined,
  })
  const entriesByDay = new Map<string, TimelineEntry[]>()
  if (trip && timeline.data) {
    for (const entry of timeline.data) {
      const entryDay = formatInTimeZone(entry.starts_at, trip.timezone, 'yyyy-MM-dd')
      entriesByDay.set(entryDay, [...(entriesByDay.get(entryDay) ?? []), entry])
    }
  }
  // Chips cover the trip range plus any entry day outside it (red-eye,
  // late checkout), so no entry is ever unreachable.
  const days = [...new Set([...rangeDays, ...entriesByDay.keys()])].sort()
  // The strip pads those days to whole weeks for calendar context; padding
  // days render but stay inert, so `days` alone decides what is selectable.
  const firstDay = days[0]
  const lastDay = days[days.length - 1]
  const strip =
    firstDay !== undefined && lastDay !== undefined
      ? calendarSpan(firstDay, lastDay)
      : []
  // Stable ref identity: fires only when the selected cell (re)mounts, so a
  // deep link lands centered without re-scrolling on every render.
  const centerSelected = useCallback(
    (node: HTMLButtonElement | null) =>
      node?.scrollIntoView({ inline: 'center', block: 'nearest' }),
    [],
  )
  // Today wins when it is a chip; while the timeline is loading we cannot
  // know that yet (red-eye days), so select nothing rather than a wrong day.
  const selectedDay =
    day ??
    (days.includes(todayIso)
      ? todayIso
      : timeline.isPending
        ? undefined
        : rangeDays[0])
  const dayEntries = entriesByDay.get(selectedDay ?? '') ?? []
  const commitmentCount = dayEntries.filter(
    (e) => e.entry_type === 'calendar_event',
  ).length
  // "Day N" counts within the trip range only; 0 marks an out-of-range day.
  const tripDayNumber = selectedDay ? rangeDays.indexOf(selectedDay) + 1 : 0
  const weekdayLong = selectedDay
    ? new Date(`${selectedDay}T00:00:00Z`).toLocaleDateString('en-US', {
        weekday: 'long',
        timeZone: 'UTC',
      })
    : ''

  return (
    <>
      <header className="mb-4">
        {/* The dot this replaces encoded five states in two hues with no
            legend and aria-hidden on top, so it told nobody anything. Same
            word the row carries, so there is one trip vocabulary. */}
        <p className="flex items-center gap-2 text-caption font-semibold uppercase tracking-wide text-muted">
          {trip
            ? `${formatDateRange(trip.starts_on, trip.ends_on)}${trip.label !== undefined ? ` · ${trip.label}` : ''}`
            : 'Trip'}
          {trip && headerBadge !== null && <Pill {...headerBadge} />}
        </p>
        <div className="flex items-center justify-between">
          <h1 className="font-display text-display font-medium">
            {trip?.destination_name.split(',')[0] ?? 'Trip'}
          </h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() =>
                void navigate({ search: (prev) => ({ ...prev, sheet: 'new' }) })
              }
              aria-label="Add a trip"
              className="grid size-10 flex-none place-items-center rounded-full border border-border bg-card text-muted hover:bg-state-neutral-soft focus-visible:outline-2 focus-visible:outline-primary"
            >
              <svg
                width="19"
                height="19"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.8}
                strokeLinecap="round"
                aria-hidden
              >
                <path d="M12 5v14M5 12h14" />
              </svg>
            </button>
            <ProfileButton />
          </div>
        </div>
      </header>

      {trips.isPending && <LoadingState label="Loading your trips" />}
      {trips.isError && (
        <DegradedState
          title="TravelWell is unreachable"
          onRetry={() => void trips.refetch()}
        />
      )}
      {trips.isSuccess && trips.data.length === 0 && (
        <EmptyState
          title="No trips yet"
          detail="Trips detected from your calendar and trips you add by hand both live here."
          action={
            <Button
              onClick={() =>
                void navigate({ search: (prev) => ({ ...prev, sheet: 'new' }) })
              }
            >
              Add a trip yourself
            </Button>
          }
        />
      )}

      <div className="flex flex-col gap-3">
        {trip && (
          <>
            {trip.evidence !== undefined && trip.evidence.length > 0 && (
              <EvidenceCard key={trip.id} evidence={trip.evidence} />
            )}

            <div className="flex gap-1.5 overflow-x-auto" role="tablist" aria-label="Trip days">
              {strip.map((d) => {
                const selectable = days.includes(d)
                const selected = d === selectedDay
                const { weekday, dayOfMonth } = cellParts(d)
                return (
                  <button
                    key={d}
                    role="tab"
                    aria-selected={selected}
                    disabled={!selectable}
                    ref={selected ? centerSelected : undefined}
                    onClick={() =>
                      void navigate({ search: (prev) => ({ ...prev, day: d }) })
                    }
                    className={`w-12 flex-none rounded-panel border py-2 text-center ${
                      selected
                        ? 'border-ink bg-ink text-white'
                        : selectable
                          ? 'border-border-soft bg-surface text-ink'
                          : 'border-transparent text-muted-soft'
                    }`}
                  >
                    <span
                      className={`block text-label uppercase tracking-wide ${
                        selected ? 'text-white/70' : selectable ? 'text-muted' : ''
                      }`}
                    >
                      {weekday}
                    </span>
                    <span className="block text-body-sm font-semibold">
                      {dayOfMonth}
                    </span>
                    <span className="mt-1 flex min-h-[4px] justify-center gap-[3px]">
                      {(entriesByDay.get(d) ?? []).slice(0, 3).map((entry, i) => (
                        <span
                          key={i}
                          className={`size-[4px] rounded-full ${entryDotClass(entry)}`}
                        />
                      ))}
                    </span>
                  </button>
                )
              })}
            </div>

            {/* min-height so switching between busy and empty days never
                shifts the sections below within the visible viewport. */}
            <div className="flex min-h-[55dvh] flex-col gap-3">
              {selectedDay !== undefined && days.includes(selectedDay) && (
                <div className="flex items-baseline justify-between px-1">
                  <p className="font-display text-display-sm">
                    {tripDayNumber > 0 ? `Day ${tripDayNumber} · ${weekdayLong}` : weekdayLong}
                  </p>
                  <p className="text-caption text-muted">
                    {commitmentCount}{' '}
                    {commitmentCount === 1 ? 'commitment' : 'commitments'}
                  </p>
                </div>
              )}

              {timeline.isPending && <LoadingState label="Loading the day" />}
              {timeline.isError && (
                <DegradedState
                  title="Can't load this day"
                  onRetry={() => void timeline.refetch()}
                />
              )}
              {timeline.isSuccess && dayEntries.length === 0 && (
                <EmptyState
                  title="Nothing on this day"
                  detail="No commitments or plan items land here yet."
                />
              )}
              {dayEntries.map((entry) =>
                entry.entry_type === 'calendar_event' && entry.calendar_event ? (
                  <div
                    key={`cal-${entry.calendar_event.id}`}
                    className="flex items-baseline gap-3 px-1"
                  >
                    <span className="w-16 flex-none text-right text-caption text-muted">
                      {formatTripTime(entry.starts_at, trip.timezone)}
                    </span>
                    <div>
                      <p className="text-body-sm text-muted">{entry.calendar_event.title}</p>
                      {entry.calendar_event.location_name !== undefined && (
                        <p className="text-caption text-muted-soft">
                          {entry.calendar_event.location_name}
                        </p>
                      )}
                    </div>
                  </div>
                ) : entry.plan_item ? (
                  <div key={`item-${entry.plan_item.id}`} className="flex items-start gap-3">
                    <span className="w-16 flex-none pt-4 text-right text-caption text-muted">
                      {formatTripTime(entry.starts_at, trip.timezone)}
                    </span>
                    <Card
                      className={`flex-1 ${
                        entry.plan_item.status === 'suggested'
                          ? 'border-dashed border-state-suggested'
                          : ''
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-body font-semibold">{entry.plan_item.title}</p>
                          {entry.plan_item.selected_option?.display_summary !== undefined && (
                            <p className="text-caption text-muted">
                              {entry.plan_item.selected_option.display_summary}
                            </p>
                          )}
                        </div>
                        <StatusBadge status={entry.plan_item.status} />
                      </div>
                    </Card>
                  </div>
                ) : null,
              )}
            </div>
          </>
        )}

        {/* Gate 1 lives below the trip you came to see, not on top of it, and
            out of All trips: a detection is a claim that a trip exists, not a
            trip. It gets no notification, so the tab count is what surfaces it. */}
        {detected.length > 0 && (
          <>
            <p className="mt-2 border-t border-border-soft pt-4 text-label font-semibold uppercase tracking-wide text-muted">
              Found for you · {detected.length}
            </p>
            {/* Density-adaptive rather than capped at N: one full card teaches
                the format, the rest are rows, so ten detections cost about what
                two cards used to and nothing gets hidden behind a "show more". */}
            {firstDetection !== undefined && (
              // Keyed so answering one detection remounts the next into the
              // card slot instead of inheriting its mutation state.
              <DetectionCard key={firstDetection.id} trip={firstDetection} />
            )}
            {restDetections.map((t) => (
              <DetectionRow key={t.id} trip={t} />
            ))}
          </>
        )}

        {/* Two sections, not one list with a tense badge on every row: a
            heading labels the group once, which is the whole reason `Past`
            is not a word the user has to read N times. */}
        {trips.isSuccess && upcomingTrips.length > 0 && (
          <TripSection
            id="upcoming-trips"
            title="Upcoming"
            trips={upcomingTrips}
            open={upcomingOpen}
            onToggle={() => setUpcomingOpen((open) => !open)}
            selectedId={trip?.id}
            onSelect={onSelectTrip}
          />
        )}

        {trips.isSuccess && pastTrips.length > 0 && (
          <TripSection
            id="past-trips"
            title="Past"
            trips={pastTrips}
            open={pastOpen}
            onToggle={() => setPastOpen((open) => !open)}
            selectedId={trip?.id}
            onSelect={onSelectTrip}
          />
        )}
      </div>

      <AddTripSheet
        open={sheet === 'new'}
        onClose={() =>
          void navigate({ search: (prev) => ({ ...prev, sheet: undefined }) })
        }
        // Land on the new trip; the old day belongs to another trip's range.
        onCreated={(t) =>
          void navigate({ search: { trip: t.id, day: undefined, sheet: undefined } })
        }
      />
    </>
  )
}
