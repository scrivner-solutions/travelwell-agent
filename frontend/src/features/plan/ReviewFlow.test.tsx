import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Plan, PlanItem } from '@/api/queries'
import { ReviewFlow } from './ReviewFlow'

/**
 * The queue behaviour is the whole point of this flow: it walks the items that
 * were open when it opened, in order, and does not renumber itself as
 * decisions land. The summary then reports the plan, not the taps.
 */

const accept = vi.hoisted(() => vi.fn())
const skip = vi.hoisted(() => vi.fn())

vi.mock('@/api/queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/queries')>()),
  acceptPlanItem: accept,
  skipPlanItem: skip,
  selectPlanItemOption: vi.fn(),
}))

function item(
  id: string,
  title: string,
  status: PlanItem['status'],
  needsRes = false,
): PlanItem {
  return {
    id,
    kind: 'activity',
    status,
    title,
    starts_at: '2026-09-19T14:45:00Z',
    updated_at: '2026-08-28T00:00:00Z',
    needs_reservation: needsRes,
    options: [{ id: `${id}-o`, state: 'selected', display_name: title }],
  }
}

function planOf(...items: PlanItem[]): Plan {
  return {
    id: 'plan-1',
    trip_id: 'trip-1',
    version: 1,
    status: 'proposed',
    headline: 'Three openings',
    items,
    updated_at: '2026-08-28T00:00:00Z',
  }
}

function renderFlow(plan: Plan) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  const ui = (p: Plan) => (
    <QueryClientProvider client={client}>
      <ReviewFlow
        onClose={() => {}}
        plan={p}
        tripId="trip-1"
        tripName="Chicago"
        timezone="America/New_York"
        onShowProvenance={() => {}}
      />
    </QueryClientProvider>
  )
  const utils = render(ui(plan))
  // Stands in for the invalidate-and-refetch the mutations trigger.
  return { ...utils, update: (p: Plan) => utils.rerender(ui(p)) }
}

beforeEach(() => {
  accept.mockReset().mockResolvedValue(undefined)
  skip.mockReset().mockResolvedValue(undefined)
})

describe('ReviewFlow', () => {
  const OPEN_A = item('a', 'Asphalt Green', 'awaiting_user')
  const OPEN_B = item('b', 'Dirt Candy', 'suggested', true)
  const SETTLED = item('c', 'Hudson River Greenway', 'planned')

  it('queues only the items still open, and counts them', () => {
    renderFlow(planOf(OPEN_A, SETTLED, OPEN_B))
    expect(screen.getByText('1 of 2')).toBeInTheDocument()
    expect(screen.getByText('Asphalt Green')).toBeInTheDocument()
    expect(screen.queryByText('Hudson River Greenway')).not.toBeInTheDocument()
  })

  it('names the trip in the header', () => {
    renderFlow(planOf(OPEN_A))
    expect(
      screen.getByRole('heading', { name: 'Your Chicago plan' }),
    ).toBeInTheDocument()
  })

  it('advances only once the decision actually lands', async () => {
    renderFlow(planOf(OPEN_A, OPEN_B))
    await userEvent.click(screen.getByRole('button', { name: 'Keep this' }))

    expect(accept).toHaveBeenCalledWith('a', '2026-08-28T00:00:00Z')
    expect(await screen.findByText('2 of 2')).toBeInTheDocument()
    expect(screen.getByText('Dirt Candy')).toBeInTheDocument()
  })

  it('stays put when the server rejects the decision', async () => {
    accept.mockRejectedValue(new Error('boom'))
    renderFlow(planOf(OPEN_A, OPEN_B))
    await userEvent.click(screen.getByRole('button', { name: 'Keep this' }))

    // A conflict has to stay readable; skipping past it would hide the reason.
    expect(await screen.findByText(/Could not save that/)).toBeInTheDocument()
    expect(screen.getByText('1 of 2')).toBeInTheDocument()
  })

  it('opens straight on the summary when nothing is open', () => {
    renderFlow(planOf(SETTLED, item('d', 'Beatrix', 'skipped')))
    expect(screen.getByText('Summary')).toBeInTheDocument()
    expect(screen.queryByText(/of 0/)).not.toBeInTheDocument()
  })

  it('summarises off the refreshed plan, not off the taps', async () => {
    const { update } = renderFlow(planOf(OPEN_A, OPEN_B))
    await userEvent.click(screen.getByRole('button', { name: 'Keep this' }))
    expect(await screen.findByText('2 of 2')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Skip this' }))

    // The invalidation lands and the plan comes back with the new statuses.
    update(
      planOf(
        item('a', 'Asphalt Green', 'planned'),
        item('b', 'Dirt Candy', 'skipped', true),
      ),
    )

    expect(
      await screen.findByRole('heading', { name: '1 addition across 1 day' }),
    ).toBeInTheDocument()
    expect(screen.getByText('1 morning. 1 skipped.')).toBeInTheDocument()
    // The skipped item is not listed as something the plan gained.
    expect(screen.queryByText('Dirt Candy')).not.toBeInTheDocument()
  })

  it('names the reservations the kept items still need', async () => {
    const { update } = renderFlow(planOf(OPEN_B))
    await userEvent.click(screen.getByRole('button', { name: 'Keep this' }))
    update(planOf(item('b', 'Dirt Candy', 'planned', true)))

    expect(
      await screen.findByText('1 reservation to confirm'),
    ).toBeInTheDocument()
    expect(screen.getByText('Reservation')).toBeInTheDocument()
  })

  it('says so plainly when everything was skipped', async () => {
    const { update } = renderFlow(planOf(OPEN_A))
    await userEvent.click(screen.getByRole('button', { name: 'Skip this' }))
    update(planOf(item('a', 'Asphalt Green', 'skipped')))

    expect(
      await screen.findByRole('heading', { name: 'Nothing left in this plan' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
  })
})
