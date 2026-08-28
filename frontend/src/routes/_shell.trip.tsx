import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { tripsQueryOptions } from '@/api/queries'
import { TripScreen } from '@/features/trip/TripScreen'

/**
 * URL contract: /trip?trip=<uuid>&day=YYYY-MM-DD&sheet=new. All are search
 * params so a notification can deep-link straight to the trip and day it is
 * talking about, and sheets restore exactly (same rule as /today?sheet=).
 * An unknown trip id degrades to the default focus trip rather than erroring.
 */
export const Route = createFileRoute('/_shell/trip')({
  validateSearch: z.object({
    trip: z.string().uuid().optional().catch(undefined),
    day: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/)
      .optional(),
    sheet: z.enum(['new']).optional(),
  }),
  loader: ({ context }) => {
    void context.queryClient.prefetchQuery(tripsQueryOptions())
  },
  component: TripScreen,
})
