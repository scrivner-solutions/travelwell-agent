import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AgentScreen } from './AgentScreen'

/**
 * What this pins: the traveler's own words stay on screen, the agent's answer
 * is rendered rather than a canned one, and a turn that changed nothing says so
 * instead of showing an empty result list that reads like a failure.
 */

const ask = vi.hoisted(() => vi.fn())
const trips = vi.hoisted(() => vi.fn())
const plan = vi.hoisted(() => vi.fn())

// The profile button is a router Link, and this screen is rendered without a
// router. Mocking it keeps the test about the agent surface rather than routing.
vi.mock('@/components/ui/ProfileButton', () => ({
  ProfileButton: () => null,
}))

vi.mock('@/api/queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/queries')>()
  return {
    ...actual,
    askAssistant: ask,
    tripsQueryOptions: () => ({ queryKey: ['trips', 'all'], queryFn: trips }),
    planQueryOptions: (tripId: string) => ({
      queryKey: ['trips', tripId, 'plan'],
      queryFn: plan,
    }),
  }
})

const TRIP = {
  id: 'trip-1',
  destination_name: 'Chicago',
  timezone: 'America/Chicago',
  starts_on: '2026-09-09',
  ends_on: '2026-09-10',
  state: 'confirmed',
  updated_at: '2026-08-28T00:00:00Z',
}

const ITEM = { id: 'item-1', status: 'awaiting_user', title: 'Hotel gym' }

function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <AgentScreen />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  ask.mockReset()
  trips.mockReset().mockResolvedValue([TRIP])
  plan.mockReset().mockResolvedValue({ items: [ITEM] })
})

describe('AgentScreen', () => {
  it('sends what the traveler typed and shows the agent’s own answer', async () => {
    ask.mockResolvedValue({
      run_id: 'run-1',
      reply: 'The gym is off today’s plan.',
      applied: [{ item_id: 'item-1', name: 'Hotel gym', status: 'skipped' }],
    })
    renderScreen()

    const box = await screen.findByLabelText('What would you like changed?')
    await userEvent.type(box, 'I am wiped, drop the gym today')
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => expect(ask).toHaveBeenCalledTimes(1))
    // The trip, the words, and an idempotency key the caller minted.
    expect(ask.mock.calls[0][0]).toBe('trip-1')
    expect(ask.mock.calls[0][1]).toBe('I am wiped, drop the gym today')
    expect(ask.mock.calls[0][2]).toEqual(expect.any(String))

    expect(
      await screen.findByText('I am wiped, drop the gym today'),
    ).toBeInTheDocument()
    expect(await screen.findByText('The gym is off today’s plan.')).toBeInTheDocument()
    expect(screen.getByText('Hotel gym')).toBeInTheDocument()
    expect(screen.getByText('Skipped')).toBeInTheDocument()
  })

  it('a turn that changed nothing says so and lists nothing', async () => {
    ask.mockResolvedValue({
      run_id: 'run-2',
      reply: 'Nothing on this plan matches that.',
      applied: [],
    })
    renderScreen()

    await userEvent.click(
      await screen.findByRole('button', { name: 'I am tired today, skip the gym' }),
    )

    expect(
      await screen.findByText('Nothing on this plan matches that.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Skipped')).not.toBeInTheDocument()
  })

  it('says nothing changed when the turn never reached the agent', async () => {
    ask.mockRejectedValue(new Error('502'))
    renderScreen()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Drop the last thing on my plan' }),
    )

    expect(
      await screen.findByText(/nothing on the plan changed/i),
    ).toBeInTheDocument()
  })

  it('offers nothing to say when every trip has ended', async () => {
    // `focusTrip` only returns a live trip, so a finished one reaches this
    // screen as no trip at all rather than as a trip that refuses to change.
    trips.mockResolvedValue([{ ...TRIP, state: 'completed' }])
    renderScreen()

    expect(await screen.findByText('No trip to change right now')).toBeInTheDocument()
    expect(screen.queryByLabelText('What would you like changed?')).not.toBeInTheDocument()
    expect(ask).not.toHaveBeenCalled()
  })
})
