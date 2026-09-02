import type { ExplorePlace, ExploreRoute } from '@/api/queries'

/* Both sides read the same `places` row, so this is an equality test written
 * with a tolerance, not a proximity test: a different place a metre away is
 * still a different place. */
function samePoint(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  return Math.abs(a.lat - b.lat) < 1e-9 && Math.abs(a.lng - b.lng) < 1e-9
}

/** The selected place, if the day does not already go there: what the spur
 *  line and the spur pill are both about. Null otherwise. */
export function spurTarget(
  places: ExplorePlace[],
  route: ExploreRoute,
  selectedId: string | null,
): ExplorePlace | null {
  const selected = places.find((place) => place.id === selectedId)
  if (
    selected === undefined ||
    selected.lat == null ||
    selected.lng == null ||
    selected.walk_minutes == null ||
    selected.walk_minutes <= 0
  ) {
    return null
  }
  const there = { lat: selected.lat, lng: selected.lng }
  return route.stops.some((stop) => samePoint(stop, there)) ? null : selected
}
