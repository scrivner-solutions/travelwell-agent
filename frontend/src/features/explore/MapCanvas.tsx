import type { HTMLAttributes, Ref } from 'react'
import type { Basemap, ExploreAnchor, ExplorePlace, ExploreRoute } from '@/api/queries'
import { BasemapLayer } from './BasemapLayer'
import { hoursLabel } from './hours'
import { spurTarget } from './spur'
import {
  hasGeography,
  offset,
  toPoint,
  type Offset,
  type Point,
  type Size,
  type Viewport,
} from './projection'

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

/** The design labels pins by initial, not by rank. A number would claim an
 *  order the map does not have; a letter just points back at the card. */
function initial(name: string): string {
  return name.trim().charAt(0).toUpperCase()
}

/* Half the callout's 210px width, which is how far its centre must stay from
 * either edge to keep the whole box on. */
const CALLOUT_HALF_PX = 105

function walkLabel(place: ExplorePlace, anchor: ExploreAnchor): string | null {
  if (place.walk_minutes == null) return null
  return place.walk_minutes === 0
    ? `In ${anchor.name}`
    : `${place.walk_minutes} min walk from ${anchor.name}`
}

export interface MapCanvasProps {
  anchor: ExploreAnchor
  places: ExplorePlace[]
  route: ExploreRoute
  basemap?: Basemap
  viewport: Viewport
  size: Size
  timezone: string
  selectedId: string | null
  onSelect: (id: string | null) => void
  /** Shows the selected place's callout, whose chevron leads here. Absent
   *  where the card itself is already on screen. */
  onOpen?: (id: string) => void
  /** Handed to the ground: the expanded map's gestures land here. */
  groundProps?: HTMLAttributes<HTMLDivElement> & { ref?: Ref<HTMLDivElement> }
}

/** The ground and what stands on it: streets, the day's line, the anchor, the
 *  pins and the callout, drawn through one viewport into a frame of `size`.
 *  Everything is placed by percentage of that frame, so it stays put while a
 *  resize is being measured. */
export function MapCanvas({
  anchor,
  places,
  route,
  basemap,
  viewport,
  size,
  timezone,
  selectedId,
  onSelect,
  onOpen,
  groundProps,
}: MapCanvasProps) {
  const pct = (p: Point) => ({ left: `${(p.x / size.w) * 100}%`, top: `${(p.y / size.h) * 100}%` })
  const place = (at: Offset): Point => toPoint(viewport, size, at)
  const centre = place({ eastM: 0, northM: 0 })
  const ground = hasGeography(basemap)

  const pins = places.flatMap((entry) => {
    const at = offset(entry.lat, entry.lng, anchor)
    return at === null ? [] : [{ place: entry, ...place(at) }]
  })
  const routePoints = route.stops.flatMap((stop) => {
    const at = offset(stop.lat, stop.lng, anchor)
    return at === null ? [] : [place(at)]
  })

  const selected = pins.find((pin) => pin.place.id === selectedId) ?? null
  const selectedHours = selected ? hoursLabel(selected.place.hours, timezone) : null

  /* The spur is a proposal, not a plan, which is why it is periwinkle and
     dashed where the route is solid primary: the palette already spends those
     two colours on exactly that distinction. */
  const spur = spurTarget(places, route, selectedId)
  const spurTo = spur === null ? null : (pins.find((pin) => pin.place.id === spur.id) ?? null)

  return (
    <div className="absolute inset-0" {...groundProps}>
      {/* The grid stands in for streets. Under real ones it would read as a
          second, wrong street network, so it gives way to them. */}
      {!ground && (
        <div aria-hidden className="absolute inset-0 bg-[image:var(--map-texture)]" />
      )}

      <svg
        viewBox={`0 0 ${size.w} ${size.h}`}
        className="absolute inset-0 h-full w-full"
        role="img"
        aria-label={`Places around ${anchor.name}`}
      >
        {ground && (
          <BasemapLayer basemap={basemap} anchor={anchor} viewport={viewport} size={size} />
        )}
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
            points={`${centre.x},${centre.y} ${spurTo.x},${spurTo.y}`}
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
          ...pct(centre),
          width: anchor.is_hotel ? 30 : 14,
          height: anchor.is_hotel ? 30 : 14,
        }}
      >
        {anchor.is_hotel ? 'H' : ''}
        <span className="sr-only">{anchor.name}</span>
      </div>

      {pins.map(({ place: pin, x, y }) => {
        const isSelected = pin.id === selectedId
        const pinSize = isSelected ? 40 : 34
        return (
          <button
            key={pin.id}
            type="button"
            aria-pressed={isSelected}
            onClick={() => onSelect(isSelected ? null : pin.id)}
            className={`absolute grid -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 text-[11px] font-semibold leading-none shadow-[var(--shadow-pin)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
              isSelected
                ? 'z-20 border-primary bg-primary text-card'
                : 'border-card bg-card text-ink'
            }`}
            style={{ ...pct({ x, y }), width: pinSize, height: pinSize }}
          >
            <span aria-hidden>{initial(pin.name)}</span>
            <span className="sr-only">
              {pin.name}
              {pin.walk_minutes != null && `, ${pin.walk_minutes} min walk`}
            </span>
          </button>
        )
      })}

      {selected && onOpen && (
        <div
          className="absolute z-30 -translate-x-1/2 -translate-y-full pb-3"
          // Clamped by half the callout's own width, not by an eyeballed
          // margin: the first version clamped the pin and the box still ran
          // off the edge, because the box is wider than the margin it left.
          style={pct({
            x: Math.min(size.w - CALLOUT_HALF_PX, Math.max(CALLOUT_HALF_PX, selected.x)),
            y: selected.y,
          })}
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
  )
}
