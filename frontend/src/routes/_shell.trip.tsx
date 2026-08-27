import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { tripsQueryOptions } from '@/api/queries'
import { TripScreen } from '@/features/trip/TripScreen'

/**
 * URL contract: /trip?day=YYYY-MM-DD. The selected day is a search param so
 * a notification can deep-link straight to the day it is talking about.
 */
export const Route = createFileRoute('/_shell/trip')({
  validateSearch: z.object({
    day: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/)
      .optional(),
  }),
  loader: ({ context }) => {
    void context.queryClient.prefetchQuery(tripsQueryOptions())
  },
  component: TripScreen,
})
