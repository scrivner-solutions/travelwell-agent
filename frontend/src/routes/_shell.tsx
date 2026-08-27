import { createFileRoute, Outlet } from '@tanstack/react-router'
import { AppShell } from '@/app/AppShell'
import { meQueryOptions } from '@/api/queries'

/**
 * Layout for the four tab destinations. beforeLoad only warms /me; the
 * queryClient auth handler is the single owner of the 401 -> sign-in
 * redirect, wherever the 401 surfaces.
 */
export const Route = createFileRoute('/_shell')({
  beforeLoad: async ({ context }) => {
    try {
      await context.queryClient.ensureQueryData(meQueryOptions())
    } catch {
      // 401: the auth handler has already started the sign-in navigation;
      // swallowing avoids flashing the router error screen while it lands.
      // Anything else (backend unreachable): fall through so screens show
      // their honest degraded state instead of bouncing to sign-in.
    }
  },
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
})
