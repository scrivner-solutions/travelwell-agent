import type { ReactNode } from 'react'
import type { ExploreAnchor, ExplorePlace } from '@/api/queries'
import { hoursLabel } from './hours'

/* Positions are real: each pin sits at its true bearing and distance from the
 * anchor, projected flat. What is missing is street detail, which needs map
 * tiles. So this draws the spatial relationship the brief asks for -- hotel to
 * gym to dinner -- without drawing streets it cannot know. Swapping tiles in
 * underneath later does not move a single pin.
 *
 * The design's painted park and road blocks are deliberately absent for the
 * same reason: they are geography, and we do not have any. */

const METERS_PER_DEGREE_LAT = 111_320
const VIEW = 320
const CENTER = VIEW / 2
const PLOT_RADIUS = CENTER - 26

export interface PlaceMapProps {
  anchor: ExploreAnchor
  places: ExplorePlace[]
  radiusM: number
  timezone: string
  selectedId: string | null
  onSelect: (id: string | null) => void
  /** Floats over the map, top-left: the category chips. */
  children?: ReactNode
}

interface Pin {
  place: ExplorePlace
  x: number
  y: number
}

function project(
  place: ExplorePlace,
  anchor: ExploreAnchor,
  metersPerUnit: number,
): Pin | null {
  if (
    place.lat == null ||
    place.lng == null ||
    anchor.lat == null ||
    anchor.lng == null
  ) {
    return null
  }
  const shrink = Math.cos((anchor.lat * Math.PI) / 180)
  const eastM = (place.lng - anchor.lng) * METERS_PER_DEGREE_LAT * shrink
  const northM = (place.lat - anchor.lat) * METERS_PER_DEGREE_LAT
  return {
    place,
    x: CENTER + eastM / metersPerUnit,
    // Screen y grows downward; north must go up.
    y: CENTER - northM / metersPerUnit,
  }
}

/* Scale to the furthest place, not to the query radius. The radius is a
 * ceiling on what was searched; drawing to it puts every pin of a walkable
 * cluster in a heap at the centre of a mostly empty circle. A floor keeps a
 * single very close place from filling the frame. */
function plotRadiusMeters(places: ExplorePlace[], radiusM: number): number {
  const furthest = places.reduce(
    (max, p) => (p.distance_meters != null && p.distance_meters > max ? p.distance_meters : max),
    0,
  )
  return furthest > 0 ? Math.max(furthest * 1.15, 400) : radiusM
}

/** Two rings: half way out, and the edge. */
function rings(scaleM: number): number[] {
  return [scaleM / 2, scaleM]
}

function formatRing(meters: number): string {
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${Math.round(meters)} m`
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

export function PlaceMap({
  anchor,
  places,
  radiusM,
  timezone,
  selectedId,
  onSelect,
  children,
}: PlaceMapProps) {
  const scaleM = plotRadiusMeters(places, radiusM)
  const metersPerUnit = scaleM / PLOT_RADIUS
  const pins = places
    .map((p) => project(p, anchor, metersPerUnit))
    .filter((p): p is Pin => p !== null)
  const selected = pins.find((p) => p.place.id === selectedId) ?? null
  const selectedHours = selected ? hoursLabel(selected.place.hours, timezone) : null

  return (
    <div className="relative h-[352px] overflow-hidden bg-map-ground">
      <div aria-hidden className="absolute inset-0 bg-[image:var(--map-texture)]" />

      {/* Kept square and centred so a percentage offset means the same distance
          horizontally as vertically. The ground fills whatever is left over. */}
      <div className="absolute inset-y-0 left-1/2 aspect-square -translate-x-1/2">
        <svg
          viewBox={`0 0 ${VIEW} ${VIEW}`}
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label={`Places around ${anchor.name}`}
        >
          {rings(scaleM).map((meters) => (
            <g key={meters}>
              <circle
                cx={CENTER}
                cy={CENTER}
                r={meters / metersPerUnit}
                fill="none"
                stroke="var(--muted-faint)"
                strokeDasharray="2 5"
              />
              <text
                x={CENTER}
                y={CENTER + meters / metersPerUnit + 12}
                textAnchor="middle"
                className="fill-[var(--muted-soft)] text-[9px]"
              >
                {formatRing(meters)}
              </text>
            </g>
          ))}
        </svg>

        {/* The anchor. A hotel is a place and gets its letter; a city centre is
            not one, and gets a plain point rather than a borrowed initial. */}
        <div
          className="absolute grid -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-ink font-semibold text-[11px] leading-none text-card shadow-[var(--shadow-pin)]"
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
                  ? 'z-10 border-primary bg-primary text-card'
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
            className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-full pb-3"
            // Clamped by half the callout's own width, not by an eyeballed
            // margin: the first version clamped the pin and the box still ran
            // off the edge, because the box is wider than the margin it left.
            style={{
              left: `${Math.min(100 - CALLOUT_HALF_PCT, Math.max(CALLOUT_HALF_PCT, (selected.x / VIEW) * 100))}%`,
              top: pct(selected.y),
            }}
          >
            <div className="w-[210px] rounded-control border border-border bg-card px-3 py-2.5 shadow-[var(--shadow-callout)]">
              <p className="text-body-sm font-semibold">{selected.place.name}</p>
              {walkLabel(selected.place, anchor) != null && (
                <p className="mt-1 text-label text-muted">
                  {walkLabel(selected.place, anchor)}
                </p>
              )}
              {selectedHours && (
                <p
                  className={`mt-1.5 text-label font-medium ${
                    selectedHours.tight ? 'text-ink' : 'text-muted-soft'
                  }`}
                >
                  {selectedHours.text}
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {children && <div className="absolute inset-x-4 top-3.5 z-30">{children}</div>}
    </div>
  )
}
