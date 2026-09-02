import { describe, expect, it } from 'vitest'
import type { ExploreAnchor, ExplorePlace, ExploreRoute } from '@/api/queries'
import {
  CENTER,
  MIN_RADIUS_M,
  PLOT_RADIUS,
  VIEW,
  fit,
  offset,
  pan,
  toOffset,
  toPoint,
  zoomAt,
  zoomBoundsFor,
  type Size,
  type Viewport,
} from './projection'

const anchor: ExploreAnchor = { name: 'The Gwen', is_hotel: true, lat: 41.8924, lng: -87.6252 }
const noRoute: ExploreRoute = { stops: [], total_minutes: null }

function place(over: Partial<ExplorePlace> & { id: string }): ExplorePlace {
  return {
    kind: 'workout',
    name: over.id,
    summary: null,
    address: null,
    lat: null,
    lng: null,
    price_level: null,
    day_pass_cents: null,
    amenities: null,
    hours: null,
    photo_url: null,
    reservable_via: null,
    matched_preferences: [],
    unknown_notes: [],
    over_budget_reason: null,
    distance_meters: null,
    walk_minutes: null,
    ...over,
  }
}

const square: Size = { w: VIEW, h: VIEW }
const wide: Size = { w: 800, h: 400 }
const close = (a: number, b: number, tol = 1e-6) => Math.abs(a - b) < tol

describe('offset', () => {
  it('measures north up and east right, in metres', () => {
    const n = offset(41.9, -87.6252, anchor)!
    const e = offset(41.8924, -87.61, anchor)!
    expect(n.northM).toBeGreaterThan(0)
    expect(close(n.eastM, 0)).toBe(true)
    expect(e.eastM).toBeGreaterThan(0)
    expect(close(e.northM, 0)).toBe(true)
    // 0.0076 degrees of latitude is about 846 m; a degree of longitude is
    // shorter than one of latitude by cos(lat), about 0.74 at Chicago.
    expect(n.northM).toBeCloseTo(846, 0)
    expect(e.eastM).toBeCloseTo(0.0152 * 111_320 * Math.cos((41.8924 * Math.PI) / 180), 0)
  })

  it('has no answer without coordinates on either end', () => {
    expect(offset(null, -87.6, anchor)).toBeNull()
    expect(offset(41.9, -87.6, { ...anchor, lat: null })).toBeNull()
  })
})

describe('fit', () => {
  const north = place({ id: 'n', lat: 41.9, lng: -87.6252 })

  it('puts the furthest pin inside the plot radius of the inline square, with headroom', () => {
    const vp = fit(anchor, [north], noRoute, 8000)
    const p = toPoint(vp, square, offset(north.lat, north.lng, anchor)!)
    expect(p.x).toBeCloseTo(CENTER, 6)
    // The plot is scaled to 1.15 x the furthest thing, so that thing lands
    // at PLOT_RADIUS / 1.15 -- today's frame exactly.
    expect((CENTER - p.y) * 1.15).toBeCloseTo(PLOT_RADIUS, 6)
  })

  it('is centred on the anchor', () => {
    const vp = fit(anchor, [north], noRoute, 8000)
    expect(vp.centerEastM).toBe(0)
    expect(vp.centerNorthM).toBe(0)
    const c = toPoint(vp, square, { eastM: 0, northM: 0 })
    expect(c).toEqual({ x: CENTER, y: CENTER })
  })

  it('falls back to the searched radius with nothing to fit', () => {
    const vp = fit(anchor, [], noRoute, 8000)
    expect(vp.radiusM).toBeCloseTo((8000 * CENTER) / PLOT_RADIUS, 6)
  })
})

describe('viewport geometry', () => {
  const vp: Viewport = { centerEastM: 120, centerNorthM: -340, radiusM: 1500 }

  it('shows exactly radiusM to the nearest edge of a non-square frame', () => {
    const top = toOffset(vp, wide, { x: wide.w / 2, y: 0 })
    const right = toOffset(vp, wide, { x: wide.w, y: wide.h / 2 })
    expect(top.northM - vp.centerNorthM).toBeCloseTo(1500, 6)
    expect(right.eastM - vp.centerEastM).toBeCloseTo(3000, 6)
  })

  it('toOffset inverts toPoint', () => {
    const at = { eastM: -812.5, northM: 2201 }
    const back = toOffset(vp, wide, toPoint(vp, wide, at))
    expect(back.eastM).toBeCloseTo(at.eastM, 6)
    expect(back.northM).toBeCloseTo(at.northM, 6)
  })

  it('pan is a translation: the ground follows the pointer', () => {
    const at = { eastM: 500, northM: 500 }
    const before = toPoint(vp, wide, at)
    const after = toPoint(pan(vp, 40, -25, wide), wide, at)
    expect(after.x - before.x).toBeCloseTo(40, 6)
    expect(after.y - before.y).toBeCloseTo(-25, 6)
  })

  it('zoomAt keeps the ground under the pointer where it is', () => {
    const bounds = { minRadiusM: MIN_RADIUS_M, maxRadiusM: 10_000 }
    const about = { x: 613, y: 87 }
    const ground = toOffset(vp, wide, about)
    for (const factor of [2, 0.5, 1.1]) {
      const zoomed = zoomAt(vp, factor, about, wide, bounds)
      expect(zoomed.radiusM).toBeCloseTo(vp.radiusM / factor, 6)
      const p = toPoint(zoomed, wide, ground)
      expect(p.x).toBeCloseTo(about.x, 6)
      expect(p.y).toBeCloseTo(about.y, 6)
    }
  })

  it('zoomAt stops at the bounds without sliding the view', () => {
    const bounds = { minRadiusM: 1000, maxRadiusM: 2000 }
    const about = { x: 10, y: 10 }
    expect(zoomAt(vp, 4, about, wide, bounds).radiusM).toBe(1000)
    expect(zoomAt(vp, 0.25, about, wide, bounds).radiusM).toBe(2000)
    const atMin = { ...vp, radiusM: 1000 }
    expect(zoomAt(atMin, 3, about, wide, bounds)).toBe(atMin)
  })

  it('bounds the zoom at twice the fitted view and the smallest useful area', () => {
    const fitted = fit(anchor, [place({ id: 'n', lat: 41.9, lng: -87.6252 })], noRoute, 8000)
    expect(zoomBoundsFor(fitted)).toEqual({
      minRadiusM: MIN_RADIUS_M,
      maxRadiusM: fitted.radiusM * 2,
    })
  })
})
