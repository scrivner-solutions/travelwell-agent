import { useQuery } from '@tanstack/react-query'
import { getRouteApi } from '@tanstack/react-router'
import { Card } from '@/components/ui/Card'
import { Sheet } from '@/components/ui/Sheet'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { LoadingState, EmptyState, DegradedState } from '@/components/ui/ScreenState'
import { formatInTimeZone } from 'date-fns-tz'
import {
  timelineQueryOptions,
  tripsQueryOptions,
  todayQueryOptions,
  type PlanItem,
} from '@/api/queries'
import { focusTrip, stateInk } from '@/lib/trips'
import { formatDateRange, formatTripTime, formatTripTimeRange } from '@/lib/time'

const route = getRouteApi('/_shell/today')

/**
 * A plan item rendered inside its wellness window card (design: the opening,
 * then the thing that fits it). Dashed border = still a suggestion.
 */
function WindowItem({ item }: { item: PlanItem }) {
  const distance = item.selected_option?.distance_minutes
  return (
    <div
      className={`mt-3 rounded-panel border p-3 ${
        item.status === 'suggested'
          ? 'border-dashed border-state-suggested'
          : 'border-border-soft'
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-body font-semibold">{item.title}</p>
        {distance !== undefined && (
          <span className="flex-none rounded-full bg-state-neutral-soft px-2.5 py-0.5 text-caption font-medium text-ink">
            {distance === 0 ? 'In the hotel' : `${distance} min walk`}
          </span>
        )}
      </div>
      {item.selected_option?.display_summary !== undefined && (
        <p className="mt-0.5 text-caption text-muted">
          {item.selected_option.display_summary}
        </p>
      )}
      {(item.selected_option?.reason !== undefined ||
        (item.why !== undefined && item.why.length > 0)) && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {item.selected_option?.reason !== undefined && (
            <span className="rounded-full bg-state-working-soft px-2.5 py-0.5 text-caption text-state-working">
              {item.selected_option.reason}
            </span>
          )}
          {item.why?.map((pref) => (
            <span
              key={pref}
              className="rounded-full bg-state-working-soft px-2.5 py-0.5 text-caption text-state-working"
            >
              {pref}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export function TodayScreen() {
  const { sheet } = route.useSearch()
  const navigate = route.useNavigate()
  const trips = useQuery(tripsQueryOptions())
  const trip = trips.data ? focusTrip(trips.data) : undefined
  const today = useQuery({ ...todayQueryOptions(trip?.id ?? ''), enabled: trip !== undefined })
  // Existing commitments for the trip-local today, shown above the plan
  // (design: the muted "8:00 Conference" rows).
  const localToday = trip ? formatInTimeZone(new Date(), trip.timezone, 'yyyy-MM-dd') : ''
  const timeline = useQuery({
    ...timelineQueryOptions(trip?.id ?? '', localToday),
    enabled: trip !== undefined,
  })
  const commitments =
    timeline.data?.filter((entry) => entry.entry_type === 'calendar_event') ?? []

  // Split today's plan: items filling the window nest inside its card
  // (design: the opening, then what fits it); the rest stand alone.
  const win = today.data?.window
  const windowItems =
    win !== undefined && win !== null
      ? (today.data?.next_up.filter((item) => item.window_id === win.id) ?? [])
      : []
  const standaloneItems =
    today.data?.next_up.filter(
      (item) => !windowItems.some((w) => w.id === item.id),
    ) ?? []

  const closeSheet = () => void navigate({ search: {} })

  return (
    <>
      {/* Design order: eyebrow (CHICAGO · DAY 2 OF 4) sits above the title. */}
      <header className="mb-4">
        {trip && (
          <p className="text-caption font-semibold uppercase tracking-wide text-muted">
            {today.data?.day_label ?? trip.destination_name}
          </p>
        )}
        <div className="flex items-baseline justify-between">
          <h1 className="font-display text-display font-medium">Today</h1>
          <button
            onClick={() => void navigate({ search: { sheet: 'trips' } })}
            className="text-body-sm font-semibold text-primary focus-visible:outline-2 focus-visible:outline-primary"
          >
            Trips
          </button>
        </div>
      </header>

      {trips.isPending && <LoadingState label="Loading your trips" />}
      {trips.isError && (
        <DegradedState
          title="TravelWell is unreachable"
          detail="Your plan is safe on the server; nothing shown here is made up. Check your connection and retry."
          onRetry={() => void trips.refetch()}
        />
      )}
      {trips.isSuccess && !trip && (
        <EmptyState
          title="No trips yet"
          detail="Connect your calendar and TravelWell will spot trips for you, or add one yourself from the Trip tab."
        />
      )}

      {trip && (
        <section aria-label={trip.destination_name}>
          <p className="mb-4 flex items-center gap-2 text-body-sm text-muted">
            {today.data ? (
              <>
                <span
                  aria-hidden
                  className={`inline-block size-[7px] rounded-full bg-current ${stateInk[trip.state] ?? 'text-state-neutral'}`}
                />
                <span className={`font-semibold ${stateInk[trip.state] ?? 'text-state-neutral'}`}>
                  {today.data.state_word}
                </span>
                {today.data.state_detail !== undefined && (
                  <span>· {today.data.state_detail}</span>
                )}
              </>
            ) : (
              trip.state_line
            )}
          </p>

          {commitments.length > 0 && (
            <ul className="mb-4 flex flex-col gap-1">
              {commitments.map(
                (entry) =>
                  entry.calendar_event && (
                    <li
                      key={entry.calendar_event.id}
                      className="flex items-center gap-3 px-1"
                    >
                      <span className="w-16 flex-none text-right text-caption text-muted">
                        {formatTripTime(entry.starts_at, trip.timezone)}
                      </span>
                      <span
                        aria-hidden
                        className="size-[7px] flex-none rounded-full border border-border"
                      />
                      <span className="text-body-sm text-muted">
                        {entry.calendar_event.title}
                      </span>
                    </li>
                  ),
              )}
            </ul>
          )}

          {today.isPending && <LoadingState label="Loading today's plan" />}
          {today.isError && (
            <DegradedState
              title="Can't load today's plan"
              onRetry={() => void today.refetch()}
            />
          )}
          {today.isSuccess && (
            <div className="flex flex-col gap-3">
              {/* Items that fill today's window render inside its card. */}
              {today.data.window && (
                <Card>
                  {/* Design: start time only, in blue; the duration lives in
                      the headline ("90 minutes free"). */}
                  <p className="text-label font-semibold uppercase tracking-wide">
                    <span className="text-state-working">
                      {formatTripTime(today.data.window.starts_at, today.data.timezone)}
                    </span>
                    <span className="text-muted"> · Wellness window</span>
                  </p>
                  <p className="mt-1 font-display text-display-sm">{today.data.window.label}</p>
                  {today.data.window.gap_explanation !== undefined && (
                    <p className="mt-1 text-body-sm text-muted">
                      {today.data.window.gap_explanation}
                    </p>
                  )}
                  {windowItems.map((item) => (
                    <WindowItem key={item.id} item={item} />
                  ))}
                  {today.data.window.bounds.length > 0 && (
                    <ul className="mt-3 flex flex-col gap-1 border-t border-border-soft pt-3">
                      {today.data.window.bounds.map((bound) => (
                        <li
                          key={`${bound.tag}-${bound.title}`}
                          className="flex items-baseline gap-2 text-caption"
                        >
                          <span className="font-mono text-label font-semibold text-muted">
                            {bound.tag}
                          </span>
                          <span className="text-ink">{bound.title}</span>
                          {bound.detail !== undefined && (
                            <span className="text-muted">{bound.detail}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
              )}
              {today.data.next_up.length === 0 && (
                <EmptyState
                  title="Nothing planned yet"
                  detail="When the agent proposes a plan for this trip it appears here first."
                />
              )}
              {standaloneItems.map((item) => (
                <Card
                  key={item.id}
                  className={
                    item.status === 'suggested'
                      ? 'border-dashed border-state-suggested'
                      : ''
                  }
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-body font-semibold">{item.title}</p>
                      {item.selected_option?.display_summary !== undefined && (
                        <p className="text-caption text-muted">
                          {item.selected_option.display_summary}
                        </p>
                      )}
                      {item.starts_at !== undefined && item.ends_at !== undefined && (
                        <p className="text-caption text-muted">
                          {formatTripTimeRange(item.starts_at, item.ends_at, today.data.timezone)}
                          {item.selected_option?.distance_minutes !== undefined &&
                            ` · ${
                              item.selected_option.distance_minutes === 0
                                ? 'In the hotel'
                                : `${item.selected_option.distance_minutes} min walk`
                            }`}
                        </p>
                      )}
                    </div>
                    <StatusBadge status={item.status} />
                  </div>
                  {item.selected_option?.reason !== undefined && (
                    <p className="mt-2 inline-flex rounded-full bg-state-working-soft px-2.5 py-0.5 text-caption text-state-working">
                      {item.selected_option.reason}
                    </p>
                  )}
                </Card>
              ))}
            </div>
          )}
        </section>
      )}

      <Sheet open={sheet === 'trips'} onClose={closeSheet} title="Your trips">
        {trips.isSuccess && trips.data.length === 0 && (
          <p className="text-body-sm text-muted">No trips yet.</p>
        )}
        <ul className="flex flex-col gap-2">
          {trips.data?.map((t) => (
            <li key={t.id} className="rounded-panel border border-border-soft p-3">
              <p className="text-body font-semibold">{t.destination_name}</p>
              <p className="text-caption text-muted">
                {formatDateRange(t.starts_on, t.ends_on)}
                {t.needs_you_count > 0 && ` · ${t.needs_you_count} need you`}
              </p>
            </li>
          ))}
        </ul>
      </Sheet>
    </>
  )
}
