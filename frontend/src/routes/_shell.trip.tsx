import { createFileRoute } from '@tanstack/react-router'
import { tripsQueryOptions } from '@/api/queries'
import { TripScreen } from '@/features/trip/TripScreen'

export const Route = createFileRoute('/_shell/trip')({
  loader: ({ context }) => {
    void context.queryClient.prefetchQuery(tripsQueryOptions())
  },
  component: TripScreen,
})
