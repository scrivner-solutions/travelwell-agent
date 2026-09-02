import { useMemo } from 'react'
import type { Basemap, ExploreAnchor } from '@/api/queries'
import { metersPerUnit, offset, type Offset, type Size, type Viewport } from './projection'

/* Ways are stored flat -- [lat, lng, lat, lng, ...] -- because the payload is
   almost entirely numbers and nesting them cost about a third more bytes. */
const STRIDE = 2

/* How far past the loaded square a way may reach before it is dropped, as a
   share of the area's radius. The server sends every way that touches the
   square, so the ones this catches are the few that run right through it and
   out the other side of the city, and garbage. */
const CULL_MARGIN = 0.5

/* World units are metres east and south of the anchor -- south, so that the
   group transform below is a plain scale and never a flip. Paths are built
   once per loaded area; pan and zoom only move the group, which is what keeps
   a gesture over sixty thousand points from rebuilding a megabyte of path
   string per frame. */
function worldPath(
  ways: number[][],
  anchor: ExploreAnchor,
  centre: Offset,
  limitM: number,
  close: boolean,
): string {
  const parts: string[] = []
  for (const way of ways) {
    let d = ''
    let minX = Infinity
    let maxX = -Infinity
    let minY = Infinity
    let maxY = -Infinity
    for (let i = 0; i + 1 < way.length; i += STRIDE) {
      const at = offset(way[i], way[i + 1], anchor)
      if (at === null) break
      const x = at.eastM
      const y = -at.northM
      d += `${d === '' ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
      minX = Math.min(minX, x)
      maxX = Math.max(maxX, x)
      minY = Math.min(minY, y)
      maxY = Math.max(maxY, y)
    }
    if (d === '') continue
    const cx = centre.eastM
    const cy = -centre.northM
    const outside =
      maxX < cx - limitM || minX > cx + limitM || maxY < cy - limitM || minY > cy + limitM
    if (outside) continue
    parts.push(close ? `${d}Z` : d)
  }
  return parts.join('')
}

export interface BasemapLayerProps {
  basemap: Basemap
  anchor: ExploreAnchor
  viewport: Viewport
  size: Size
  /** Paint plain ground under this area first. For a finer area drawn over a
   *  coarser one: the two were simplified at different precisions, and the
   *  coarse streets showing through would double every road. */
  ground?: boolean
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
export function BasemapLayer({ basemap, anchor, viewport, size, ground = false }: BasemapLayerProps) {
  const paths = useMemo(() => {
    /* Where the area is: the server's snapped centre, which is not the anchor
       even for the anchor's own area. */
    const centre = offset(basemap.lat, basemap.lng, anchor) ?? { eastM: 0, northM: 0 }
    const limitM = basemap.radius_m * (1 + CULL_MARGIN)
    return {
      centre,
      water: worldPath(basemap.water, anchor, centre, limitM, true),
      parks: worldPath(basemap.parks, anchor, centre, limitM, true),
      buildings: worldPath(basemap.buildings, anchor, centre, limitM, true),
      minor: worldPath(basemap.roads_minor, anchor, centre, limitM, false),
      major: worldPath(basemap.roads_major, anchor, centre, limitM, false),
    }
  }, [basemap, anchor])

  const scale = 1 / metersPerUnit(viewport, size)
  const tx = size.w / 2 - viewport.centerEastM * scale
  const ty = size.h / 2 + viewport.centerNorthM * scale

  /* Road widths are in frame units, not metres: `non-scaling-stroke` keeps
     them from becoming rivers when the view zooms in, or vanishing out. */
  return (
    <g aria-hidden transform={`translate(${tx} ${ty}) scale(${scale})`}>
      {ground && (
        <rect
          x={paths.centre.eastM - basemap.radius_m}
          y={-paths.centre.northM - basemap.radius_m}
          width={basemap.radius_m * 2}
          height={basemap.radius_m * 2}
          className="fill-map-ground"
          data-testid="area-ground"
        />
      )}
      {paths.water !== '' && <path d={paths.water} className="fill-map-water" />}
      {paths.parks !== '' && <path d={paths.parks} className="fill-map-park" />}
      {paths.buildings !== '' && <path d={paths.buildings} className="fill-map-building" />}
      {paths.minor !== '' && (
        <path
          d={paths.minor}
          fill="none"
          strokeWidth={1.6}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          className="stroke-map-road"
        />
      )}
      {paths.major !== '' && (
        <path
          d={paths.major}
          fill="none"
          strokeWidth={3}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
          className="stroke-map-road-major"
        />
      )}
    </g>
  )
}
