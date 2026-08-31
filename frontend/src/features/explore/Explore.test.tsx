import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ExploreAnchor, ExplorePlace } from '@/api/queries'
import { CategoryChips } from './CategoryChips'
import { PlaceCard } from './PlaceCard'
import { PlaceMap } from './PlaceMap'

/**
 * What this pins: the card says each fact once, a category with nothing in it
 * is visible rather than hidden, the map puts north up and scales to the
 * places it was given rather than to the radius that was searched, and what
 * could not be judged about a place is stated rather than left to look like a
 * poor match.
 */

const anchor: ExploreAnchor = {
  name: 'The Gwen',
  is_hotel: true,
  lat: 41.8924,
  lng: -87.6252,
}

function place(over: Partial<ExplorePlace> = {}): ExplorePlace {
  return {
    id: 'p1',
    kind: 'workout',
    name: 'YMCA',
    amenities: [],
    matched_preferences: [],
    unknown_notes: [],
    ...over,
  }
}

describe('PlaceCard', () => {
  it('gives the walk time once, not in both the corner and the facts', () => {
    render(
      <PlaceCard
        place={place({ walk_minutes: 7, day_pass_cents: 1500 })}
        selected={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getAllByText(/7 min/)).toHaveLength(1)
    expect(screen.getByText(/\$15 day pass/)).toBeTruthy()
  })

  it('states what could not be judged instead of letting it read as a poor match', () => {
    render(
      <PlaceCard
        place={place({
          matched_preferences: ['Swim'],
          unknown_notes: ['Facilities not listed', 'Day-pass price not listed'],
        })}
        selected={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText(/Facilities not listed/)).toBeTruthy()
    expect(screen.getByText(/Day-pass price not listed/)).toBeTruthy()
  })

  it('does not dress an unknown up as a matched preference', () => {
    /* The chips are what the place earned. A note is the absence of an answer,
       so it must not land in the same list or it reads as a fifth match. */
    render(
      <PlaceCard
        place={place({
          matched_preferences: ['Swim'],
          unknown_notes: ['Facilities not listed'],
        })}
        selected={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['Swim'])
  })

  it('says nothing at all when there is nothing unknown', () => {
    render(<PlaceCard place={place()} selected={false} onSelect={() => {}} />)
    expect(screen.queryByText(/not listed/)).toBeNull()
  })

  it('leaves the price to the summary when there is one', () => {
    const { rerender } = render(
      <PlaceCard
        place={place({ summary: 'Healthy American · $$', price_level: 2 })}
        selected={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getAllByText(/\$\$/)).toHaveLength(1)

    // With no summary the price is the only thing that would carry it.
    rerender(
      <PlaceCard
        place={place({ price_level: 2 })}
        selected={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText('$$')).toBeTruthy()
  })

  it('shows why a place is over budget rather than dropping it', () => {
    render(
      <PlaceCard
        place={place({ over_budget_reason: '$60 day pass, above the $20 you set' })}
        selected={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText(/above the \$20 you set/)).toBeTruthy()
  })
})

describe('CategoryChips', () => {
  const kinds = [
    { kind: 'workout' as const, count: 3 },
    { kind: 'recovery' as const, count: 0 },
  ]

  it('totals the categories on the All chip', () => {
    render(<CategoryChips kinds={kinds} selected={undefined} onSelect={() => {}} />)
    expect(screen.getByRole('button', { name: 'All 3' })).toBeTruthy()
  })

  it('shows an empty category as disabled rather than hiding it', () => {
    render(<CategoryChips kinds={kinds} selected={undefined} onSelect={() => {}} />)
    const recovery = screen.getByRole('button', { name: 'Recovery 0' })
    expect(recovery.hasAttribute('disabled')).toBe(true)
  })

  it('a second click on the selected chip clears the filter', async () => {
    const onSelect = vi.fn()
    render(<CategoryChips kinds={kinds} selected="workout" onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('button', { name: 'Workout 3' }))
    expect(onSelect).toHaveBeenCalledWith(undefined)
  })
})

describe('PlaceMap', () => {
  const north = place({ id: 'n', name: 'North', lat: 41.9, lng: -87.6252, distance_meters: 840 })
  const east = place({ id: 'e', name: 'East', lat: 41.8924, lng: -87.61, distance_meters: 1260 })

  function pins(container: HTMLElement) {
    return [...container.querySelectorAll('g.cursor-pointer circle')] as SVGCircleElement[]
  }

  it('puts north above the anchor and east to its right', () => {
    const { container } = render(
      <PlaceMap
        anchor={anchor}
        places={[north, east]}
        radiusM={8000}
        selectedId={null}
        onSelect={() => {}}
      />,
    )
    const at = pins(container).map((c) => ({
      x: Number(c.getAttribute('cx')),
      y: Number(c.getAttribute('cy')),
    }))
    expect(at).toHaveLength(2)
    const [n, e] = at as [(typeof at)[number], (typeof at)[number]]
    expect(n.y).toBeLessThan(160)
    expect(n.x).toBeCloseTo(160, 0)
    expect(e.x).toBeGreaterThan(160)
    expect(e.y).toBeCloseTo(160, 0)
  })

  it('scales to the furthest place, not to the radius searched', () => {
    const { container } = render(
      <PlaceMap
        anchor={anchor}
        places={[north, east]}
        radiusM={8000}
        selectedId={null}
        onSelect={() => {}}
      />,
    )
    // 1.26 km furthest, so the outer ring reads in hundreds of metres rather
    // than the 8 km that was searched.
    const labels = [...container.querySelectorAll('text')].map((t) => t.textContent)
    expect(labels).toContain('1.4 km')
    expect(labels).not.toContain('8.0 km')
  })

  it('a place with no coordinates gets no pin instead of a wrong one', () => {
    const { container } = render(
      <PlaceMap
        anchor={anchor}
        places={[north, place({ id: 'x', name: 'Unlocated' })]}
        radiusM={8000}
        selectedId={null}
        onSelect={() => {}}
      />,
    )
    expect(pins(container)).toHaveLength(1)
  })

  it('names only the selected pin, so the map does not become a word cloud', () => {
    const { container } = render(
      <PlaceMap
        anchor={anchor}
        places={[north, east]}
        radiusM={8000}
        selectedId="n"
        onSelect={() => {}}
      />,
    )
    const svg = container.querySelector('svg')!
    expect(within(svg as unknown as HTMLElement).getByText('North')).toBeTruthy()
    expect(within(svg as unknown as HTMLElement).queryByText('East')).toBeNull()
  })
})
