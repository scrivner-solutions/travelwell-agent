import type { ExploreAnchor, ExplorePlace, ExploreRoute } from '@/api/queries'

/* The day read as a walk rather than as a list of times. It stays on screen
 * with nothing planned, because "nothing planned today" is the answer to the
 * question an empty map otherwise leaves open. */
export function RouteStrip({ route }: { route: ExploreRoute }) {
  const [start, ...rest] = route.stops
  return (
    <div className="flex max-w-full flex-wrap items-center gap-1.5 rounded-panel border border-border bg-card/95 px-3 py-2">
      {start === undefined ? (
        <span className="text-label font-medium text-muted">Nothing planned today</span>
      ) : (
        <>
          <span className="text-label font-medium text-muted">{start.name}</span>
          {rest.map((stop, index) => (
            <span key={`${stop.name}-${index}`} className="flex items-center gap-1.5">
              {stop.walk_minutes != null && (
                <span className="text-[11px] font-medium leading-none text-muted-soft">
                  {stop.walk_minutes} min
                </span>
              )}
              <span aria-hidden className="text-muted-faint">
                &rarr;
              </span>
              <span className="text-label font-semibold text-agent">
                {stop.name}
              </span>
            </span>
          ))}
          {route.total_minutes != null && (
            <span className="w-full border-t border-surface pt-1.5 text-[11.5px] font-medium leading-none text-muted-soft">
              {route.total_minutes} min walking
            </span>
          )}
        </>
      )}
    </div>
  )
}

/** What adding the selected place to the day would cost, priced from the
 *  anchor. Periwinkle like the spur it labels: a proposal, not a plan. */
export function SpurPill({ place, anchor }: { place: ExplorePlace; anchor: ExploreAnchor }) {
  return (
    <p className="rounded-full border border-agent-soft bg-state-suggested-soft px-3 py-1.5 text-label font-medium text-agent">
      Add {place.name}: +{place.walk_minutes} min from {anchor.name}
    </p>
  )
}
