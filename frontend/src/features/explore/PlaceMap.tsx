import { useRef, useState, type ReactNode } from 'react'
import { Maximize2 } from 'lucide-react'
import type { Basemap, ExploreAnchor, ExplorePlace, ExploreRoute } from '@/api/queries'
import { ExpandedMap } from './ExpandedMap'
import { MapCanvas } from './MapCanvas'
import { spurTarget } from './spur'
import { RouteStrip, SpurPill } from './RouteStrip'
import { VIEW, fit, hasGeography } from './projection'
import { useFrameSize } from './useFrameSize'

export interface PlaceMapProps {
  anchor: ExploreAnchor
  places: ExplorePlace[]
  route: ExploreRoute
  /** Real streets, water and parks. Absent until it loads, and absent for good
   *  if it cannot: the map is designed to work without it. */
  basemap?: Basemap
  radiusM: number
  timezone: string
  selectedId: string | null
  onSelect: (id: string | null) => void
  /** Brings the selected place's card into view, from the callout. */
  onOpen: (id: string) => void
  /** Floats over the map, top-left: the category chips. */
  children?: ReactNode
}

/** The map as a band in the Explore screen: fitted to the places, still, and
 *  a door into the expanded map for anyone who wants to look around. */
export function PlaceMap({
  anchor,
  places,
  route,
  basemap,
  radiusM,
  timezone,
  selectedId,
  onSelect,
  onOpen,
  children,
}: PlaceMapProps) {
  const bandRef = useRef<HTMLDivElement>(null)
  const size = useFrameSize(bandRef, { w: VIEW, h: VIEW })
  const [expanded, setExpanded] = useState(false)

  const viewport = fit(anchor, places, route, radiusM)
  const ground = hasGeography(basemap)
  const spur = spurTarget(places, route, selectedId)

  return (
    <div ref={bandRef} className="relative h-[352px] overflow-hidden bg-map-ground">
      <MapCanvas
        anchor={anchor}
        places={places}
        route={route}
        basemap={basemap}
        viewport={viewport}
        size={size}
        timezone={timezone}
        selectedId={selectedId}
        onSelect={onSelect}
        onOpen={onOpen}
      />

      <div className="absolute inset-x-4 top-3.5 z-30 flex items-start gap-2">
        <div className="min-w-0 flex-1">{children}</div>
        <button
          type="button"
          onClick={() => setExpanded(true)}
          aria-label="Expand map"
          className="grid size-9 flex-none place-items-center rounded-full border border-border bg-card text-ink shadow-[var(--shadow-chip)] hover:bg-surface focus-visible:outline-2 focus-visible:outline-primary"
        >
          <Maximize2 className="size-4" aria-hidden />
        </button>
      </div>

      {/* ODbL requires the credit wherever the geometry is shown, so this is a
          licence term rather than a nicety. Placed against the ground's own
          right edge, below the chips and clear of the route strip. */}
      {ground && (
        <p className="pointer-events-none absolute right-1.5 bottom-1 z-10 text-[9px] leading-none text-muted-faint">
          {basemap.attribution}
        </p>
      )}

      <div className="absolute inset-x-4 bottom-3.5 z-20 flex flex-col items-start gap-1.5">
        <RouteStrip route={route} />
        {spur !== null && <SpurPill place={spur} anchor={anchor} />}
      </div>

      {expanded && (
        <ExpandedMap
          anchor={anchor}
          places={places}
          route={route}
          basemap={basemap}
          radiusM={radiusM}
          timezone={timezone}
          selectedId={selectedId}
          onSelect={onSelect}
          onClose={() => setExpanded(false)}
        >
          {children}
        </ExpandedMap>
      )}
    </div>
  )
}
