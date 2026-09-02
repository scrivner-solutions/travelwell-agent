import { describe, expect, it } from 'vitest'
import type { ExplorePlace } from '@/api/queries'
import {
  DEFAULT_FILTERS,
  activeCount,
  constraintLine,
  openThrough,
  passes,
  windowRange,
  type Filters,
} from './filters'

/* Filters mirror the prototype's `passes`, with the app's own rule on top:
 * what the provider never said keeps a place in, it never hides it. */

const TZ = 'America/Chicago'
// A Wednesday at 3 PM in Chicago (CDT, UTC-5).
const AFTERNOON = new Date('2026-09-02T20:00:00Z')
// The same day at 10:30 PM.
const LATE = new Date('2026-09-03T03:30:00Z')

function place(over: Partial<ExplorePlace> = {}): ExplorePlace {
  return {
    id: 'p',
    kind: 'workout',
    name: 'Gym',
    amenities: null,
    matched_preferences: [],
    unknown_notes: [],
    hours: { wed: [6 * 60, 22 * 60] },
    walk_minutes: 8,
    day_pass_cents: 2500,
    ...over,
  }
}

const prefs = { dayPassBudgetCents: 3000, amenities: ['pool', 'sauna'] }
const ctx = { prefs, now: AFTERNOON, timezone: TZ }
const f = (over: Partial<Filters> = {}): Filters => ({ ...DEFAULT_FILTERS, ...over })

describe('windowRange', () => {
  it('reads the trip clock, not the device clock', () => {
    expect(windowRange('now', AFTERNOON, TZ)).toEqual([15 * 60, 16 * 60])
    expect(windowRange('next2h', AFTERNOON, TZ)).toEqual([15 * 60, 17 * 60])
    expect(windowRange('now', AFTERNOON, 'Asia/Tokyo')).toEqual([5 * 60, 6 * 60])
  })

  it('this evening is six till ten, and is over after ten', () => {
    expect(windowRange('evening', AFTERNOON, TZ)).toEqual([18 * 60, 22 * 60])
    expect(windowRange('evening', LATE, TZ)).toBeNull()
  })

  it('stops at midnight rather than asking for tomorrow', () => {
    expect(windowRange('next2h', LATE, TZ)).toEqual([22 * 60 + 30, 24 * 60])
  })
})

describe('openThrough', () => {
  const range: [number, number] = [15 * 60, 17 * 60]
  it('needs the place open for the whole window', () => {
    expect(openThrough({ wed: [6 * 60, 22 * 60] }, range, AFTERNOON, TZ)).toBe(true)
    expect(openThrough({ wed: [6 * 60, 16 * 60] }, range, AFTERNOON, TZ)).toBe(false)
    expect(openThrough({ wed: [16 * 60, 22 * 60] }, range, AFTERNOON, TZ)).toBe(false)
  })
  it('a day missing from known hours is closed; unknown hours are unknown', () => {
    expect(openThrough({ thu: [6 * 60, 22 * 60] }, range, AFTERNOON, TZ)).toBe(false)
    expect(openThrough(null, range, AFTERNOON, TZ)).toBeNull()
  })
})

describe('passes', () => {
  it('lets a place through on the defaults', () => {
    expect(passes(place(), f(), ctx)).toBe(true)
  })

  it('drops a place that closes inside the window', () => {
    expect(passes(place({ hours: { wed: [6 * 60, 16 * 60] } }), f(), ctx)).toBe(false)
    expect(passes(place({ hours: { wed: [6 * 60, 16 * 60] } }), f({ window: 'now' }), ctx)).toBe(true)
  })

  it('this evening after ten drops everything, even the unknowns', () => {
    expect(passes(place({ hours: null }), f({ window: 'evening' }), { ...ctx, now: LATE })).toBe(false)
  })

  it('walk at most', () => {
    expect(passes(place({ walk_minutes: 12 }), f({ walk: 10 }), ctx)).toBe(false)
    expect(passes(place({ walk_minutes: 10 }), f({ walk: 10 }), ctx)).toBe(true)
  })

  it('stays under the pass cap, with a free place always under it', () => {
    expect(passes(place({ day_pass_cents: 3500 }), f({ underCap: true }), ctx)).toBe(false)
    expect(passes(place({ day_pass_cents: 3000 }), f({ underCap: true }), ctx)).toBe(true)
    expect(passes(place({ day_pass_cents: 0 }), f({ underCap: true }), ctx)).toBe(true)
  })

  it('the cap toggle is inert without a cap in the profile', () => {
    const noCap = { ...ctx, prefs: { ...prefs, dayPassBudgetCents: null } }
    expect(passes(place({ day_pass_cents: 9900 }), f({ underCap: true }), noCap)).toBe(true)
    expect(passes(place({ day_pass_cents: 9900 }), f({ underCap: true }), { ...ctx, prefs: undefined })).toBe(true)
  })

  it('must have my amenities means at least one of them', () => {
    expect(passes(place({ amenities: ['treadmill'] }), f({ amenities: true }), ctx)).toBe(false)
    expect(passes(place({ amenities: ['treadmill', 'sauna'] }), f({ amenities: true }), ctx)).toBe(true)
  })

  it('unknown keeps: hours, walk, price and amenities the provider never gave', () => {
    const unknown = place({ hours: null, walk_minutes: null, day_pass_cents: null, amenities: null })
    const everything = f({ window: 'now', walk: 5, underCap: true, amenities: true })
    expect(passes(unknown, everything, ctx)).toBe(true)
    expect(passes(place({ amenities: [] }), f({ amenities: true }), ctx)).toBe(true)
  })
})

describe('activeCount and constraintLine', () => {
  it('counts only what is off its default', () => {
    expect(activeCount(f())).toBe(0)
    expect(activeCount(f({ window: 'now', walk: 10, underCap: true, amenities: true }))).toBe(4)
  })

  it('names the count, the window, and only what narrows it', () => {
    expect(constraintLine(4, f())).toBe('4 places · next 2 hrs')
    expect(constraintLine(1, f({ walk: 10 }))).toBe('1 place · next 2 hrs · under 10 min walk')
    expect(constraintLine(0, f({ window: 'evening', underCap: true, amenities: true }))).toBe(
      '0 places · this evening · under your pass cap · with your amenities',
    )
  })
})
