import { describe, expect, it } from 'vitest'
import type { PlanItem, ReservationStatus } from '@/api/queries'
import { canBook } from './useBooking'

function item(over: Partial<PlanItem> = {}): PlanItem {
  return {
    id: 'i1',
    kind: 'meal',
    status: 'planned',
    title: 'Beatrix',
    starts_at: '2026-09-02T19:30:00Z',
    needs_reservation: true,
    why: [],
    options: [],
    updated_at: '2026-09-01T00:00:00Z',
    ...over,
  }
}

function withReservation(status: ReservationStatus): PlanItem {
  return item({
    reservation: { id: 'r1', status, provider: 'travelwell', party_size: 2 },
  })
}

describe('canBook', () => {
  it('offers a booking for an item that wants one and has none', () => {
    expect(canBook(item(), false)).toBe(true)
  })

  it('offers nothing for an item that never wanted a table', () => {
    expect(canBook(item({ needs_reservation: false }), false)).toBe(false)
  })

  // The gates are ordered: keep, then book. Offering a table on a suggestion
  // nobody has answered would collapse the two into one, and the executor
  // would refuse to move the row anyway.
  it('offers nothing until the item has been kept', () => {
    for (const status of ['suggested', 'awaiting_user'] as const) {
      expect(canBook(item({ status }), false)).toBe(false)
    }
    for (const status of ['planned', 'changed'] as const) {
      expect(canBook(item({ status }), false)).toBe(true)
    }
  })

  // Already on the booking track. `working` is a booking in flight and
  // `confirmed` is one that landed; neither wants a second attempt.
  it('offers nothing while a booking is in flight or already made', () => {
    for (const status of ['working', 'confirmed'] as const) {
      expect(canBook(item({ status }), false)).toBe(false)
    }
  })

  // A finished trip's plan is a record, and the server refuses every mutation
  // on one with 409. Offering the button would be offering a guaranteed error.
  it('offers nothing once the trip is over', () => {
    expect(canBook(item(), true)).toBe(false)
  })

  it('does not offer to book over a booking already in hand', () => {
    for (const status of ['pending', 'holding', 'confirmed'] as const) {
      expect(canBook(withReservation(status), false)).toBe(false)
    }
  })

  // The retry case, and the reason the reservation now carries why it failed:
  // a refusal leaves the window standing and the table unbooked, which is
  // exactly the state a second attempt is for.
  it('offers again after a refusal or a cancellation', () => {
    for (const status of ['failed', 'canceled'] as const) {
      expect(canBook(withReservation(status), false)).toBe(true)
    }
  })
})
