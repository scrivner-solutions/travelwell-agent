import { useQuery } from '@tanstack/react-query'
import { Card } from '@/components/ui/Card'
import { LoadingState, EmptyState, DegradedState } from '@/components/ui/ScreenState'
import { tripsQueryOptions } from '@/api/queries'

// Phase 1 grows this into the full timeline (Existing / Suggested / Confirmed
// rows, detection confirm, manual create). Phase 0 renders the real trip list
// so the tab is wired end-to-end through the contract from day one.
export function TripScreen() {
  const trips = useQuery(tripsQueryOptions())

  return (
    <>
      <header className="mb-4">
        <h1 className="font-display text-display font-medium">Trip</h1>
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
        />
      )}
      <div className="flex flex-col gap-3">
        {trips.data?.map((trip) => (
          <Card key={trip.id}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-body font-semibold">{trip.destination_name}</p>
                <p className="text-caption text-muted">
                  {trip.starts_on} to {trip.ends_on} · {trip.timezone}
                </p>
              </div>
              <span className="text-label font-semibold uppercase tracking-wide text-muted">
                {trip.state.replace('_', ' ')}
              </span>
            </div>
            {trip.needs_you_count > 0 && (
              <p className="mt-2 text-caption font-semibold text-state-attention">
                {trip.needs_you_count} {trip.needs_you_count === 1 ? 'item needs' : 'items need'} you
              </p>
            )}
          </Card>
        ))}
      </div>
    </>
  )
}
