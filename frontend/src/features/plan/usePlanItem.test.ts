import { describe, expect, it } from 'vitest'
import type { ItemStatus, PlanItem } from '@/api/queries'
import { isEditable, isOpenToDecision } from './usePlanItem'

function item(status: ItemStatus): PlanItem {
  return {
    id: 'i1',
    kind: 'meal',
    status,
    title: 'Mildreds Soho',
    starts_at: '2026-09-02T19:00:00Z',
    needs_reservation: true,
    updated_at: '2026-09-01T00:00:00Z',
  }
}

const OPEN: ItemStatus[] = ['suggested', 'awaiting_user', 'planned', 'changed']
const CLOSED: ItemStatus[] = ['confirmed', 'working', 'skipped', 'removed']

describe('isOpenToDecision', () => {
  it('is true at the gates a user can still answer', () => {
    expect(OPEN.filter((s) => isOpenToDecision(item(s)))).toEqual(OPEN)
  })

  it('is false once a booking holds it or the answer is already given', () => {
    expect(CLOSED.filter((s) => isOpenToDecision(item(s)))).toEqual([])
  })
})

describe('isEditable', () => {
  it('matches isOpenToDecision while the trip is still live', () => {
    for (const status of [...OPEN, ...CLOSED]) {
      expect(isEditable(item(status), false)).toBe(isOpenToDecision(item(status)))
    }
  })

  it('refuses every status once the trip is over', () => {
    // The status axis cannot see the trip's tense on its own: London's dinner
    // is `planned` on an archived trip, so isOpenToDecision alone says yes.
    for (const status of [...OPEN, ...CLOSED]) {
      expect(isEditable(item(status), true)).toBe(false)
    }
    expect(isOpenToDecision(item('planned'))).toBe(true)
  })
})
