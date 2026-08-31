import type { ReactNode } from 'react'
import type { Basemap, ExploreAnchor, ExplorePlace, ExploreRoute } from '@/api/queries'
import { BasemapLayer } from './BasemapLayer'
import {
  CENTER,
  PLOT_RADIUS,
  VIEW,
  hasGeography,
  offset,
  plotRadiusFor,
  type Offset,
  type Point,
} from './projection'
import { hoursLabel } from './hours'

/* Positions are real: each pin sits at its true bearing and distance from the
 * anchor, projected flat, on top of real streets drawn by `BasemapLayer`.
 *
 * The design's painted park, river and block are still not copied, and the
 * reason is worth keeping: they are geography drawn where it looked good, and
 * a green rectangle labelled MILLENNIUM PARK is right in Chicago and a lie in
 * Kyoto. The answer was never a nicer fake. OpenStreetMap gives the real
 * geometry away -- what a tile provider charges for is its own rendering of
 * it, which is precisely the half we do not want, since ours has to arrive in
 * this palette. */

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

/** The design labels pins by initial, not by rank. A number would claim an
 *  order the map does not have; a letter just points back at the card. */
function initial(name: string): string {
  return name.trim().charAt(0).toUpperCase()
}

const pct = (n: number) => `${(n / VIEW) * 100}%`

/* Half the callout's 210px width as a share of the 352px plot square, which is
 * how far its centre must stay from either edge to keep the whole box on. */
const CALLOUT_HALF_PCT = (105 / 352) * 100

function walkLabel(place: ExplorePlace, anchor: ExploreAnchor): string | null {
  if (place.walk_minutes == null) return null
  return place.walk_minutes === 0
    ? `In ${anchor.name}`
    : `${place.walk_minutes} min walk from ${anchor.name}`
}

/* Both sides read the same `places` row, so this is an equality test written
 * with a tolerance, not a proximity test: a different place a metre away is
 * still a different place. */
