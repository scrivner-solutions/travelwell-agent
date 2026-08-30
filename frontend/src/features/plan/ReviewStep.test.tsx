import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { PlanItem } from '@/api/queries'
import { ReviewStep } from './ReviewStep'

/**
 * What this pins: the opening leads, every option is on screen at once, and
 * the gates disappear rather than sitting there dead once an item is settled.
 */

const choose = vi.hoisted(() => vi.fn())

vi.mock('@/api/queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/queries')>()),
  acceptPlanItem: vi.fn(),
  skipPlanItem: vi.fn(),
  selectPlanItemOption: choose,
}))

const SELECTED = {
  id: 'opt-sel',
  state: 'selected' as const,
  display_name: 'YMCA',
  display_summary: 'Pool + treadmill · 75 min',
  reason: 'Fits your 90-minute opening',
  distance_minutes: 7,
  matched_preferences: [],
}
const ALTERNATIVE = {
  id: 'opt-alt',
  state: 'alternative' as const,
  display_name: 'Hotel fitness room',
  distance_minutes: 0,
  matched_preferences: [],
}

const ITEM: PlanItem = {
  id: 'item-1',
  kind: 'activity',
  status: 'suggested',
  title: 'YMCA',
  starts_at: '2026-09-19T21:30:00Z',
  updated_at: '2026-08-28T00:00:00Z',
  needs_reservation: false,
  why: [],
  window: {
    id: 'w-1',
    status: 'open',
    starts_at: '2026-09-19T21:30:00Z',
    ends_at: '2026-09-19T23:00:00Z',
    label: '90 minutes free',
    gap_explanation: 'Between your workshop and dinner.',
    bounds: [],
  },
  options: [SELECTED, ALTERNATIVE],
}

function renderStep(item: PlanItem) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ReviewStep
        item={item}
        tripId="trip-1"
        timezone="America/New_York"
        onShowProvenance={() => {}}
        onDecided={() => {}}
      />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  choose.mockReset().mockResolvedValue(undefined)
})

describe('ReviewStep', () => {
  it('leads with the opening, not with the place', () => {
    renderStep(ITEM)
    // The window is the argument for the suggestion, so it is the heading.
    expect(
      screen.getByRole('heading', { name: '90 minutes free' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Between your workshop and dinner.')).toBeInTheDocument()
  })

  it('shows every option at once so they can be compared', () => {
    renderStep(ITEM)
    const options = screen.getAllByRole('radio')
    expect(options.map((o) => o.textContent)).toEqual([
      expect.stringContaining('YMCA'),
      expect.stringContaining('Hotel fitness room'),
    ])
    // The selection is marked, not hidden behind a toggle.
    expect(options[0]).toHaveAttribute('aria-checked', 'true')
    expect(options[1]).toHaveAttribute('aria-checked', 'false')
  })

  it('promotes an alternative with the item token', async () => {
    renderStep(ITEM)
    await userEvent.click(screen.getByRole('radio', { name: /Hotel fitness room/ }))
    expect(choose).toHaveBeenCalledWith('item-1', 'opt-alt', '2026-08-28T00:00:00Z')
  })

  it('does not re-post the option already selected', async () => {
    renderStep(ITEM)
    await userEvent.click(screen.getByRole('radio', { name: /YMCA/ }))
    expect(choose).not.toHaveBeenCalled()
  })

  it('flags an item that still needs a booking', () => {
    renderStep({ ...ITEM, needs_reservation: true })
    expect(screen.getByText('Needs a reservation')).toBeInTheDocument()
  })

  it('drops the gates once a booking holds the item', () => {
    // A dead control with no explanation reads as broken, so they go entirely.
    renderStep({ ...ITEM, status: 'working' })
    expect(screen.queryByRole('button', { name: 'Keep this' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Skip this' })).not.toBeInTheDocument()
    expect(screen.queryAllByRole('radio')).toHaveLength(0)
  })

  it('keeps Skip but drops Keep for an item already in the plan', () => {
    renderStep({ ...ITEM, status: 'planned' })
    expect(screen.queryByRole('button', { name: 'Keep this' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Skip this' })).toBeInTheDocument()
  })

  it('falls back to the time when the item fills no opening', () => {
    renderStep({ ...ITEM, window: undefined })
    expect(screen.getByRole('heading', { name: '5:30 PM, free' })).toBeInTheDocument()
  })

  it('names the meal rather than calling the evening free', () => {
    // A dinner fills no gap the agent had to find, so "free" would be wrong.
    renderStep({
      ...ITEM,
      kind: 'meal',
      window: undefined,
      starts_at: '2026-09-19T23:30:00Z',
    })
    expect(
      screen.getByRole('heading', { name: 'Dinner at 7:30 PM' }),
    ).toBeInTheDocument()
  })
})
