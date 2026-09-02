import { useCallback, useMemo, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { basemapFetchesLeft, basemapQueryOptions, type Basemap, type ExploreAnchor } from '@/api/queries'
import { areaCovering, areaKey, covers, type AreaRequest, type Rect } from './areas'
import { hasGeography } from './projection'

/* How many settled views are kept live. A zoom-in, a pan to the next block
   and the wide fill for a tall frame is three; anything older is served from
   the query cache the moment the view returns to it, at no request. */
const KEEP = 3

/* Answered cells are kept; a cell still on the wire when the view moves on
   is dropped, which cancels its request. A pan across a wide map settles
   several times a second, and each settle that kept its predecessor alive
   would be one more query in a provider queue two deep. If the view comes
   back, the cell is simply asked for again. */
function remember(prev: AreaRequest[], answered: boolean[], next: AreaRequest): AreaRequest[] {
  const key = areaKey(next)
  const last = prev[prev.length - 1]
  if (last !== undefined && areaKey(last) === key) return prev
  const kept = prev.filter((area, i) => answered[i] === true && areaKey(area) !== key)
  return [...kept, next].slice(-KEEP)
}

interface Answers {
  layers: Basemap[]
  /** Per requested area, in order: has the server said anything yet. */
  answered: boolean[]
}

const settle = (results: { data?: Basemap; status: 'pending' | 'error' | 'success' }[]): Answers => ({
  layers: results.flatMap((result) =>
    result.data !== undefined && hasGeography(result.data) ? [result.data] : [],
  ),
  answered: results.map((result) => result.status !== 'pending'),
})

export interface AreaDetail {
  /** Coarsest first, so each paints its ground over the one beneath. */
  layers: Basemap[]
  /** Give this to the expanded map; it calls it once a view holds still. */
  onView: (rect: Rect) => void
}

/* A finer cell is asked for only when it is at most half the size of the
   finest one already covering the view. One step down the ladder buys a few
   more decimals and the same streets; two steps is where buildings appear
   and blocks resolve, which is what a zoom-in was for. */
const WORTH_A_REQUEST = 2

/* How much of a tall frame a cell has to cover: its width and the middle
   1.5:1 of its height. A phone is over twice as tall as it is wide, and a
   cell that had to reach its top and bottom edges would be one or two
   buckets wider than the zoom asked for, so buildings would arrive late and
   blurred. What lies beyond is the coarser layer, under the chips and the
   card, and the next settle nearer it fetches its own cell. */
const ASPECT_COVERED = 1.5

function middle(rect: Rect): Rect {
  return {
    ...rect,
    halfWidthM: Math.min(rect.halfWidthM, rect.halfHeightM * ASPECT_COVERED),
    halfHeightM: Math.min(rect.halfHeightM, rect.halfWidthM * ASPECT_COVERED),
  }
}

/** Finer ground for wherever the expanded map has settled, and wider ground
 *  for a frame the base area does not fill.

 *  Kept out of the map components on purpose: they draw whatever they are
 *  handed and stay testable without a query client, and this is the one
 *  place that decides whether a settled view is worth a request. It never
 *  asks while something it holds already covers the view at nearly this
 *  size, never asks at all once the trip's session budget is spent, and a
 *  base that came back empty means the server has nothing for this city, so
 *  it stops there. At most one request is on the wire at a time: moving on
 *  cancels the one the last view asked for. */
export function useAreaDetail(
  tripId: string,
  anchor: ExploreAnchor | null | undefined,
  base: Basemap | undefined,
): AreaDetail {
  const [areas, setAreas] = useState<AreaRequest[]>([])

  const answers = useQueries({
    queries: areas.map((area) => ({
      ...basemapQueryOptions(tripId, area),
      enabled: basemapFetchesLeft(tripId) > 0,
    })),
    combine: settle,
  })
  const layers = useMemo(
    () => [...answers.layers].sort((a, b) => b.radius_m - a.radius_m),
    [answers.layers],
  )
  const held = useMemo(
    () => (base !== undefined && hasGeography(base) ? [base, ...layers] : layers),
    [base, layers],
  )

  const onView = useCallback(
    (shown: Rect) => {
      if (anchor == null) return
      if (base !== undefined && !hasGeography(base)) return
      const rect = middle(shown)
      const wanted = areaCovering(anchor, rect)
      if (wanted === null) return
      const covering = held.filter((area) => covers(area, anchor, rect))
      if (covering.length > 0) {
        const finest = Math.min(...covering.map((area) => area.radius_m))
        if (wanted.radius_m * WORTH_A_REQUEST > finest) return
      }
      setAreas((prev) => remember(prev, answers.answered, wanted))
    },
    [anchor, answers.answered, base, held],
  )

  return { layers, onView }
}
