import { describe, expect, it } from 'vitest'
import type { Plan, PlanItem, Trip } from '@/api/queries'
import {
  retrospectiveStats,
  stageChip,
  stageCopy,
  tripStage,
  windowItems,
  windowsTitle,
} from './tripStage'

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
    state_line: 'Watching your schedule',
    evidence: [],
    updated_at: '2026-08-28T00:00:00Z',
    ...over,
  }
}

function item(over: Partial<PlanItem> = {}): PlanItem {
  return {
    id: 'i1',
    kind: 'activity',
    status: 'suggested',
    title: 'Morning swim',
    starts_at: '2026-09-13T12:00:00Z',
    needs_reservation: false,
    why: [],
    options: [],
    updated_at: '2026-08-28T00:00:00Z',
    ...over,
  }
}

function plan(items: PlanItem[]): Plan {
  return {
    id: 'p1',
    trip_id: 't1',
    version: 1,
    status: 'proposed',
    headline: 'Four windows, one worth booking',
    items,
    updated_at: '2026-08-28T00:00:00Z',
  }
}

describe('tripStage', () => {
  it('reads a finished trip as done whatever its plan says', () => {
    expect(tripStage(trip({ state: 'completed' }), plan([item()]))).toBe('done')
  })

  it('treats a missing plan as waiting, not as a failure', () => {
    expect(tripStage(trip())).toBe('waiting')
  })

  it('treats an empty plan as waiting', () => {
    expect(tripStage(trip(), plan([]))).toBe('waiting')
  })

  it('is proposed while any item still needs a decision', () => {
    expect(
      tripStage(trip(), plan([item({ status: 'planned' }), item({ id: 'i2' })])),
    ).toBe('proposed')
  })

  it('is accepted once nothing is open', () => {
    expect(tripStage(trip(), plan([item({ status: 'planned' })]))).toBe('accepted')
  })
})

describe('stageChip', () => {
  it('defers to the server state_line on lifecycle stages', () => {
    const t = trip({ state_line: 'Confirmed - will start preparing closer to the trip' })
    expect(stageChip(t, 'waiting')).toBe(
      'Confirmed - will start preparing closer to the trip',
    )
  })

  it('counts what is open on a proposed plan', () => {
    expect(stageChip(trip(), 'proposed', plan([item(), item({ id: 'i2' })]))).toBe(
      'Plan ready · 2 to review',
    )
  })

  it('names booking as its own accepted state', () => {
    expect(stageChip(trip({ plan_progress: 'booking' }), 'accepted')).toBe(
      'Plan accepted · booking',
    )
  })
})

describe('stageCopy', () => {
  it('quotes the server on a proposed plan rather than writing its own', () => {
    const p = { ...plan([item()]), provenance_summary: 'Read 11 calendar events' }
    const copy = stageCopy(trip(), 'proposed', p, [])
    expect(copy.head).toBe('Four windows, one worth booking')
    expect(copy.body).toBe('Read 11 calendar events')
  })

  it('says a plan is being built when the trip says it is', () => {
    const copy = stageCopy(trip({ plan_progress: 'preparing' }), 'waiting', undefined, [])
    expect(copy.head).toBe('Your plan is being built')
  })

  it('counts the accepted windows itself, since the headline was for the offer', () => {
    const p = plan([item({ status: 'planned' }), item({ id: 'i2', status: 'removed' })])
    expect(stageCopy(trip(), 'accepted', p, []).head).toBe('1 window is in your plan')
  })

  // The head sits directly above the window list, so it counts that list. Its
  // own filter kept `skipped` and read one higher than the rows beneath it.
  it('leaves skipped windows out of the accepted count, as the list does', () => {
    const p = plan([item({ status: 'planned' }), item({ id: 'i2', status: 'skipped' })])
    expect(stageCopy(trip(), 'accepted', p, []).head).toBe('1 window is in your plan')
  })

  it('reads the retrospective headline off the same numbers as the tiles', () => {
    const stats = [
      { n: 3, label: 'kept' },
      { n: 1, label: 'skipped' },
    ]
    expect(stageCopy(trip(), 'done', undefined, stats).head).toBe('You kept 3 of 4 windows')
  })

  it('says so plainly when nothing was skipped', () => {
    const stats = [
      { n: 3, label: 'kept' },
      { n: 0, label: 'skipped' },
    ]
    expect(stageCopy(trip(), 'done', undefined, stats).head).toBe('You kept every window')
  })

  // A window can fail to be kept without being skipped, and the old test was
  // `skipped === 0` - which called London's failed dinner "every window".
  it('does not call it every window when one could not be booked', () => {
    const stats = [
      { n: 1, label: 'kept' },
      { n: 1, label: 'failed' },
      { n: 0, label: 'skipped' },
    ]
    expect(stageCopy(trip(), 'done', undefined, stats).head).toBe(
      'You kept 1 of 2 windows',
    )
  })

  it('writes no body for a finished trip', () => {
    expect(stageCopy(trip(), 'done', undefined, []).body).toBeUndefined()
  })
})

