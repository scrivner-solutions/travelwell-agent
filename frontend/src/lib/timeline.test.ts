import { describe, expect, it } from 'vitest'
import type { ItemStatus, PlanItem } from '@/api/queries'
import { commitmentChrome, itemBadge, reservationNote, rowChromeFor } from './timeline'

const ALL_STATUSES: ItemStatus[] = [
  'suggested',
  'awaiting_user',
  'planned',
  'confirmed',
  'working',
  'changed',
  'skipped',
  'removed',
]

function item(over: Partial<PlanItem> = {}): PlanItem {
  return {
    id: 'i1',
    kind: 'activity',
    status: 'planned',
    title: 'Morning swim',
    starts_at: '2026-09-02T07:15:00Z',
    needs_reservation: false,
    why: [],
    options: [],
    updated_at: '2026-09-01T00:00:00Z',
    ...over,
  }
}

describe('reservationNote for a booking nobody is making', () => {
  // `pending` means "waiting to book" for every other provider. Saying that
  // here would claim work is under way, when the truth is that this place has
  // no booking surface we can reach and the user has to finish it themselves.
  it('names the hand-off rather than implying progress', () => {
    const note = reservationNote(
      item({
        needs_reservation: true,
        reservation: {
          id: 'r1',
          status: 'pending',
          provider: 'external_link',
          party_size: 2,
          external_url: 'https://example.test/book',
        },
      }),
    )
    expect(note?.label).toBe('Book it yourself')
  })

  it('still says waiting to book when we are the ones booking', () => {
    const note = reservationNote(
      item({
        needs_reservation: true,
        reservation: {
          id: 'r1',
          status: 'pending',
          provider: 'travelwell',
          party_size: 2,
        },
      }),
    )
    expect(note?.label).toBe('Waiting to book')
  })
})

describe('itemBadge', () => {
  it('says nothing at any gate the user can still answer', () => {
    for (const status of ['suggested', 'awaiting_user', 'planned'] as const) {
      expect(itemBadge(item({ status }))).toBeNull()
    }
  })

  it('names a booking in flight and a booking made', () => {
    expect(itemBadge(item({ status: 'working', needs_reservation: true }))?.label).toBe(
      'Booking…',
    )
    expect(itemBadge(item({ status: 'confirmed', needs_reservation: true }))?.label).toBe(
      'Booked',
    )
  })

  it('does not call a confirmed item Booked when it never wanted a reservation', () => {
    expect(itemBadge(item({ status: 'confirmed', needs_reservation: false }))).toBeNull()
  })

  it('reports a refused booking over whatever status the item was left at', () => {
    const failed = {
      id: 'r1',
      status: 'failed',
      provider: 'opentable',
    } as PlanItem['reservation']
    for (const status of ALL_STATUSES) {
      expect(itemBadge(item({ status, reservation: failed }))?.label).toBe(
        "Couldn't book",
      )
    }
  })

  it('keeps a word for the spent statuses, which only the retrospective shows', () => {
    expect(itemBadge(item({ status: 'skipped' }))?.label).toBe('Skipped')
    expect(itemBadge(item({ status: 'removed' }))?.label).toBe('Removed')
  })

  it('has four badges on any live surface, and three silences', () => {
    // Every status a live timeline can render, with the reservation each one
    // implies. skipped and removed are absent because the timeline deletes them.
    const live: [ItemStatus, boolean][] = [
      ['suggested', false],
      ['awaiting_user', true],
      ['planned', true],
      ['confirmed', true],
      ['working', true],
      ['changed', false],
    ]
    const labels = live.map(([status, needs_reservation]) =>
      itemBadge(item({ status, needs_reservation }))?.label,
    )
    expect(labels.filter((l) => l === undefined)).toHaveLength(3)
    expect(new Set(labels.filter((l) => l !== undefined))).toEqual(
      new Set(['Booked', 'Booking…', 'Changed']),
    )
    // The fourth is the only one that does not come from a status at all.
    expect(
      itemBadge(
        item({
          status: 'planned',
          reservation: {
            id: 'r',
            status: 'failed',
            provider: 'opentable',
            party_size: 2,
          },
        }),
      )?.label,
    ).toBe("Couldn't book")
  })

})

describe('reservationNote', () => {
  const res = (over: Partial<NonNullable<PlanItem['reservation']>>) =>
    ({ id: 'r1', provider: 'opentable', status: 'pending', ...over }) as PlanItem['reservation']

  it('asks for a table only while there is no reservation', () => {
    expect(reservationNote(item({ needs_reservation: true }))?.label).toBe(
      'Needs a reservation',
    )
    expect(reservationNote(item({ needs_reservation: false }))).toBeNull()
  })

  it('stops asking for a table the item already holds', () => {
    // F10: the sheet read "Needs a reservation" over a row badged Booked.
    const note = reservationNote(
      item({
        status: 'confirmed',
        needs_reservation: true,
        reservation: res({ status: 'confirmed', confirmation_code: '#9K7C2' }),
      }),
    )
    expect(note?.label).toBe('Booked · confirmation #9K7C2')
  })

  it('still says Booked when the confirmation code is missing', () => {
    expect(
      reservationNote(
        item({ needs_reservation: true, reservation: res({ status: 'confirmed' }) }),
      )?.label,
    ).toBe('Booked')
  })

  it('leaves a refusal to the sentence the sheet writes for it', () => {
    expect(
      reservationNote(
        item({ needs_reservation: true, reservation: res({ status: 'failed' }) }),
      ),
    ).toBeNull()
  })

  it('names every other reservation state rather than falling silent', () => {
    const labels = (['pending', 'holding', 'canceled'] as const).map(
      (status) => reservationNote(item({ reservation: res({ status }) }))?.label,
    )
    expect(labels).toEqual(['Waiting to book', 'Holding a table', 'Reservation canceled'])
  })
})

describe('rowChromeFor', () => {
  it('covers every status with a border and a dot', () => {
    for (const status of ALL_STATUSES) {
      const chrome = rowChromeFor(status)
      expect(chrome.frame).toMatch(/border-/)
      expect(chrome.dot).toMatch(/^bg-/)
    }
  })

  it('dashes only the suggestion, which is the one thing not yet real', () => {
    const dashed = ALL_STATUSES.filter((s) => rowChromeFor(s).frame.includes('dashed'))
    expect(dashed).toEqual(['suggested'])
  })

  it('marks the row that needs you with full ink, its only marker now', () => {
    expect(rowChromeFor('awaiting_user').frame).toContain('border-ink')
  })

  it('shares the card border once settled and keeps one darker token for suggestions', () => {
    expect(rowChromeFor('planned').frame).toContain('border-border-confirmed')
    expect(rowChromeFor('suggested').frame).toContain('border-border-row-suggested')
  })

  // Blink floors fractional border widths, so a declared 1.5px paints as 1px
  // and silently means something else in an engine that does not floor.
  it('declares no fractional border widths', () => {
    for (const status of ALL_STATUSES) {
      expect(rowChromeFor(status).frame).not.toMatch(/border-\[[\d.]*\.\d+px\]/)
    }
  })

  it('gives a commitment the muted fill that says the agent did not place it', () => {
    expect(commitmentChrome.frame).toContain('bg-card-muted')
    expect(commitmentChrome.dot).toBe('bg-state-existing')
  })
})
