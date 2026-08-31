/** The Explore map's flat projection, and the scale it draws at.

 *  Its own module because none of it renders anything, and because two layers
 *  now have to agree about it: the pins, and the street geometry underneath
 *  them. A second copy of this maths would put a city's streets under the
 *  wrong pin, and it would look like a data problem rather than a duplicated
 *  constant.
 */

import type { Basemap, ExploreAnchor, ExplorePlace, ExploreRoute } from '@/api/queries'

export const METERS_PER_DEGREE_LAT = 111_320
export const VIEW = 320
export const CENTER = VIEW / 2
export const PLOT_RADIUS = CENTER - 26

/** Metres east and north of the anchor. Scaling happens afterwards, once every
 *  point that has to fit on the plot has been measured. */
export interface Offset {
  eastM: number
  northM: number
}

export interface Point {
  x: number
  y: number
}

export function offset(
  lat: number | null | undefined,
  lng: number | null | undefined,
  anchor: ExploreAnchor,
): Offset | null {
  if (lat == null || lng == null || anchor.lat == null || anchor.lng == null) {
    return null
  }
  const shrink = Math.cos((anchor.lat * Math.PI) / 180)
  return {
    eastM: (lng - anchor.lng) * METERS_PER_DEGREE_LAT * shrink,
    northM: (lat - anchor.lat) * METERS_PER_DEGREE_LAT,
  }
}

/* Scale to the furthest thing drawn, not to the query radius. The radius is a
 * ceiling on what was searched; drawing to it puts every pin of a walkable
 * cluster in a heap at the centre of a mostly empty frame. A floor keeps a
 * single very close place from filling it.
 *
 * Route stops count towards the maximum even when a category filter hides
 * their pin, or the day's dinner leg runs off the edge whenever the Workout
 * chip is the one selected. */
function plotRadiusMeters(offsets: Offset[], radiusM: number): number {
  const furthest = offsets.reduce(
    (max, o) => Math.max(max, Math.hypot(o.eastM, o.northM)),
    0,
  )
  return furthest > 0 ? Math.max(furthest * 1.15, 400) : radiusM
}

/** How many metres the map will actually draw to, given what it is showing.

 *  Exported because the basemap has to be fetched for the same ground the map
 *  ends up covering, and that is decided here. A second computation in the
 *  screen would drift from this one and ask for an area the map does not draw.
 */
export function plotRadiusFor(
  anchor: ExploreAnchor,
  places: ExplorePlace[],
  route: ExploreRoute,
  radiusM: number,
): number {
  const offsets = [
    ...places.map((place) => offset(place.lat, place.lng, anchor)),
    ...route.stops.map((stop) => offset(stop.lat, stop.lng, anchor)),
  ].filter((at): at is Offset => at !== null)
  return plotRadiusMeters(offsets, radiusM)
}

/** True when there is enough geography to replace the placeholder grid.

 *  The grid texture stands in for streets. Leaving it under real ones would
 *  read as a second, wrong street network. */
export function hasGeography(basemap: Basemap | undefined): basemap is Basemap {
  if (basemap === undefined) return false
  return (
    basemap.roads_major.length > 0 ||
    basemap.roads_minor.length > 0 ||
    basemap.water.length > 0 ||
    basemap.parks.length > 0 ||
    basemap.buildings.length > 0
  )
}
