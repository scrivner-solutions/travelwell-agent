import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { sourcesQueryOptions, tripsQueryOptions } from '@/api/queries'
import { TripScreen } from '@/features/trip/TripScreen'

/**
 * URL contract: /trip?trip=<uuid>&day=YYYY-MM-DD&sheet=new|trips|archive. All
 * are search params so a notification can deep-link straight to the trip and
 * day it is talking about, and sheets restore exactly (same rule as
 * /today?sheet=). `trips` lists every trip, `archive` only the past ones.
 * An unknown trip id degrades to the default focus trip rather than erroring.
 */
export const Route = createFileRoute('/_shell/trip')({
  validateSearch: z.object({
    trip: z.string().uuid().optional().catch(undefined),
    day: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/)
      .optional(),
    sheet: z.enum(['new', 'trips', 'archive']).optional(),
  }),
  loader: ({ context }) => {
    void context.queryClient.prefetchQuery(tripsQueryOptions())
    // The facts card's trust strip. Cheap, cached, and shared with /profile.
    void context.queryClient.prefetchQuery(sourcesQueryOptions())
  },
  component: TripScreen,
})
