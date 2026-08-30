import { describe, expect, it } from 'vitest'
import type { Trip } from '@/api/queries'
import {
  calendarSpan,
  evidenceKindSummary,
  evidenceSourceSummary,
  isPast,
  needsYouLabel,
  openingDay,
  tripBadge,
} from './trips'

function trip(over: Partial<Trip> = {}): Trip {
  return {
    id: 't1',
    state: 'confirmed',
    origin: 'calendar_detection',
    destination_name: 'Austin, TX',
    timezone: 'America/Chicago',
    starts_on: '2026-09-12',
    ends_on: '2026-09-15',
    plan_progress: 'none',
    needs_you_count: 0,
    updated_at: '2026-08-28T00:00:00Z',
    ...over,
  }
}

describe('calendarSpan', () => {
  it('pads a mid-week range out to Sunday-to-Saturday', () => {
    // 2026-09-09 is a Wednesday, 2026-09-12 already a Saturday.
    const span = calendarSpan('2026-09-09', '2026-09-12')
    expect(span[0]).toBe('2026-09-06')
    expect(span[span.length - 1]).toBe('2026-09-12')
    expect(span).toHaveLength(7)
  })

  it('crosses month boundaries without skipping days', () => {
    // 2026-08-30 is a Sunday; the closing Saturday lands in September.
    const span = calendarSpan('2026-08-30', '2026-09-02')
    expect(span[0]).toBe('2026-08-30')
    expect(span[span.length - 1]).toBe('2026-09-05')
    expect(span).toContain('2026-08-31')
    expect(span).toContain('2026-09-01')
    expect(span).toHaveLength(7)
  })

  it('keeps a single day inside one full week', () => {
    const span = calendarSpan('2026-08-25', '2026-08-25')
    expect(span[0]).toBe('2026-08-23')
    expect(span[span.length - 1]).toBe('2026-08-29')
    expect(span).toHaveLength(7)
  })
})

describe('collapsed evidence copy', () => {
  it('joins deduped sources into a natural list', () => {
    expect(
      evidenceSourceSummary([
        { source: 'google_calendar' },
        { source: 'gmail' },
        { source: 'google_calendar' },
      ]),
    ).toBe('calendar and email')
    expect(evidenceSourceSummary([{ source: 'google_calendar' }])).toBe('calendar')
  })

  it('summarizes kinds as capitalized plain words with a fallback', () => {
    expect(
      evidenceKindSummary([
        { kind: 'flight_event' },
        { kind: 'hotel_email' },
        { kind: 'conference_event' },
      ]),
    ).toBe('Flight, hotel and conference')
    expect(evidenceKindSummary([{ kind: 'something_new' }])).toBe('Calendar item')
  })
})

describe('tripBadge', () => {
  it('says nothing for a confirmed trip with no plan yet', () => {
    // Silence is the honest rendering of "nothing has happened and nothing
    // should have"; badging the default is what produced eight words before.
    expect(tripBadge(trip())).toBeNull()
  })

  it('marks working states with a trailing ellipsis', () => {
    // The ellipsis, not the hue, is what tells you the badge will change on
    // its own -- it survives greyscale and needs no legend.
    expect(tripBadge(trip({ plan_progress: 'preparing' }))?.label).toBe('Preparing…')
    expect(tripBadge(trip({ plan_progress: 'booking' }))?.label).toBe('Booking…')
  })

  it('marks an accepted plan as a settled fact', () => {
    const badge = tripBadge(trip({ plan_progress: 'planned' }))
    expect(badge?.label).toBe('Planned')
    expect(badge?.label.endsWith('…')).toBe(false)
  })

  it('lets Now outrank the plan rollup', () => {
    // Being on the trip is the one thing no date on the row can tell you.
    expect(tripBadge(trip({ state: 'active', plan_progress: 'booking' }))?.label).toBe(
      'Now',
    )
  })

  it('drops the badge once a trip is over', () => {
    // The Past section already says where it sits, and "Planned" about a trip
    // that already happened is noise.
    expect(tripBadge(trip({ state: 'completed', plan_progress: 'planned' }))).toBeNull()
  })
})

describe('needsYouLabel', () => {
  it('stays silent when nothing is open', () => {
    expect(needsYouLabel(0)).toBeNull()
    expect(needsYouLabel(0, 'plan')).toBeNull()
  })

  it('names the gate when the open work is all one kind', () => {
    expect(needsYouLabel(3, 'plan')).toBe('Plan ready')
    expect(needsYouLabel(2, 'approval')).toBe('2 to approve')
  })

  it('falls back to the count when two gates are open at once', () => {
    // No single phrase covers both honestly, so it counts instead of guessing.
    expect(needsYouLabel(3, 'mixed')).toBe('3 items need you')
    expect(needsYouLabel(1)).toBe('1 item needs you')
  })
})

describe('isPast', () => {
  it('routes ended trips to their own section', () => {
    expect(isPast(trip({ state: 'completed' }))).toBe(true)
    expect(isPast(trip({ state: 'archived' }))).toBe(true)
    expect(isPast(trip({ state: 'active' }))).toBe(false)
    expect(isPast(trip())).toBe(false)
  })
})

describe('openingDay', () => {
  const days = ['2026-09-12', '2026-09-13', '2026-09-14', '2026-09-15']
  const on = (...withEntries: string[]) => (d: string) => withEntries.includes(d)

  it('opens a running trip on today even when today is empty', () => {
    expect(
      openingDay({
        days,
        todayIso: '2026-09-13',
        dayHasEntries: on('2026-09-14'),
        timelinePending: false,
      }),
    ).toBe('2026-09-13')
  })

  it('selects nothing until the timeline can say where the entries are', () => {
    expect(
      openingDay({
        days,
        todayIso: '2026-10-01',
        dayHasEntries: on(),
        timelinePending: true,
      }),
    ).toBeUndefined()
  })

  it('skips an empty arrival day to the first day with something on it', () => {
    expect(
      openingDay({
        days,
        todayIso: '2026-10-01',
        dayHasEntries: on('2026-09-14', '2026-09-15'),
        timelinePending: false,
      }),
    ).toBe('2026-09-14')
  })

  it('falls back to day one when the whole trip is empty', () => {
    expect(
      openingDay({
        days,
        todayIso: '2026-10-01',
        dayHasEntries: on(),
        timelinePending: false,
      }),
    ).toBe('2026-09-12')
  })

  it('opens on a red-eye day that sits before the trip range', () => {
    expect(
      openingDay({
        days: ['2026-09-11', ...days],
        todayIso: '2026-10-01',
        dayHasEntries: on('2026-09-11', '2026-09-14'),
        timelinePending: false,
      }),
    ).toBe('2026-09-11')
  })
})
