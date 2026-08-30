import type { ReactNode, SVGProps } from 'react'
import { Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { tripsQueryOptions } from '@/api/queries'
import { InstallPrompt } from '@/components/ui/InstallPrompt'

/**
 * Tab icons traced from the design prototype's tab bar (exact SVG paths, not
 * icon-library lookalikes). currentColor lets the active state tint icon and
 * label together.
 */
const iconProps: SVGProps<SVGSVGElement> = {
  width: 23,
  height: 23,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
}

function TodayIcon() {
  return (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15 14" />
    </svg>
  )
}

function TripIcon() {
  return (
    <svg {...iconProps}>
      <rect x="3" y="7" width="18" height="13" rx="2.5" />
      <path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
    </svg>
  )
}

function ExploreIcon() {
  return (
    <svg {...iconProps}>
      <circle cx="12" cy="12" r="9" />
      <polygon points="15.5 8.5 10.5 10.5 8.5 15.5 13.5 13.5" />
    </svg>
  )
}

function AgentIcon() {
  return (
    <svg {...iconProps}>
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  )
}

function MicIcon() {
  return (
    <svg {...iconProps} width={25} height={25} strokeWidth={1.9}>
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  )
}

const leftTabs = [
  { to: '/today', label: 'Today', Icon: TodayIcon },
  { to: '/trip', label: 'Trip', Icon: TripIcon },
] as const

const rightTabs = [
  { to: '/explore', label: 'Explore', Icon: ExploreIcon },
  { to: '/agent', label: 'Agent', Icon: AgentIcon },
] as const

function Tab({
  to,
  label,
  Icon,
  count = 0,
}: {
  to: string
  label: string
  Icon: () => ReactNode
  count?: number
}) {
  return (
    <Link
      to={to}
      // 10.5px label is the prototype's nav size; smaller than any type token
      className="flex flex-1 flex-col items-center gap-[5px] pb-2.5 pt-2 text-[10.5px] font-semibold leading-none text-muted-soft focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
      activeProps={{ className: 'text-primary', 'aria-current': 'page' }}
    >
      <span className="relative">
        <Icon />
        {count > 0 && (
          <span
            aria-hidden
            className="absolute -right-2 -top-1 grid min-w-[16px] place-items-center rounded-full bg-state-attention px-1 text-[10px] font-semibold leading-[16px] text-white"
          >
            {count}
          </span>
        )}
      </span>
      {label}
      {count > 0 && <span className="sr-only">, {count} need you</span>}
    </Link>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  // Server-derived, one term per gate (confirm the trip, decide a suggestion,
  // approve an action). Only the last two are notified, so this badge is the
  // whole discovery path for a detection sitting below the fold.
  const trips = useQuery(tripsQueryOptions())
  const needsYou = (trips.data ?? []).reduce((n, t) => n + t.needs_you_count, 0)

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-lg flex-col">
      <main className="flex-1 px-4 pb-24 pt-[max(1rem,env(safe-area-inset-top))]">
        <InstallPrompt className="mb-4" />
        {children}
      </main>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 border-t border-border bg-card pb-[env(safe-area-inset-bottom)]"
      >
        <div className="mx-auto flex w-full max-w-lg items-start px-2 pt-1">
          {leftTabs.map((tab) => (
            <Tab
              key={tab.to}
              {...tab}
              count={tab.to === '/trip' ? needsYou : 0}
            />
          ))}
          {/* Center mic FAB (design: the agent's voice entry point). Voice
              capture ships in Phase 5; until then it opens the Agent tab. */}
          <div className="flex flex-1 justify-center">
            <Link
              to="/agent"
              aria-label="Talk to TravelWell"
              className="-mt-6 grid size-[62px] place-items-center rounded-full border-4 border-card bg-primary text-white shadow-[0_12px_24px_-10px_rgba(24,95,165,0.5)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              <MicIcon />
            </Link>
          </div>
          {rightTabs.map((tab) => (
            <Tab key={tab.to} {...tab} />
          ))}
        </div>
      </nav>
    </div>
  )
}
