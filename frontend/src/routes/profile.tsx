import { createFileRoute, redirect } from '@tanstack/react-router'
import { z } from 'zod'
import { ApiError } from '@/api/client'
import {
  meQueryOptions,
  preferencesQueryOptions,
  sourcesQueryOptions,
  tripsQueryOptions,
} from '@/api/queries'
import { ProfileScreen } from '@/features/profile/ProfileScreen'

/**
 * Full-screen route outside the _shell layout: the design's profile sheet
 * covers the tab bar entirely. Same auth policy as _shell - redirect only on
 * a definitive 401.
 */
export const Route = createFileRoute('/profile')({
  /**
   * URL contract: /profile?connected=<kind> | ?connect_error=<code>. The OAuth
   * callback has no page of its own, so it redirects here with the outcome.
   * Both are plain strings rather than enums: the connectable kinds are served
   * by /me/sources precisely so the client keeps no second copy of that list.
   */
  validateSearch: z.object({
    connected: z.string().optional().catch(undefined),
    connect_error: z.string().optional().catch(undefined),
  }),
  beforeLoad: async ({ context }) => {
    try {
      await context.queryClient.ensureQueryData(meQueryOptions())
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        throw redirect({ to: '/sign-in' })
      }
    }
  },
  loader: ({ context }) => {
    void context.queryClient.prefetchQuery(preferencesQueryOptions())
    void context.queryClient.prefetchQuery(sourcesQueryOptions())
    void context.queryClient.prefetchQuery(tripsQueryOptions())
  },
  component: ProfileScreen,
})
