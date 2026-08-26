import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { tripsQueryOptions } from '@/api/queries'
import { TodayScreen } from '@/features/today/TodayScreen'

/**
 * URL contract: /today?sheet=trips. Sheets are search params so a
 * notification deep link can restore screen + sheet state exactly.
 */
export const Route = createFileRoute('/_shell/today')({
  validateSearch: z.object({
    sheet: z.enum(['trips']).optional(),
  }),
  loader: ({ context }) => {
    void context.queryClient.prefetchQuery(tripsQueryOptions())
  },
  component: TodayScreen,
})
