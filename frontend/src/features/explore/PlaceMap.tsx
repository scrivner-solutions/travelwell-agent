import type { ExploreAnchor, ExplorePlace } from '@/api/queries'

/* Positions are real: each pin sits at its true bearing and distance from the
 * anchor, projected flat. What is missing is street detail, which needs map
 * tiles. So this draws the spatial relationship the brief asks for -- hotel to
 * gym to dinner -- without drawing streets it cannot know. Swapping tiles in
 * underneath later does not move a single pin. */

const METERS_PER_DEGREE_LAT = 111_320
const VIEW = 320
const CENTER = VIEW / 2
const PLOT_RADIUS = CENTER - 26

export interface PlaceMapProps {
  anchor: ExploreAnchor
  places: ExplorePlace[]
  radiusM: number
  selectedId: string | null
  onSelect: (id: string | null) => void
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

export function PlaceMap({
  anchor,
  places,
  radiusM,
  selectedId,
  onSelect,
}: PlaceMapProps) {
  const scaleM = plotRadiusMeters(places, radiusM)
  const metersPerUnit = scaleM / PLOT_RADIUS
  const pins = places
    .map((p) => project(p, anchor, metersPerUnit))
    .filter((p): p is Pin => p !== null)

  return (
    <div className="rounded-card border border-border-soft bg-card p-2">
      <svg
        viewBox={`0 0 ${VIEW} ${VIEW}`}
        className="h-auto w-full"
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
              stroke="var(--border-soft)"
            />
            <text
              x={CENTER}
              y={CENTER - meters / metersPerUnit - 4}
              textAnchor="middle"
              className="fill-[var(--state-neutral)] text-[9px]"
            >
              {formatRing(meters)}
            </text>
          </g>
        ))}

        {pins.map(({ place, x, y }) => {
          const selected = place.id === selectedId
          return (
            <g
              key={place.id}
              onClick={() => onSelect(selected ? null : place.id)}
              className="cursor-pointer"
            >
              <circle
                cx={x}
                cy={y}
                r={selected ? 8 : 5}
                fill={
                  place.over_budget_reason
                    ? 'var(--state-neutral)'
                    : 'var(--state-confirmed)'
                }
                stroke="var(--card)"
                strokeWidth={2}
              />
              {selected && (
                <text
                  x={x}
                  y={y - 13}
                  textAnchor="middle"
                  className="fill-[var(--ink)] text-[10px] font-medium"
                >
                  {place.name}
                </text>
              )}
            </g>
          )
        })}

        <g>
          <circle cx={CENTER} cy={CENTER} r={6} fill="var(--ink)" />
          <text
            x={CENTER}
            y={CENTER + 18}
            textAnchor="middle"
            className="fill-[var(--ink)] text-[10px] font-medium"
          >
            {anchor.name}
          </text>
        </g>
      </svg>
    </div>
  )
}
