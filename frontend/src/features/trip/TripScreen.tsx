import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getRouteApi } from '@tanstack/react-router'
import { formatInTimeZone } from 'date-fns-tz'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { LoadingState, EmptyState, DegradedState } from '@/components/ui/ScreenState'
import { ProfileButton } from '@/components/ui/ProfileButton'
import {
  confirmTrip,
  dismissTrip,
  sourcesQueryOptions,
  timelineQueryOptions,
  tripsQueryOptions,
  type TimelineEntry,
  type Trip,
} from '@/api/queries'
import { ApiError } from '@/api/client'
import {
  calendarSpan,
  evidenceRows,
  focusTrip,
  isPast,
  openingDay,
  tripDays,
  tripDot,
  tripStateWord,
} from '@/lib/trips'
import { formatDateRange } from '@/lib/time'
import { PlanSection } from '@/features/plan/PlanSection'
import { PlanItemSheet } from '@/features/plan/PlanItemSheet'
import { ProvenanceSheet } from '@/features/plan/ProvenanceSheet'
import { AddTripSheet } from './AddTripSheet'
import { CommitmentRow, PlanItemRow } from './TimelineRow'
import { FactRowView, TripFactsCard } from './TripFactsCard'
import { TripListRow } from './TripListRow'
import { TripsSheet } from './TripsSheet'

const route = getRouteApi('/_shell/trip')

