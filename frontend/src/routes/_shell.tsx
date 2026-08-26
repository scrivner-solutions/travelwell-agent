import { createFileRoute, Outlet, redirect } from '@tanstack/react-router'
import { AppShell } from '@/app/AppShell'
import { ApiError } from '@/api/client'
import { meQueryOptions } from '@/api/queries'

/**
 * Layout for the four tab destinations. The auth guard redirects only on a
 * definitive 401; an unreachable backend falls through so screens can show
 * their honest degraded state instead of bouncing the user to sign-in.
 */
export const Route = createFileRoute('/_shell')({
  beforeLoad: async ({ context }) => {
    try {
      await context.queryClient.ensureQueryData(meQueryOptions())
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        throw redirect({ to: '/sign-in' })
      }
    }
  },
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
})
