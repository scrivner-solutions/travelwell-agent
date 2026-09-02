import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterSheet } from './FilterSheet'
import { FiltersButton } from './FiltersButton'
import { DEFAULT_FILTERS } from './filters'

/* The sheet applies as you touch it and only reports; its two profile-backed
 * toggles say what is missing instead of looking broken. */
describe('FilterSheet', () => {
  const prefs = { dayPassBudgetCents: 3000, amenities: ['pool', 'sauna'] }

  function open(over: Partial<Parameters<typeof FilterSheet>[0]> = {}) {
    const onChange = vi.fn()
    const onClose = vi.fn()
    render(
      <FilterSheet
        open
        onClose={onClose}
        filters={DEFAULT_FILTERS}
        onChange={onChange}
        prefs={prefs}
        count={4}
        onStandingPreferences={() => {}}
        {...over}
      />,
    )
    return { onChange, onClose }
  }

  it('shows the current state and applies a change at once', async () => {
    const { onChange } = open()
    expect(screen.getByRole('button', { name: 'Next 2 hrs' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Any' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'This evening' }))
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_FILTERS, window: 'evening' })
    await userEvent.click(screen.getByRole('button', { name: '10 min' }))
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_FILTERS, walk: 10 })
  })

  it('reads the cap and amenities from the profile', async () => {
    const { onChange } = open()
    const cap = screen.getByRole('switch', { name: 'Stay under my $30 pass cap' })
    expect(cap).toBeEnabled()
    expect(screen.getByText('Hides day passes above the cap')).toBeInTheDocument()
    await userEvent.click(cap)
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_FILTERS, underCap: true })
    expect(screen.getByText('pool · sauna')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Must have my amenities' })).toBeEnabled()
  })

  it('says what the profile is missing rather than looking broken', () => {
    open({ prefs: { dayPassBudgetCents: null, amenities: [] } })
    expect(screen.getByRole('switch', { name: 'Stay under my pass cap' })).toBeDisabled()
    expect(screen.getByText('Set a pass cap in your profile')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'Must have my amenities' })).toBeDisabled()
    expect(screen.getByText('None set yet')).toBeInTheDocument()
  })

  it('resets to the defaults and the apply button only counts and closes', async () => {
    const { onChange, onClose } = open({ filters: { ...DEFAULT_FILTERS, walk: 5, amenities: true } })
    await userEvent.click(screen.getByRole('button', { name: 'Reset' }))
    expect(onChange).toHaveBeenCalledWith(DEFAULT_FILTERS)
    await userEvent.click(screen.getByRole('button', { name: 'Show 4 places' }))
    expect(onClose).toHaveBeenCalled()
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('counts one place in the singular', () => {
    open({ count: 1 })
    expect(screen.getByRole('button', { name: 'Show 1 place' })).toBeInTheDocument()
  })
})

describe('FiltersButton', () => {
  it('wears the number of filters on, and nothing when none are', () => {
    const { rerender } = render(<FiltersButton count={0} onClick={() => {}} />)
    expect(screen.getByRole('button')).toHaveTextContent(/^Filters$/)
    rerender(<FiltersButton count={2} onClick={() => {}} />)
    expect(screen.getByRole('button')).toHaveTextContent('Filters · 2')
  })
})
