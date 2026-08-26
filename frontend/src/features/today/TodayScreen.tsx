import { useQuery } from '@tanstack/react-query'
import { getRouteApi } from '@tanstack/react-router'
import { Card } from '@/components/ui/Card'
import { Sheet } from '@/components/ui/Sheet'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { LoadingState, EmptyState, DegradedState } from '@/components/ui/ScreenState'
import { tripsQueryOptions, todayQueryOptions, type Trip } from '@/api/queries'
import { formatTripTimeRange } from '@/lib/time'

const route = getRouteApi('/_shell/today')

// The tab surfaces the trip the agent is currently working: active beats
// preparing beats upcoming; the server orders /trips by start date.
const focusOrder: readonly Trip['state'][] = ['active', 'preparing', 'upcoming', 'confirmed']

function focusTrip(trips: Trip[]): Trip | undefined {
  for (const state of focusOrder) {
    const match = trips.find((trip) => trip.state === state)
    if (match) return match
  }
  return undefined
}

export function TodayScreen() {
  const { sheet } = route.useSearch()
  const navigate = route.useNavigate()
  const trips = useQuery(tripsQueryOptions())
  const trip = trips.data ? focusTrip(trips.data) : undefined
  const today = useQuery({ ...todayQueryOptions(trip?.id ?? ''), enabled: trip !== undefined })

  const closeSheet = () => void navigate({ search: {} })

  return (
    <>
      <header className="mb-4 flex items-baseline justify-between">
        <h1 className="font-display text-display font-medium">Today</h1>
        <button
          onClick={() => void navigate({ search: { sheet: 'trips' } })}
          className="text-body-sm font-semibold text-primary focus-visible:outline-2 focus-visible:outline-primary"
        >
          Trips
        </button>
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
          <p className="text-caption font-semibold uppercase tracking-wide text-muted">
            {today.data?.day_label ?? trip.destination_name}
          </p>
          {trip.state_line !== undefined && (
            <p className="mb-4 text-body-sm text-muted">{trip.state_line}</p>
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
              {today.data.window && (
                <Card>
                  <p className="text-label font-semibold uppercase tracking-wide text-muted">
                    Wellness window
                  </p>
                  <p className="mt-1 text-body font-semibold">
                    {formatTripTimeRange(
                      today.data.window.starts_at,
                      today.data.window.ends_at,
                      today.data.timezone,
                    )}
                  </p>
                  {today.data.window.bounds.length > 0 && (
                    <p className="mt-1 text-caption text-muted">
                      {today.data.window.bounds.join(' · ')}
                    </p>
                  )}
                </Card>
              )}
              {today.data.next_up.length === 0 && (
                <EmptyState
                  title="Nothing planned yet"
                  detail="When the agent proposes a plan for this trip it appears here first."
                />
              )}
              {today.data.next_up.map((item) => (
                <Card key={item.id}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-body font-semibold">{item.title}</p>
                      {item.starts_at !== undefined && item.ends_at !== undefined && (
                        <p className="text-caption text-muted">
                          {formatTripTimeRange(item.starts_at, item.ends_at, today.data.timezone)}
                        </p>
                      )}
                    </div>
                    <StatusBadge status={item.status} />
                  </div>
                  {item.why !== undefined && item.why.length > 0 && (
                    <p className="mt-2 text-caption text-muted">{item.why.join(' · ')}</p>
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
                {t.starts_on} to {t.ends_on}
                {t.needs_you_count > 0 && ` · ${t.needs_you_count} need you`}
              </p>
            </li>
          ))}
        </ul>
      </Sheet>
    </>
  )
}
