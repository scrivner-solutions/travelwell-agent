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

/* ---- Viewport ------------------------------------------------------------

   What the map is looking at, in metres from the anchor, independent of the
   pixels it is drawn into. Pan and zoom are edits to this record; the draw is a
   function of it. Every function below is pure so the gestures can be tested
   without a DOM, and so the inline band and the expanded map can share one
   projection instead of agreeing by coincidence. */

export interface Viewport {
  centerEastM: number
  centerNorthM: number
  /** Metres from the centre to the nearest edge. The frame need not be square,
   *  so it is the SHORTER side that shows exactly this much ground. */
  radiusM: number
}

/** The frame, in whatever unit the caller places things in: SVG user units for
 *  the inline band, CSS pixels for the expanded map. */
export interface Size {
  w: number
  h: number
}

export interface ZoomBounds {
  minRadiusM: number
  maxRadiusM: number
}

/* Below this the 4-5 dp simplification of the geometry wobbles, and the
 * smallest area the server keeps is 750 m anyway. */
export const MIN_RADIUS_M = 250

/** Zooming further out than twice the fitted view only shows empty ground past
 *  the square that was fetched. */
export function zoomBoundsFor(fitted: Viewport): ZoomBounds {
  return { minRadiusM: MIN_RADIUS_M, maxRadiusM: fitted.radiusM * 2 }
}

/** Today's view: centred on the anchor, scaled so the furthest pin sits at
 *  `PLOT_RADIUS` of the `CENTER` half-frame. */
export function fit(
  anchor: ExploreAnchor,
  places: ExplorePlace[],
  route: ExploreRoute,
  radiusM: number,
): Viewport {
  return {
    centerEastM: 0,
    centerNorthM: 0,
    radiusM: (plotRadiusFor(anchor, places, route, radiusM) * CENTER) / PLOT_RADIUS,
  }
}

export function metersPerUnit(vp: Viewport, size: Size): number {
  return vp.radiusM / (Math.min(size.w, size.h) / 2)
}

export function toPoint(vp: Viewport, size: Size, at: Offset): Point {
  const mpu = metersPerUnit(vp, size)
  return {
    x: size.w / 2 + (at.eastM - vp.centerEastM) / mpu,
    // Screen y grows downward; north must go up.
    y: size.h / 2 - (at.northM - vp.centerNorthM) / mpu,
  }
}

export function toOffset(vp: Viewport, size: Size, p: Point): Offset {
  const mpu = metersPerUnit(vp, size)
  return {
    eastM: vp.centerEastM + (p.x - size.w / 2) * mpu,
    northM: vp.centerNorthM - (p.y - size.h / 2) * mpu,
  }
}

/** Drag the ground by (dx, dy) frame units: the centre moves the other way. */
export function pan(vp: Viewport, dx: number, dy: number, size: Size): Viewport {
  const mpu = metersPerUnit(vp, size)
  return {
    ...vp,
    centerEastM: vp.centerEastM - dx * mpu,
    centerNorthM: vp.centerNorthM + dy * mpu,
  }
}

/** Zoom by `factor` (> 1 zooms in) about a point of the frame, keeping the
 *  ground under that point where it is. Clamped to `bounds`; at a limit the
 *  view stays put rather than sliding. */
export function zoomAt(
  vp: Viewport,
  factor: number,
  about: Point,
  size: Size,
  bounds: ZoomBounds,
): Viewport {
  const radiusM = Math.min(bounds.maxRadiusM, Math.max(bounds.minRadiusM, vp.radiusM / factor))
  if (radiusM === vp.radiusM) return vp
  const ground = toOffset(vp, size, about)
  const zoomed = { ...vp, radiusM }
  const mpu = metersPerUnit(zoomed, size)
  return {
    ...zoomed,
    centerEastM: ground.eastM - (about.x - size.w / 2) * mpu,
    centerNorthM: ground.northM + (about.y - size.h / 2) * mpu,
  }
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
