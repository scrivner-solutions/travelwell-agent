import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { ExploreScreen } from '@/features/explore/ExploreScreen'

/**
 * URL contract: /explore?window=now|next2h|evening&walk=5|10|20&cap=true
 * &amenities=true&sheet=filters. Filters live here rather than in state so a
 * narrowed list survives opening a place and coming back, and so the back
 * button undoes a filter the way it undoes a page. Defaults are left out of
 * the URL, so a plain /explore is the default view.
 */
export const Route = createFileRoute('/_shell/explore')({
  validateSearch: z.object({
    window: z.enum(['now', 'next2h', 'evening']).optional().catch(undefined),
    walk: z.union([z.literal(5), z.literal(10), z.literal(20)]).optional().catch(undefined),
    cap: z.literal(true).optional().catch(undefined),
    amenities: z.literal(true).optional().catch(undefined),
    sheet: z.literal('filters').optional().catch(undefined),
  }),
  component: ExploreScreen,
})
