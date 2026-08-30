import { createFileRoute } from '@tanstack/react-router'
import {
  planQueryOptions,
  preferencesQueryOptions,
  sourcesQueryOptions,
  tripQueryOptions,
  tripsQueryOptions,
} from '@/api/queries'
import { TripDetailScreen } from '@/features/trip/TripDetailScreen'

/**
 * URL contract: /trip/<uuid>. A path param, not a search param, because this
 * is a place rather than a setting - it is what a notification links to and
 * what a shared link means.
 *
 * `trip_` opts out of nesting under /trip: the detail screen replaces the trip
 * tab's working surface rather than rendering inside it, while still living in
 * the tab shell, so the tab bar stays and Trip stays lit.
 */
export const Route = createFileRoute('/_shell/trip_/$tripId')({
  loader: ({ context, params }) => {
    // All warmed, none awaited: the screen designs its own pending and
    // degraded states, and blocking navigation on five requests would trade a
    // loading card for a frozen tab bar.
    void context.queryClient.prefetchQuery(tripQueryOptions(params.tripId))
    void context.queryClient.prefetchQuery(planQueryOptions(params.tripId))
    void context.queryClient.prefetchQuery(tripsQueryOptions())
    void context.queryClient.prefetchQuery(sourcesQueryOptions())
    void context.queryClient.prefetchQuery(preferencesQueryOptions())
  },
  component: TripDetailScreen,
})
