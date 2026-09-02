import type { Basemap, ExploreAnchor } from '@/api/queries'
import { METERS_PER_DEGREE_LAT, metersPerUnit, offset, type Size, type Viewport } from './projection'

/* The server's cache cells, repeated here so the client can name the cell it
   is about to be given and skip asking for one it already holds. Mirrors
   `_RADIUS_BUCKETS` and `snap()` in backend/app/services/basemap/geometry.py;
   the two are pinned together by the same numbers in areas.test.ts and
   test_basemap.py. A disagreement costs one duplicate request, never a wrong
   picture, because what is drawn is placed by the centre the server returns. */
export const RADIUS_BUCKETS = [750, 1000, 1500, 2000, 3000, 4000, 5500, 8000, 11000, 16000] as const
const GRID_SHARE = 0.5

/** One cache cell: a snapped centre and a bucketed radius. */
export interface AreaRequest {
  lat: number
  lng: number
  radius_m: number
}

/** What the frame shows, in metres from the anchor. */
export interface Rect {
  centerEastM: number
  centerNorthM: number
  halfWidthM: number
  halfHeightM: number
}

export function bucketRadius(radiusM: number): number {
  let widest = 0
  for (const bucket of RADIUS_BUCKETS) {
    if (radiusM <= bucket) return bucket
    widest = bucket
  }
  return widest
}

export function snap(lat: number, lng: number, radiusM: number): { lat: number; lng: number } {
  const stepLat = (radiusM * GRID_SHARE) / METERS_PER_DEGREE_LAT
  const snappedLat = Math.round(lat / stepLat) * stepLat
  const stepLng = stepLat / Math.max(Math.cos((snappedLat * Math.PI) / 180), 0.01)
  return { lat: snappedLat, lng: Math.round(lng / stepLng) * stepLng }
}

export function normalizeArea(lat: number, lng: number, radiusM: number): AreaRequest {
  const radius = bucketRadius(radiusM)
  return { ...snap(lat, lng, radius), radius_m: radius }
}

export function areaKey(area: { lat: number | null; lng: number | null; radius_m: number }): string {
  return `${area.lat},${area.lng},${area.radius_m}`
}

export function visibleRect(viewport: Viewport, size: Size): Rect {
  const mpu = metersPerUnit(viewport, size)
  return {
    centerEastM: viewport.centerEastM,
    centerNorthM: viewport.centerNorthM,
    halfWidthM: (size.w / 2) * mpu,
    halfHeightM: (size.h / 2) * mpu,
  }
}

/** Whether the square this area was fetched for contains the whole rect. */
export function covers(
  area: Pick<Basemap, 'lat' | 'lng' | 'radius_m'>,
  anchor: ExploreAnchor,
  rect: Rect,
): boolean {
  const at = offset(area.lat, area.lng, anchor)
  if (at === null) return false
  return (
    Math.abs(rect.centerEastM - at.eastM) + rect.halfWidthM <= area.radius_m &&
    Math.abs(rect.centerNorthM - at.northM) + rect.halfHeightM <= area.radius_m
  )
}

/** The smallest cell that shows the whole rect, snapping included: a centre
 *  moves by up to a quarter of the radius when it is snapped, so the bucket
 *  that merely contains the rect can leave a strip of it bare. Falls back to
 *  the widest cell rather than nothing, since most of a map beats none. */
export function areaCovering(anchor: ExploreAnchor, rect: Rect): AreaRequest | null {
  if (anchor.lat == null || anchor.lng == null) return null
  const shrink = Math.cos((anchor.lat * Math.PI) / 180)
  const lat = anchor.lat + rect.centerNorthM / METERS_PER_DEGREE_LAT
  const lng = anchor.lng + rect.centerEastM / (METERS_PER_DEGREE_LAT * shrink)
  let widest: AreaRequest | null = null
  for (const bucket of RADIUS_BUCKETS) {
    widest = normalizeArea(lat, lng, bucket)
    if (covers(widest, anchor, rect)) return widest
  }
  return widest
}