// Calendar-strip cell text: one line, "Tue 18". Composed rather than asked of
// Intl, which orders an en-US weekday+day as "18 Tue".
function cellLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`)
  const weekday = d.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' })
  return `${weekday} ${d.getUTCDate()}`
}

// Day-chip dots, one per entry, in the timeline's own vocabulary: a commitment
// is `--state-existing` here and in the row it summarises, periwinkle is still
// being proposed, blue is settled. On the selected chip they all wash out to
// the surface colour, because the chip's own fill is already the signal.
function entryDotClass(entry: TimelineEntry, selected: boolean): string {
  if (selected) return 'bg-surface/45'
  if (entry.entry_type === 'calendar_event') return 'bg-state-existing'
  return entry.plan_item?.status === 'suggested'
    ? 'bg-state-suggested'
    : 'bg-state-confirmed'
}

/** Size is the caller's: the header switcher wants 12px, a disclosure 16px. */
function Chevron({ open, className = '' }: { open: boolean; className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      fill="none"
      className={`flex-none transition-transform motion-reduce:transition-none ${open ? 'rotate-180' : ''} ${className}`}
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
      {evidenceRows(trip.evidence).map((row, i) => (
        <FactRowView key={i} row={row} />
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

export function TripScreen() {
  const { day, trip: tripId, sheet } = route.useSearch()
  const navigate = route.useNavigate()
  const [provenanceItem, setProvenanceItem] = useState<string | undefined>(undefined)
  const [openItem, setOpenItem] = useState<string | undefined>(undefined)
  const trips = useQuery(tripsQueryOptions())
  // Drives the facts card's trust strip only. Its absence degrades to no
  // strip, never to a blocked card: the facts are true either way.
  const sources = useQuery(sourcesQueryOptions())
  // ?trip= (a tapped card or a deep link) wins; otherwise the agent's focus.
  const trip = trips.data
    ? (trips.data.find((t) => t.id === tripId) ?? focusTrip(trips.data))
    : undefined
  const detected = trips.data?.filter((t) => t.state === 'detected') ?? []
  const [firstDetection, ...restDetections] = detected
  // Detections have their own section above; the rest split by tense, so the
  // heading carries what a per-row badge would otherwise have to repeat.
  const listedTrips = trips.data?.filter((t) => t.state !== 'detected') ?? []
  const pastTrips = listedTrips.filter(isPast)
  // The trip you are reading is the whole screen above; listing it again below
  // would be the screen offering to navigate you to where you already are.
  const otherTrips = listedTrips.filter((t) => !isPast(t) && t.id !== trip?.id)

  // Picking a trip opens its own screen rather than re-pointing this one.
  // This screen is the working surface for the trip you are on - a day strip
  // and a timeline - and it was answering for finished trips too, giving them
  // an empty strip and an empty day. Every trip now has somewhere to land.
  const onSelectTrip = useCallback(
    (id: string) => void navigate({ to: '/trip/$tripId', params: { tripId: id } }),
    [navigate],
  )
  const openTripsSheet = useCallback(
    () => void navigate({ search: (prev) => ({ ...prev, sheet: 'trips' }) }),
    [navigate],
  )

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
  const selectedDay =
    day ??
    openingDay({
      days,
      todayIso,
      dayHasEntries: (d) => entriesByDay.has(d),
      timelinePending: timeline.isPending,
    })
  const dayEntries = entriesByDay.get(selectedDay ?? '') ?? []
  // Read back out of the live timeline rather than captured at tap, so a swap
  // made inside the sheet shows in the sheet that made it. Guarded rather than
  // relying on the find missing: with no open item every commitment entry has
  // an undefined plan_item id and would match.
  const openPlanItem =
    openItem === undefined
      ? undefined
      : (timeline.data?.find((e) => e.plan_item?.id === openItem)?.plan_item ?? undefined)
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
      <header className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          {/* The identifying line is also the control that changes it: dates
              and purpose are how you tell one trip from another, so making
              them tappable puts switching where you already look. The dot has
              no legend here - the sheet it opens is the legend, where every
              trip carries the same dot beside its state word. */}
          <button
            onClick={openTripsSheet}
            disabled={trip === undefined}
            aria-label={
              trip
                ? `${trip.destination_name}, ${tripStateWord(trip)}. Switch trips`
                : 'Switch trips'
            }
            className="flex max-w-full items-center gap-2 text-eyebrow-wide font-semibold uppercase text-muted-soft disabled:opacity-60"
          >
            {trip && (
              <span
                className={`size-1.5 flex-none rounded-full ${tripDot(trip)}`}
                aria-hidden
              />
            )}
            <span className="truncate">
              {trip
                ? `${formatDateRange(trip.starts_on, trip.ends_on)}${trip.label !== undefined ? ` · ${trip.label}` : ''}`
                : 'Trip'}
            </span>
            <Chevron open={false} className="size-3" />
          </button>
          <h1 className="mt-2 font-display text-display">
            {trip?.destination_name.split(',')[0] ?? 'Trip'}
          </h1>
        </div>
        <ProfileButton />
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
            {/* Open, not behind a disclosure: "does it have my trip right?"
                is the question you arrive with, and it was the one thing the
                screen made you tap to answer. */}
            <TripFactsCard
              rows={evidenceRows(trip.evidence ?? [])}
              sources={sources.data}
            />

            {/* Gate 2, above the days it would fill: the offer has to be read
                before the timeline showing dashed suggestions makes sense. */}
            <PlanSection trip={trip} onShowProvenance={setProvenanceItem} />

            {/* Chips grow to fill the width and stop shrinking at 74px, so a
                four-day trip spreads and a padded fortnight scrolls. */}
            <div
              className="flex gap-[7px] overflow-x-auto"
              role="tablist"
              aria-label="Trip days"
            >
              {strip.map((d) => {
                const selectable = days.includes(d)
                const selected = d === selectedDay
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
                    className={`flex min-w-[74px] flex-1 flex-col items-center gap-[7px] rounded-control border px-2 pt-2.5 pb-[9px] ${
                      selected
                        ? 'border-ink bg-ink'
                        : selectable
                          ? 'border-border bg-card'
                          : 'border-transparent'
                    }`}
                  >
                    <span
                      className={`whitespace-nowrap text-label font-semibold ${
                        selected
                          ? 'text-surface'
                          : selectable
                            ? 'text-ink'
                            : 'text-muted-faint'
                      }`}
                    >
                      {cellLabel(d)}
                    </span>
                    {/* Fixed height so a day with nothing on it is the same
                        size as a day that is full. Capped: past about five the
                        dots stop counting and start being texture. */}
                    <span className="flex h-1.5 items-center gap-[3px]">
                      {(entriesByDay.get(d) ?? []).slice(0, 5).map((entry, i) => (
                        <span
                          key={i}
                          className={`size-[5px] rounded-full ${entryDotClass(entry, selected)}`}
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
              {/* Commitments and plan items in one list and one shape. What
                  separates them is surface, not layout: a commitment is filled
                  and grey-dotted because you put it there yourself. */}
              {dayEntries.length > 0 && (
                <ul className="flex flex-col gap-2">
                  {dayEntries.map((entry) =>
                    entry.entry_type === 'calendar_event' && entry.calendar_event ? (
                      <CommitmentRow
                        key={`cal-${entry.calendar_event.id}`}
                        event={entry.calendar_event}
                        at={entry.starts_at}
                        timezone={trip.timezone}
                      />
                    ) : entry.plan_item ? (
                      <PlanItemRow
                        key={`item-${entry.plan_item.id}`}
                        item={entry.plan_item}
                        at={entry.starts_at}
                        timezone={trip.timezone}
                        onSelect={setOpenItem}
                      />
                    ) : null,
                  )}
                </ul>
              )}
            </div>
          </>
        )}

        {/* Gate 1 lives below the trip you came to see, not on top of it, and
            out of All trips: a detection is a claim that a trip exists, not a
            trip. It gets no notification, so the tab count is what surfaces it. */}
        {detected.length > 0 && (
          <>
            <p className="mt-2 border-t border-border-soft pt-4 text-section font-semibold uppercase text-muted-soft">
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

        {/* Visible, not accordioned: these are navigation, and an accordion
            over navigation costs a scroll and an expand before you can even
            see where you might go. Only the archive collapses, and it
            collapses into a button that says how many and where they went. */}
        {trips.isSuccess && otherTrips.length > 0 && (
          <>
            <p className="mt-2 border-t border-border-soft pt-4 text-section font-semibold uppercase text-muted-soft">
              Other trips
            </p>
            {otherTrips.map((t) => (
              <TripListRow
                key={t.id}
                trip={t}
                onSelect={onSelectTrip}
                className="border border-border"
              />
            ))}
          </>
        )}

        {trips.isSuccess && pastTrips.length > 0 && (
          <button
            onClick={openTripsSheet}
            className="flex w-full items-center justify-between gap-3 rounded-panel border border-dashed border-border-faint px-4 py-3.5 text-body-sm font-semibold text-muted hover:bg-card focus-visible:outline-2 focus-visible:outline-primary"
          >
            {pastTrips.length} past {pastTrips.length === 1 ? 'trip' : 'trips'}
            <span className="text-label font-normal text-muted-soft">Archive</span>
          </button>
        )}
      </div>

      <TripsSheet
        open={sheet === 'trips'}
        onClose={() =>
          void navigate({ search: (prev) => ({ ...prev, sheet: undefined }) })
        }
        trips={listedTrips}
        selectedId={trip?.id}
        onSelect={onSelectTrip}
        onAddTrip={() =>
          void navigate({ search: (prev) => ({ ...prev, sheet: 'new' }) })
        }
      />

      <AddTripSheet
        open={sheet === 'new'}
        onClose={() =>
          void navigate({ search: (prev) => ({ ...prev, sheet: undefined }) })
        }
        // Land on the new trip's own screen: a trip you just added has no plan
        // and no timeline, so its detail screen is the only one with anything
        // to say about it.
        onCreated={(t) => onSelectTrip(t.id)}
      />

      <PlanItemSheet
        item={openPlanItem}
        tripId={trip?.id ?? ''}
        timezone={trip?.timezone ?? 'UTC'}
        // The focus trip is never a past one, but the sheet must not depend on
        // that being true somewhere else.
        tripIsPast={trip !== undefined && isPast(trip)}
        onClose={() => setOpenItem(undefined)}
        onShowProvenance={setProvenanceItem}
      />

      <ProvenanceSheet
        itemId={provenanceItem}
        onClose={() => setProvenanceItem(undefined)}
      />
    </>
  )
}
