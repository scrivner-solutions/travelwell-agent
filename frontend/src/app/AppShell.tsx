import type { ReactNode } from 'react'
import { Link } from '@tanstack/react-router'
import { Sun, CalendarDays, Compass, Sparkles } from 'lucide-react'

const tabs = [
  { to: '/today', label: 'Today', Icon: Sun },
  { to: '/trip', label: 'Trip', Icon: CalendarDays },
  { to: '/explore', label: 'Explore', Icon: Compass },
  { to: '/agent', label: 'Agent', Icon: Sparkles },
] as const

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-lg flex-col">
      <main className="flex-1 px-4 pb-24 pt-[max(1rem,env(safe-area-inset-top))]">
        {children}
      </main>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 border-t border-border bg-card pb-[env(safe-area-inset-bottom)]"
      >
        <div className="mx-auto flex w-full max-w-lg items-stretch justify-around">
          {tabs.map(({ to, label, Icon }) => (
            <Link
              key={to}
              to={to}
              className="flex flex-1 flex-col items-center gap-0.5 py-2.5 text-label font-semibold text-muted-soft focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
              activeProps={{ className: 'text-primary', 'aria-current': 'page' }}
            >
              <Icon className="size-5" aria-hidden />
              {label}
            </Link>
          ))}
        </div>
      </nav>
    </div>
  )
}
