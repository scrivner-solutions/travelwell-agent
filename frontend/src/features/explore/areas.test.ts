import { describe, expect, it } from 'vitest'
import type { ExploreAnchor } from '@/api/queries'
import { areaCovering, areaKey, bucketRadius, covers, normalizeArea, snap, visibleRect } from './areas'

const anchor: ExploreAnchor = { name: 'The Gwen', is_hotel: true, lat: 41.8924, lng: -87.6252 }

describe('area cells', () => {
  it('snaps exactly as the server does', () => {
    /* The same three points as test_basemap.py, with the values Python
       printed for them. If either side changes its grid, this is the test
       that says so. */
    const chicago = normalizeArea(41.8924, -87.6252, 2000)
    expect(chicago.radius_m).toBe(2000)
    expect(chicago.lat).toBeCloseTo(41.88825008983112, 10)
    expect(chicago.lng).toBeCloseTo(-87.6291089942673, 10)
    const finer = normalizeArea(41.9124, -87.6552, 900)
    expect(finer).toEqual({ lat: expect.closeTo(41.91070786920589, 10), lng: expect.closeTo(-87.65389639576168, 10), radius_m: 1000 })
    const helsinki = normalizeArea(60.17, 24.94, 5500)
    expect(helsinki.lat).toBeCloseTo(60.17786561264822, 10)
    expect(helsinki.lng).toBeCloseTo(24.93657232900258, 10)
  })

  it('a snapped centre snaps to itself', () => {
    const once = snap(41.8924, -87.6252, 2000)
    expect(snap(once.lat, once.lng, 2000)).toEqual(once)
  })

  it('rounds the radius up the ladder', () => {
    expect(bucketRadius(900)).toBe(1000)
    expect(bucketRadius(2000)).toBe(2000)
    expect(bucketRadius(50_000)).toBe(16000)
  })

  it('names a cell by its numbers', () => {
    expect(areaKey({ lat: 41.5, lng: -87.25, radius_m: 2000 })).toBe('41.5,-87.25,2000')
  })
})

describe('coverage', () => {
  const view = { centerEastM: 0, centerNorthM: 0, radiusM: 1000 }

  it('measures the frame in metres, the long side included', () => {
    const rect = visibleRect(view, { w: 360, h: 640 })
    expect(rect.halfWidthM).toBeCloseTo(1000)
    expect(rect.halfHeightM).toBeCloseTo(1000 * (640 / 360))
  })

  it('a cell covers a rect that fits inside its square', () => {
    const cell = { lat: 41.8924, lng: -87.6252, radius_m: 2000 }
    expect(covers(cell, anchor, { centerEastM: 0, centerNorthM: 0, halfWidthM: 1500, halfHeightM: 1900 })).toBe(true)
    expect(covers(cell, anchor, { centerEastM: 600, centerNorthM: 0, halfWidthM: 1500, halfHeightM: 1900 })).toBe(false)
    expect(covers({ lat: null, lng: null, radius_m: 2000 }, anchor, { centerEastM: 0, centerNorthM: 0, halfWidthM: 1, halfHeightM: 1 })).toBe(false)
  })

  it('picks the smallest cell that still covers after snapping', () => {
    const rect = visibleRect(view, { w: 360, h: 640 })
    const area = areaCovering(anchor, rect)
    expect(area).not.toBeNull()
    expect(covers(area!, anchor, rect)).toBe(true)
    const oneDown = bucketRadius(area!.radius_m - 1)
    if (oneDown < area!.radius_m) {
      expect(covers(normalizeArea(41.8924, -87.6252, oneDown), anchor, rect)).toBe(false)
    }
  })

  it('falls back to the widest cell rather than nothing', () => {
    const huge = { centerEastM: 0, centerNorthM: 0, halfWidthM: 40_000, halfHeightM: 40_000 }
    expect(areaCovering(anchor, huge)?.radius_m).toBe(16000)
    expect(areaCovering({ ...anchor, lat: null, lng: null }, huge)).toBeNull()
  })
})