function samePoint(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  return Math.abs(a.lat - b.lat) < 1e-9 && Math.abs(a.lng - b.lng) < 1e-9
}

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
  const placeOffsets = places.map((place) => ({
    place,
    at: offset(place.lat, place.lng, anchor),
  }))
  const routeOffsets = route.stops.map((stop) => ({
    stop,
    at: offset(stop.lat, stop.lng, anchor),
  }))

  const metersPerUnit = plotRadiusFor(anchor, places, route, radiusM) / PLOT_RADIUS
  const toPoint = (at: Offset): Point => ({
    x: CENTER + at.eastM / metersPerUnit,
    // Screen y grows downward; north must go up.
    y: CENTER - at.northM / metersPerUnit,
  })

  /* The basemap arrives as coordinates, so it goes through exactly the maths
     the pins do. That is what keeps the streets under the right pin when a
     category filter changes the scale -- a pre-rendered image could not. */
  const project = (lat: number, lng: number): Point => {
    const at = offset(lat, lng, anchor)
    // Far enough off-canvas to be culled. Reached only when the anchor has no
    // coordinates, in which case there is no basemap to draw either.
    return at === null ? { x: -9999, y: -9999 } : toPoint(at)
  }
  const ground = hasGeography(basemap)

  const pins = placeOffsets.flatMap((entry) =>
    entry.at === null ? [] : [{ place: entry.place, ...toPoint(entry.at) }],
  )
  const routePoints = routeOffsets.flatMap((entry) =>
    entry.at === null ? [] : [toPoint(entry.at)],
  )

  const selected = pins.find((pin) => pin.place.id === selectedId) ?? null
  const selectedHours = selected ? hoursLabel(selected.place.hours, timezone) : null

  /* The spur is a proposal, not a plan, which is why it is periwinkle and
     dashed where the route is solid primary: the palette already spends those
     two colours on exactly that distinction. It says something only about a
     place the day does not already go to. */
  const spurTo =
    selected !== null &&
    selected.place.lat != null &&
    selected.place.lng != null &&
    selected.place.walk_minutes != null &&
    selected.place.walk_minutes > 0 &&
    !route.stops.some((stop) =>
      samePoint(stop, { lat: selected.place.lat!, lng: selected.place.lng! }),
    )
      ? selected
      : null

  return (
    <div className="relative h-[352px] overflow-hidden bg-map-ground">
      {/* The grid stands in for streets. Under real ones it would read as a
          second, wrong street network, so it gives way to them. */}
      {!ground && (
        <div aria-hidden className="absolute inset-0 bg-[image:var(--map-texture)]" />
      )}

      {/* Kept square and centred so a percentage offset means the same distance
          horizontally as vertically. The ground fills whatever is left over. */}
      <div className="absolute inset-y-0 left-1/2 aspect-square -translate-x-1/2">
        <svg
          viewBox={`0 0 ${VIEW} ${VIEW}`}
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label={`Places around ${anchor.name}`}
        >
          {ground && <BasemapLayer basemap={basemap} project={project} view={VIEW} />}
          {routePoints.length > 1 && (
            <polyline
              points={routePoints.map((p) => `${p.x},${p.y}`).join(' ')}
              fill="none"
              stroke="var(--primary)"
              strokeWidth={2.4}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={0.8}
            />
          )}
          {spurTo && (
            <polyline
              points={`${CENTER},${CENTER} ${spurTo.x},${spurTo.y}`}
              fill="none"
              stroke="var(--agent-bright)"
              strokeWidth={2}
              strokeDasharray="4 6"
              strokeLinecap="round"
              opacity={0.9}
            />
          )}
        </svg>

        {/* The anchor. A hotel is a place and gets its letter; a city centre is
            not one, and gets a plain point rather than a borrowed initial.

            Painted over the pins because a place can sit on top of it -- a
            hotel gym is a minute from the hotel -- and the point every distance
            on the screen is measured from cannot be the one that disappears.
            Click-through, so covering that pin does not also disable it. */}
        <div
          className="pointer-events-none absolute z-10 grid -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-ink font-semibold text-[11px] leading-none text-card shadow-[var(--shadow-pin)]"
          style={{
            left: pct(CENTER),
            top: pct(CENTER),
            width: anchor.is_hotel ? 30 : 14,
            height: anchor.is_hotel ? 30 : 14,
          }}
        >
          {anchor.is_hotel ? 'H' : ''}
          <span className="sr-only">{anchor.name}</span>
        </div>

        {pins.map(({ place, x, y }) => {
          const isSelected = place.id === selectedId
          const size = isSelected ? 40 : 34
          return (
            <button
              key={place.id}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onSelect(isSelected ? null : place.id)}
              className={`absolute grid -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 text-[11px] font-semibold leading-none shadow-[var(--shadow-pin)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                isSelected
                  ? 'z-20 border-primary bg-primary text-card'
                  : 'border-card bg-card text-ink'
              }`}
              style={{ left: pct(x), top: pct(y), width: size, height: size }}
            >
              <span aria-hidden>{initial(place.name)}</span>
              <span className="sr-only">
                {place.name}
                {place.walk_minutes != null && `, ${place.walk_minutes} min walk`}
              </span>
            </button>
          )
        })}

        {selected && (
          <div
            className="absolute z-30 -translate-x-1/2 -translate-y-full pb-3"
            // Clamped by half the callout's own width, not by an eyeballed
            // margin: the first version clamped the pin and the box still ran
            // off the edge, because the box is wider than the margin it left.
            style={{
              left: `${Math.min(100 - CALLOUT_HALF_PCT, Math.max(CALLOUT_HALF_PCT, (selected.x / VIEW) * 100))}%`,
              top: pct(selected.y),
            }}
          >
            <button
              type="button"
              onClick={() => onOpen(selected.place.id)}
              className="w-[210px] rounded-control border border-border bg-card px-3 py-2.5 text-left shadow-[var(--shadow-callout)] hover:border-primary focus-visible:outline-2 focus-visible:outline-primary"
            >
              <span className="block text-body-sm font-semibold">
                {selected.place.name}
              </span>
              {walkLabel(selected.place, anchor) != null && (
                <span className="mt-1 block text-label text-muted">
                  {walkLabel(selected.place, anchor)}
                </span>
              )}
              {/* The design's chevron, and it has to lead somewhere: it brings
                  this place's card into view, which is where the actions are.
                  A chevron that did nothing would promise a screen. */}
              <span className="mt-1.5 flex items-center justify-between gap-2">
                <span
                  className={`text-label font-medium ${
                    selectedHours?.tight ? 'text-ink' : 'text-muted-soft'
                  }`}
                >
                  {selectedHours?.text ?? 'See details'}
                </span>
                <svg
                  aria-hidden
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="var(--primary)"
                  strokeWidth={2.2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </span>
            </button>
          </div>
        )}
      </div>

      {children && <div className="absolute inset-x-4 top-3.5 z-30">{children}</div>}

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
        {spurTo && (
          <p className="rounded-full border border-agent-soft bg-state-suggested-soft px-3 py-1.5 text-label font-medium text-agent">
            Add {spurTo.place.name}: +{spurTo.place.walk_minutes} min from {anchor.name}
          </p>
        )}
      </div>
    </div>
  )
}

/* The day read as a walk rather than as a list of times. It stays on screen
 * with nothing planned, because "nothing planned today" is the answer to the
 * question an empty map otherwise leaves open. */
function RouteStrip({ route }: { route: ExploreRoute }) {
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
