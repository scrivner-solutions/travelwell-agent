import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getRouteApi } from '@tanstack/react-router'
import { formatInTimeZone } from 'date-fns-tz'
import { Button } from '@/components/ui/Button'
import { Card, CardButton } from '@/components/ui/Card'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { LoadingState, EmptyState, DegradedState } from '@/components/ui/ScreenState'
import { ProfileButton } from '@/components/ui/ProfileButton'
import {
  confirmTrip,
  timelineQueryOptions,
  tripsQueryOptions,
  type TimelineEntry,
  type Trip,
} from '@/api/queries'
import { ApiError } from '@/api/client'
import {
  calendarSpan,
  evidenceTag,
  focusTrip,
  sourceLabel,
  stateInk,
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

/** "We found an upcoming trip" card: evidence rows + confirm (409-aware). */
function DetectionCard({ trip }: { trip: Trip }) {
  const queryClient = useQueryClient()
  const confirm = useMutation({
    mutationFn: () => confirmTrip(trip.id, trip.updated_at),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['trips'] }),
  })
  const conflicted =
    confirm.error instanceof ApiError && confirm.error.status === 409

  return (
    <Card>
      <p className="text-label font-semibold uppercase tracking-wide text-muted">
        We found an upcoming trip
      </p>
      <p className="mt-1 font-display text-display-sm">{trip.destination_name}</p>
      <p className="text-caption text-muted">
        {formatDateRange(trip.starts_on, trip.ends_on)}
      </p>
      {trip.evidence !== undefined && trip.evidence.length > 0 && (
        <ul className="mt-3 flex flex-col gap-2 border-t border-border-soft pt-3">
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
      )}
      {conflicted ? (
        <p className="mt-3 text-caption font-semibold text-state-attention">
          This trip changed on the server. The list below has been refreshed; try again.
        </p>
      ) : (
        confirm.isError && (
          <p className="mt-3 text-caption font-semibold text-state-attention">
            Could not confirm the trip. Check your connection and retry.
          </p>
        )
      )}
      <button
        onClick={() => confirm.mutate()}
        disabled={confirm.isPending}
        className="mt-3 h-11 w-full rounded-panel bg-primary text-body-sm font-semibold text-white disabled:opacity-60"
      >
        {confirm.isPending ? 'Confirming…' : 'Use this trip'}
      </button>
    </Card>
  )
}

export function TripScreen() {
  const { day, trip: tripId, sheet } = route.useSearch()
  const navigate = route.useNavigate()
  const trips = useQuery(tripsQueryOptions())
  // ?trip= (a tapped card or a deep link) wins; otherwise the agent's focus.
  const trip = trips.data
    ? (trips.data.find((t) => t.id === tripId) ?? focusTrip(trips.data))
    : undefined
  const detected = trips.data?.filter((t) => t.state === 'detected') ?? []

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
        <p className="flex items-center gap-2 text-caption font-semibold uppercase tracking-wide text-muted">
          {trip && (
            <span
              aria-hidden
              className={`inline-block size-[7px] rounded-full bg-current ${stateInk[trip.state] ?? 'text-state-neutral'}`}
            />
          )}
          {trip
            ? `${formatDateRange(trip.starts_on, trip.ends_on)}${trip.label !== undefined ? ` · ${trip.label}` : ''}`
            : 'Trip'}
        </p>
        <div className="flex items-center justify-between">
          <h1 className="font-display text-display font-medium">
            {trip?.destination_name.split(',')[0] ?? 'Trip'}
          </h1>
          <ProfileButton />
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
        {detected.map((t) => (
          <DetectionCard key={t.id} trip={t} />
        ))}

        {trip && (
          <>
            {trip.evidence !== undefined && trip.evidence.length > 0 && (
              <Card>
                <ul className="flex flex-col gap-2.5">
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
              </Card>
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
          </>
        )}

        {trips.isSuccess && trips.data.length > 0 && (
          <>
            <p className="mt-2 text-label font-semibold uppercase tracking-wide text-muted">
              All trips
            </p>
            {trips.data.map((t) => (
              <CardButton
                key={t.id}
                aria-current={t.id === trip?.id || undefined}
                className={t.id === trip?.id ? 'border-ink' : ''}
                // day resets: the old selection belongs to the previous trip's range
                onClick={() =>
                  void navigate({ search: { trip: t.id, day: undefined } })
                }
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-body font-semibold">{t.destination_name}</p>
                    <p className="text-caption text-muted">
                      {formatDateRange(t.starts_on, t.ends_on)}
                      {t.label !== undefined && ` · ${t.label}`}
                    </p>
                  </div>
                  <span
                    className={`flex items-baseline gap-1.5 text-label font-semibold uppercase tracking-wide ${stateInk[t.state] ?? 'text-state-neutral'}`}
                  >
                    <span aria-hidden className="size-[6px] flex-none self-center rounded-full bg-current" />
                    {t.state.replace('_', ' ')}
                  </span>
                </div>
                {t.needs_you_count > 0 && (
                  <p className="mt-2 text-caption font-semibold text-state-attention">
                    {t.needs_you_count} {t.needs_you_count === 1 ? 'item needs' : 'items need'} you
                  </p>
                )}
              </CardButton>
            ))}
            <button
              onClick={() =>
                void navigate({ search: (prev) => ({ ...prev, sheet: 'new' }) })
              }
              className="h-[50px] w-full rounded-panel border border-dashed border-border text-body-sm font-semibold text-muted hover:bg-card"
            >
              Add a trip manually
            </button>
          </>
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
