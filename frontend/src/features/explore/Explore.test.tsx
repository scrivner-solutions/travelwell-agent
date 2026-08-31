import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ExploreAnchor, ExplorePlace, ExploreRoute } from '@/api/queries'
import { CategoryChips } from './CategoryChips'
import { PlaceCard } from './PlaceCard'
import { PlaceMap } from './PlaceMap'
import { hoursLabel } from './hours'

/**
 * What this pins: the card says each fact once, a category with nothing in it
 * is visible rather than hidden, the map puts north up and scales to the
 * places it was given rather than to the radius that was searched, what could
 * not be judged about a place is stated rather than left to look like a poor
 * match, and opening hours are read against the trip's clock.
 */

const TZ = 'America/Chicago'

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
        timezone={TZ}
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
        timezone={TZ}
        selected={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText(/Facilities not listed/)).toBeTruthy()
    expect(screen.getByText(/Day-pass price not listed/)).toBeTruthy()
  })

  it('does not dress an unknown up as a matched preference', () => {
    /* The periwinkle line is what the place earned. A note is the absence of
       an answer, so it must not join that line or it reads as another match. */
    render(
      <PlaceCard
        place={place({
          matched_preferences: ['Swim'],
          unknown_notes: ['Facilities not listed'],
        })}
        timezone={TZ}
        selected={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText('Swim').textContent).toBe('Swim')
    expect(screen.getByText('Facilities not listed').textContent).toBe('Facilities not listed')
  })

  it('says nothing at all when there is nothing unknown', () => {
    render(
      <PlaceCard place={place()} timezone={TZ} selected={false} onSelect={() => {}} />,
    )
    expect(screen.queryByText(/not listed/)).toBeNull()
  })

  it('leaves the price to the summary when there is one', () => {
    const { rerender } = render(
      <PlaceCard
        place={place({ summary: 'Healthy American · $$', price_level: 2 })}
        timezone={TZ}
        selected={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getAllByText(/\$\$/)).toHaveLength(1)

    // With no summary the price is the only thing that would carry it.
    rerender(
      <PlaceCard
        place={place({ price_level: 2 })}
        timezone={TZ}
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
        timezone={TZ}
        selected={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText(/above the \$20 you set/)).toBeTruthy()
  })

  it('badges the hours the design leads with, when we were told them', () => {
    // Monday 1:00 PM in Chicago, against a place open 6 AM to 10 PM.
    vi.setSystemTime(new Date('2026-08-31T18:00:00Z'))
    render(
      <PlaceCard
        place={place({ hours: { mon: [360, 1320] } })}
        timezone={TZ}
        selected={false}
        onSelect={() => {}}
      />,
    )
    expect(screen.getByText('Open till 10 PM')).toBeTruthy()
    vi.useRealTimers()
  })

  it('shows no hours badge at all when the provider never gave us any', () => {
    render(
      <PlaceCard place={place()} timezone={TZ} selected={false} onSelect={() => {}} />,
    )
    expect(screen.queryByText(/Open|Closed/)).toBeNull()
  })
})

describe('hoursLabel', () => {
  // Monday, 1:00 PM in Chicago.
  const now = new Date('2026-08-31T18:00:00Z')

  it('reads the trip clock, not the device clock', () => {
    /* The same instant is already Tuesday in Tokyo, so a Monday-only place is
       shut there. This is the whole reason the trip zone is a parameter. */
    expect(hoursLabel({ mon: [360, 1320] }, TZ, now)?.text).toBe('Open till 10 PM')
    expect(hoursLabel({ mon: [360, 1320] }, 'Asia/Tokyo', now)?.text).toBe('Closed today')
  })

  it('separates "never told us" from "closed"', () => {
    expect(hoursLabel(null, TZ, now)).toBeNull()
    expect(hoursLabel({ tue: [360, 1320] }, TZ, now)).toEqual({
      text: 'Closed today',
      tight: true,
    })
  })

  it('marks closing soon, already shut, and not open yet as tight', () => {
    expect(hoursLabel({ mon: [360, 840] }, TZ, now)).toEqual({
      text: 'Closes in 60 min',
      tight: true,
    })
    expect(hoursLabel({ mon: [360, 600] }, TZ, now)?.text).toBe('Closed now')
    expect(hoursLabel({ mon: [900, 1320] }, TZ, now)?.text).toBe('Opens 3 PM')
  })

  it('says 24 hours rather than "open till midnight"', () => {
    expect(hoursLabel({ mon: [0, 1440] }, TZ, now)).toEqual({
      text: 'Open 24 hours',
      tight: false,
    })
  })
})

describe('CategoryChips', () => {
  const kinds = [
    { kind: 'workout' as const, count: 3 },
    { kind: 'food' as const, count: 0 },
  ]

  it('totals the categories on the All chip', () => {
    render(<CategoryChips kinds={kinds} selected={undefined} onSelect={() => {}} />)
    expect(screen.getByRole('button', { name: 'All 3' })).toBeTruthy()
  })

  it('shows an empty category as disabled rather than hiding it', () => {
    render(<CategoryChips kinds={kinds} selected={undefined} onSelect={() => {}} />)
    expect(screen.getByRole('button', { name: 'Food 0' }).getAttribute('disabled')).not.toBeNull()
  })

  it('a second click on the selected chip clears the filter', async () => {
    const onSelect = vi.fn()
    render(<CategoryChips kinds={kinds} selected="workout" onSelect={onSelect} />)
    await userEvent.click(screen.getByRole('button', { name: 'Workout 3' }))
    expect(onSelect).toHaveBeenCalledWith(undefined)
  })
})

describe('PlaceMap', () => {
  const north = place({ id: 'n', name: 'North', lat: 41.9, lng: -87.6252, distance_meters: 840, walk_minutes: 7 })
  const east = place({ id: 'e', name: 'East', lat: 41.8924, lng: -87.61, distance_meters: 1260 })

  const noRoute: ExploreRoute = { stops: [], total_minutes: null }
  const anchorStop = {
    name: 'The Gwen',
    lat: 41.8924,
    lng: -87.6252,
    is_anchor: true,
    walk_minutes: null,
  }
  const routeToNorth: ExploreRoute = {
    stops: [anchorStop, { name: 'North', lat: 41.9, lng: -87.6252, is_anchor: false, walk_minutes: 11 }],
    total_minutes: 11,
  }

  function draw(over: Partial<ComponentProps<typeof PlaceMap>> = {}) {
    return render(
      <PlaceMap
        anchor={anchor}
        places={[north, east]}
        route={noRoute}
        radiusM={8000}
        timezone={TZ}
        selectedId={null}
        onSelect={() => {}}
        onOpen={() => {}}
        {...over}
      />,
    )
  }

  /** The place pins, which are the only aria-pressed buttons on the map. */
  function pins(container: HTMLElement) {
    return [...container.querySelectorAll('button[aria-pressed]')] as HTMLElement[]
  }

  function at(el: HTMLElement) {
    return { x: Number.parseFloat(el.style.left), y: Number.parseFloat(el.style.top) }
  }

  const lines = (container: HTMLElement) => [...container.querySelectorAll('polyline')]
  const route = (container: HTMLElement) =>
    lines(container).find((l) => l.getAttribute('stroke-dasharray') === null)
  const spur = (container: HTMLElement) =>
    lines(container).find((l) => l.getAttribute('stroke-dasharray') !== null)
  const xs = (line: SVGPolylineElement) =>
    line.getAttribute('points')!.split(' ').map((p) => Number.parseFloat(p.split(',')[0]!))
  const ys = (line: SVGPolylineElement) =>
    line.getAttribute('points')!.split(' ').map((p) => Number.parseFloat(p.split(',')[1]!))

  it('puts north above the anchor and east to its right', () => {
    const { container } = draw()
    // Percentages of a square plot, so 50% is the anchor in both axes.
    const placed = pins(container).map(at)
    expect(placed).toHaveLength(2)
    const [n, e] = placed as [(typeof placed)[number], (typeof placed)[number]]
    expect(n.y).toBeLessThan(50)
    expect(n.x).toBeCloseTo(50, 0)
    expect(e.x).toBeGreaterThan(50)
    expect(e.y).toBeCloseTo(50, 0)
  })

  it('scales to the furthest place, not to the radius searched', () => {
    const { container } = draw()
    // 1.26 km furthest inside an 8 km search. Scaled to the radius, the east
    // pin would sit near 57%, barely off the anchor; scaled to the places it
    // reaches the edge of the plot. The rings that used to say so are gone
    // with the design, so the pin's own position is what carries it.
    const e = at(pins(container)[1]!)
    expect(e.x).toBeGreaterThan(80)
  })

  it('keeps a route stop on the plot when its category is filtered out', () => {
    // Dinner, while the Workout chip is selected: no pin, but the line still
    // has to reach it. Scaled to the visible places alone this runs to roughly
    // x=736 in a 320-wide plot, which is off the band entirely.
    const { container } = draw({
      route: {
        stops: [anchorStop, { name: 'Dinner', lat: 41.8924, lng: -87.55, is_anchor: false, walk_minutes: 83 }],
        total_minutes: 83,
      },
    })
    expect(Math.max(...xs(route(container)!))).toBeLessThanOrEqual(320)
  })

  it('a place with no coordinates gets no pin instead of a wrong one', () => {
    const { container } = draw({ places: [north, place({ id: 'x', name: 'Unlocated' })] })
    expect(pins(container)).toHaveLength(1)
  })

  it('names only the selected place, so the map does not become a word cloud', () => {
    const { container } = draw({ selectedId: 'n' })
    // Every pin carries an initial and nothing more; the name belongs to the
    // callout, which only the selected place has.
    const visible = pins(container).map((b) => b.querySelector('[aria-hidden]')?.textContent)
    expect(visible).toEqual(['N', 'E'])
    expect(screen.getByText('7 min walk from The Gwen')).toBeTruthy()
  })

  it('keeps the callout inside the band when its pin sits at the edge', () => {
    const far = place({ id: 'f', name: 'Far east', lat: 41.8924, lng: -87.55, distance_meters: 6000 })
    const { container } = draw({ places: [far], selectedId: 'f' })
    const callout = container.querySelector('.z-30') as HTMLElement
    expect(Number.parseFloat(callout.style.left)).toBeLessThanOrEqual(80)
  })

  it('shows the anchor over a pin that sits on it, without disabling that pin', async () => {
    // A hotel gym is a minute from the hotel, so its pin lands on the anchor.
    const inHouse = place({ id: 'g', name: 'Gym', lat: 41.8925, lng: -87.6252, walk_minutes: 1 })
    const onSelect = vi.fn()
    const { container } = draw({ places: [inHouse, east], onSelect })
    const anchorDot = container.querySelector('.bg-ink') as HTMLElement
    expect(anchorDot.className).toContain('pointer-events-none')
    await userEvent.click(pins(container)[0]!)
    expect(onSelect).toHaveBeenCalledWith('g')
  })

  it('the callout chevron leads to the card rather than nowhere', async () => {
    const onOpen = vi.fn()
    const { container } = draw({ selectedId: 'n', onOpen })
    await userEvent.click(container.querySelector('.z-30 button') as HTMLElement)
    expect(onOpen).toHaveBeenCalledWith('n')
  })

  it("draws the day as one line through its stops, north still up", () => {
    const { container } = draw({ route: routeToNorth })
    const drawn = route(container)!
    expect(xs(drawn)).toHaveLength(2)
    const [start, stop] = ys(drawn) as [number, number]
    expect(stop).toBeLessThan(start)
  })

  it('reads the day back as a walk, with what it adds up to', () => {
    const { container } = draw({ route: routeToNorth })
    // Scoped to the strip: the anchor and the stop are both named elsewhere on
    // the map, by the pins' screen-reader labels.
    const strip = container.querySelector('.z-20 > div')!.textContent
    expect(strip).toContain('The Gwen')
    expect(strip).toContain('11 min')
    expect(strip).toContain('North')
    expect(strip).toContain('11 min walking')
  })

  it('says the day is empty rather than leaving a bare map', () => {
    draw()
    expect(screen.getByText('Nothing planned today')).toBeTruthy()
  })

  it('offers a place the day does not go to as a spur, priced from the anchor', () => {
    const { container } = draw({ selectedId: 'n' })
    expect(spur(container)).toBeDefined()
    expect(screen.getByText('Add North: +7 min from The Gwen')).toBeTruthy()
  })

  it('offers no spur to a place the day already goes to', () => {
    const { container } = draw({ selectedId: 'n', route: routeToNorth })
    expect(spur(container)).toBeUndefined()
    expect(screen.queryByText(/^Add North/)).toBeNull()
  })
})