describe('retrospectiveStats', () => {
  it('counts what stood and what was skipped, and drops removed from both', () => {
    const stats = retrospectiveStats(
      plan([
        item({ id: 'a', status: 'confirmed' }),
        item({ id: 'b', status: 'changed' }),
        item({ id: 'c', status: 'skipped' }),
        item({ id: 'd', status: 'removed' }),
      ]),
    )
    expect(stats).toEqual([
      { n: 2, label: 'kept' },
      { n: 1, label: 'skipped' },
    ])
  })

  it('adds a reservations tile only when a reservation was confirmed', () => {
    const stats = retrospectiveStats(
      plan([
        item({
          id: 'a',
          status: 'confirmed',
          reservation: {
            id: 'r1',
            status: 'confirmed',
            provider: 'travelwell',
            confirmation_code: 'ABC',
            party_size: 2,
          },
        }),
      ]),
    )
    expect(stats.map((s) => s.label)).toEqual(['kept', 'booked', 'skipped'])
  })

  // The status says the window stood; only the reservation knows it never
  // happened. Counting it as kept is what produced "You kept every window"
  // one scroll above a row badged COULDN'T BOOK.
  it('moves a window whose booking failed out of kept and names it', () => {
    const stats = retrospectiveStats(
      plan([
        item({ id: 'a', status: 'planned' }),
        item({
          id: 'b',
          status: 'planned',
          needs_reservation: true,
          reservation: {
            id: 'r1',
            status: 'failed',
            provider: 'opentable',
            party_size: 2,
          },
        }),
      ]),
    )
    expect(stats).toEqual([
      { n: 1, label: 'kept' },
      { n: 1, label: 'failed' },
      { n: 0, label: 'skipped' },
    ])
  })
})

describe('windowItems', () => {
  const p = plan([
    item({ id: 'late', starts_at: '2026-09-14T12:00:00Z' }),
    item({ id: 'skip', status: 'skipped', starts_at: '2026-09-13T13:00:00Z' }),
    item({ id: 'gone', status: 'removed', starts_at: '2026-09-13T14:00:00Z' }),
    item({ id: 'early', starts_at: '2026-09-13T12:00:00Z' }),
  ])

  // Q4's scope: skipped rows leave the live timeline but stay in the record.
  it('hides skipped windows on a live plan', () => {
    expect(windowItems(p, 'proposed').map((i) => i.id)).toEqual(['early', 'late'])
  })

  it('keeps skipped windows in the retrospective', () => {
    expect(windowItems(p, 'done').map((i) => i.id)).toEqual(['early', 'skip', 'late'])
  })

  it('never shows a removed window', () => {
    expect(windowItems(p, 'done').some((i) => i.id === 'gone')).toBe(false)
  })

  it('is empty without a plan', () => {
    expect(windowItems(undefined, 'proposed')).toEqual([])
  })
})

describe('windowsTitle', () => {
  it('names the tense the reader is in', () => {
    expect(windowsTitle('proposed')).toBe('Proposed windows')
    expect(windowsTitle('accepted')).toBe('In your plan')
    expect(windowsTitle('done')).toBe('What happened')
  })
})
