import type { Basemap } from '@/api/queries'
import type { Point } from './projection'

/* Ways are stored flat -- [lat, lng, lat, lng, ...] -- because the payload is
   almost entirely numbers and nesting them cost about a third more bytes. */
const STRIDE = 2

/* How far outside the frame a way may reach before it is dropped. The cached
   area is squared off around the anchor while the frame is scaled to the pins,
   so a city's worth of geometry can sit off-canvas; culling it keeps that out
   of the DOM rather than out of the download. */
const MARGIN = 24

function path(ways: number[][], project: (lat: number, lng: number) => Point, view: number, close: boolean): string {
  const parts: string[] = []
  for (const way of ways) {
    let d = ''
    let minX = Infinity
    let maxX = -Infinity
    let minY = Infinity
    let maxY = -Infinity
    for (let i = 0; i + 1 < way.length; i += STRIDE) {
      const lat = way[i]
      const lng = way[i + 1]
      if (lat === undefined || lng === undefined) break
      const { x, y } = project(lat, lng)
      d += `${d === '' ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
      minX = Math.min(minX, x)
      maxX = Math.max(maxX, x)
      minY = Math.min(minY, y)
      maxY = Math.max(maxY, y)
    }
    if (d === '') continue
    const offCanvas =
      maxX < -MARGIN || minX > view + MARGIN || maxY < -MARGIN || minY > view + MARGIN
    if (offCanvas) continue
    parts.push(close ? `${d}Z` : d)
  }
  return parts.join('')
}

export interface BasemapLayerProps {
  basemap: Basemap
  project: (lat: number, lng: number) => Point
  view: number
}

/** The ground: water, parks and streets, drawn beneath everything of ours.

 *  Painted rather than fetched as an image, which is the whole reason it can
 *  be in the product's palette. A rendered tile arrives in someone else's
 *  colours and would fight the design on every screen it appeared on.
 *
 *  Draw order is the real map convention and not arbitrary: areas first, then
 *  buildings, then the smaller road classes, then the larger ones on top. That
 *  is what makes a street look carved through a block rather than painted over
 *  it, and a motorway look like it crosses a side street. */
export function BasemapLayer({ basemap, project, view }: BasemapLayerProps) {
  const water = path(basemap.water, project, view, true)
  const parks = path(basemap.parks, project, view, true)
  const buildings = path(basemap.buildings, project, view, true)
  const minor = path(basemap.roads_minor, project, view, false)
  const major = path(basemap.roads_major, project, view, false)

  return (
    <g aria-hidden>
      {water !== '' && <path d={water} className="fill-map-water" />}
      {parks !== '' && <path d={parks} className="fill-map-park" />}
      {buildings !== '' && <path d={buildings} className="fill-map-building" />}
      {minor !== '' && (
        <path
          d={minor}
          fill="none"
          strokeWidth={1.6}
          strokeLinecap="round"
          className="stroke-map-road"
        />
      )}
      {major !== '' && (
        <path
          d={major}
          fill="none"
          strokeWidth={3}
          strokeLinecap="round"
          className="stroke-map-road-major"
        />
      )}
    </g>
  )
}
