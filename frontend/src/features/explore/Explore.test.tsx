import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Basemap, ExploreAnchor, ExplorePlace, ExploreRoute } from '@/api/queries'
import { CategoryChips } from './CategoryChips'
import { PlaceCard } from './PlaceCard'
import { PlaceMap } from './PlaceMap'
import type { Rect } from './areas'
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

/**
 * The basemap: real OpenStreetMap geometry under the pins.
 *
 * What these pin is the property that made it worth fetching coordinates
 * rather than an image. The streets go through the same projection the pins
 * do, so they stay under the right pin when the scale changes -- which it does
 * on every category tap. A rendered tile could not do that, and neither could
 * a second copy of the projection maths.
 */
describe('PlaceMap basemap', () => {
  const streets: Basemap = {
    radius_m: 2000,
    lat: 41.8924,
    lng: -87.6252,
    attribution: '© OpenStreetMap contributors',
    // A north-south street through the anchor, and an east-west one.
    roads_major: [[41.885, -87.6252, 41.9, -87.6252]],
    roads_minor: [[41.8924, -87.633, 41.8924, -87.617]],
    water: [[41.895, -87.63, 41.896, -87.628, 41.895, -87.63]],
    parks: [],
    buildings: [],
  }
  const empty: Basemap = {
    radius_m: 2000,
    lat: 41.8924,
    lng: -87.6252,
    attribution: '© OpenStreetMap contributors',
    roads_major: [],
    roads_minor: [],
    water: [],
    parks: [],
    buildings: [],
  }
  const somewhere = place({ id: 'n', name: 'North', lat: 41.9, lng: -87.6252 })

  function drawMap(basemap?: Basemap) {
    return render(
      <PlaceMap
        anchor={anchor}
        places={[somewhere]}
        route={{ stops: [], total_minutes: null }}
        basemap={basemap}
        radiusM={8000}
        timezone={TZ}
        selectedId={null}
        onSelect={() => {}}
        onOpen={() => {}}
      />,
    )
  }

  const texture = (c: HTMLElement) => c.querySelector('[class*="map-texture"]')

  it('draws real streets when it has them', () => {
    const { container } = drawMap(streets)
    expect(container.querySelector('.stroke-map-road-major')).not.toBeNull()
    expect(container.querySelector('.stroke-map-road')).not.toBeNull()
    expect(container.querySelector('.fill-map-water')).not.toBeNull()
  })

  it('gives up the placeholder grid to real streets', () => {
    // The grid stands in for a street network; both at once reads as two.
    expect(texture(drawMap().container)).not.toBeNull()
    expect(texture(drawMap(streets).container)).toBeNull()
  })

  it('keeps the placeholder grid when the area came back with nothing in it', () => {
    // Open sea and "we could not fetch" arrive identically here, and neither is
    // a reason to remove the only texture the band has.
    expect(texture(drawMap(empty).container)).not.toBeNull()
  })

  it('credits OpenStreetMap wherever the geometry is shown', () => {
    // ODbL, not decoration.
    const { container } = drawMap(streets)
    expect(container.textContent).toContain('OpenStreetMap')
  })

  it('leaves the credit off when there is no geometry to credit', () => {
    expect(drawMap(empty).container.textContent).not.toContain('OpenStreetMap')
  })

  /* The ground is drawn in metres under one group transform, so where a
     street lands on the frame is the path composed with that transform. */
  function majorRoad(container: HTMLElement) {
    const g = container.querySelector('g[transform]')!.getAttribute('transform')!
    const [tx, ty, s] = g
      .match(/translate\((\S+) (\S+)\) scale\((\S+)\)/)!
      .slice(1)
      .map(Number) as [number, number, number]
    const d = container.querySelector('.stroke-map-road-major')!.getAttribute('d')!
    return [...d.matchAll(/[ML](-?[\d.]+) (-?[\d.]+)/g)].map((m) => ({
      x: tx + Number(m[1]) * s,
      y: ty + Number(m[2]) * s,
    }))
  }

  it('puts the street through the anchor at the centre of the plot', () => {
    /* The load-bearing one. The north-south road runs along the anchor's own
       longitude, so whatever the scale, it has to be drawn down the middle. */
    const { container } = drawMap(streets)
    const xs = majorRoad(container).map((p) => p.x)
    expect(xs.length).toBeGreaterThan(0)
    expect(xs.every((x) => Math.abs(x - 160) < 0.5)).toBe(true)
  })

  it('draws north up on the ground as well as for the pins', () => {
    const { container } = drawMap(streets)
    const [south, north] = majorRoad(container)
    expect(north!.y).toBeLessThan(south!.y)
  })

  it('rescales the streets with the pins rather than holding still', () => {
    /* What an image could not do. Same geometry, a nearer furthest pin, so the
       plot zooms in and the same street has to move outward with it. */
    const near = place({ id: 'x', name: 'Near', lat: 41.8934, lng: -87.6252 })
    const wide = render(
      <PlaceMap anchor={anchor} places={[somewhere]} route={{ stops: [], total_minutes: null }}
        basemap={streets} radiusM={8000} timezone={TZ} selectedId={null}
        onSelect={() => {}} onOpen={() => {}} />,
    )
    const close = render(
      <PlaceMap anchor={anchor} places={[near]} route={{ stops: [], total_minutes: null }}
        basemap={streets} radiusM={8000} timezone={TZ} selectedId={null}
        onSelect={() => {}} onOpen={() => {}} />,
    )
    const ys = (c: HTMLElement) => majorRoad(c).map((p) => p.y)
    const spread = (c: HTMLElement) => Math.max(...ys(c)) - Math.min(...ys(c))
    expect(spread(close.container)).toBeGreaterThan(spread(wide.container) * 2)
    /* And it does so by moving the group, not by rebuilding the geometry: the
       path itself is the same string at both scales. That is the property a
       gesture over sixty thousand points depends on. */
    const d = (c: HTMLElement) => c.querySelector('.stroke-map-road-major')!.getAttribute('d')
    expect(d(close.container)).toBe(d(wide.container))
  })

  it('keeps road widths in frame units under the zoom transform', () => {
    const { container } = drawMap(streets)
    for (const road of container.querySelectorAll('[class*="stroke-map-road"]')) {
      expect(road.getAttribute('vector-effect')).toBe('non-scaling-stroke')
    }
  })

  it('culls a way that is nowhere near the frame', () => {
    const faraway: Basemap = { ...empty, roads_major: [[51.5, -0.12, 51.51, -0.13]] }
    const { container } = drawMap(faraway)
    expect(container.querySelector('.stroke-map-road-major')).toBeNull()
  })
})

/* The expanded map: the same ground on the whole screen, where looking around
 * is allowed. Its state is a viewport, so every control is checked by where
 * the pins end up rather than by what a button is called. */
describe('PlaceMap expanded', () => {
  const north = place({ id: 'n', name: 'North', lat: 41.9, lng: -87.6252, walk_minutes: 7 })
  const east = place({ id: 'e', name: 'East', lat: 41.8924, lng: -87.61, walk_minutes: 12 })
  const noRoute: ExploreRoute = { stops: [], total_minutes: null }

  async function open(over: Partial<ComponentProps<typeof PlaceMap>> = {}) {
    const onSelect = vi.fn()
    const result = render(
      <PlaceMap
        anchor={anchor}
        places={[north, east]}
        route={noRoute}
        radiusM={8000}
        timezone={TZ}
        selectedId={null}
        onSelect={onSelect}
        onOpen={() => {}}
        {...over}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Expand map' }))
    const dialog = result.container.querySelector('dialog') as HTMLDialogElement
    // showModal() moves focus into the dialog in a browser; jsdom's stand-in
    // does not, so the test does what a tap on the ground does.
    ;(dialog.firstElementChild as HTMLElement).focus()
    return { ...result, dialog, onSelect }
  }

  /** Pin positions inside the dialog, as percentages of its frame. */
  function pins(dialog: HTMLElement) {
    return [...dialog.querySelectorAll('button[aria-pressed]')].map((el) => ({
      x: Number.parseFloat((el as HTMLElement).style.left),
      y: Number.parseFloat((el as HTMLElement).style.top),
    }))
  }
  const button = (dialog: HTMLElement, name: string) =>
    within(dialog).getByRole('button', { name })

  it('opens the map on the whole screen, and closes it again', async () => {
    const { container, dialog } = await open()
    expect(dialog.open).toBe(true)
    expect(dialog).toHaveAccessibleName('Map of places around The Gwen')
    await userEvent.click(button(dialog, 'Close map'))
    expect(container.querySelector('dialog')).toBeNull()
  })

  it('zooms in about the centre, in steps you can see', async () => {
    const { dialog } = await open()
    const before = pins(dialog)
    await userEvent.click(button(dialog, 'Zoom in'))
    const after = pins(dialog)
    for (const [i, pin] of after.entries()) {
      expect(pin.x - 50).toBeCloseTo((before[i]!.x - 50) * 1.5, 6)
      expect(pin.y - 50).toBeCloseTo((before[i]!.y - 50) * 1.5, 6)
    }
  })

  it('pans with the arrow keys, the view moving the way the arrow points', async () => {
    const { dialog } = await open()
    const before = pins(dialog)
    await userEvent.keyboard('{ArrowRight}')
    const after = pins(dialog)
    // 48 px of a 360 px frame: the ground slides left as the view looks right.
    expect(after[0]!.x - before[0]!.x).toBeCloseTo((-48 / 360) * 100, 6)
    expect(after[0]!.y).toBeCloseTo(before[0]!.y, 6)
  })

  it('recentres to the fitted view after any amount of wandering', async () => {
    const { dialog } = await open()
    const fitted = pins(dialog)
    await userEvent.click(button(dialog, 'Zoom in'))
    await userEvent.keyboard('{ArrowUp}{ArrowLeft}')
    expect(pins(dialog)).not.toEqual(fitted)
    await userEvent.click(button(dialog, 'Recentre'))
    expect(pins(dialog)).toEqual(fitted)
  })

  it('stops zooming out at twice the fitted view', async () => {
    const { dialog } = await open()
    const out = button(dialog, 'Zoom out')
    await userEvent.click(out)
    expect(out).toBeEnabled()
    await userEvent.click(out)
    expect(out).toBeDisabled()
  })

  it('a pin still selects', async () => {
    const { dialog, onSelect } = await open()
    await userEvent.click(within(dialog).getByRole('button', { name: /^North/ }))
    expect(onSelect).toHaveBeenCalledWith('n')
  })

  it('brings the selected card up to meet the pin, in place of the callout', async () => {
    const { dialog } = await open({ selectedId: 'n' })
    expect(within(dialog).getByRole('heading', { name: 'North' })).toBeInTheDocument()
    // The callout is for the band, where the card is off-screen. Here it is not.
    expect(dialog.querySelector('.w-\\[210px\\]')).toBeNull()
    expect(within(dialog).getByText(/Add North: \+7 min from The Gwen/)).toBeInTheDocument()
  })

  it('never speaks in the first person', async () => {
    const { dialog } = await open({ selectedId: 'e' })
    expect(dialog.textContent).not.toMatch(/\bI\b/)
  })
})

/* Gestures, with synthetic pointer and wheel events. Each one is checked by
 * where the pins end up, which is the same check a finger would make. */
describe('PlaceMap gestures', () => {
  const north = place({ id: 'n', name: 'North', lat: 41.9, lng: -87.6252, walk_minutes: 7 })
  const east = place({ id: 'e', name: 'East', lat: 41.8924, lng: -87.61, walk_minutes: 12 })
  // The dialog's frame in jsdom, where nothing has a size: the hook's fallback.
  const W = 360
  const H = 640

  async function open() {
    const onSelect = vi.fn()
    const { container } = render(
      <PlaceMap
        anchor={anchor}
        places={[north, east]}
        route={{ stops: [], total_minutes: null }}
        radiusM={8000}
        timezone={TZ}
        selectedId={null}
        onSelect={onSelect}
        onOpen={() => {}}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Expand map' }))
    const dialog = container.querySelector('dialog') as HTMLDialogElement
    const ground = within(dialog).getByRole('img').parentElement as HTMLElement
    return { dialog, ground, onSelect }
  }

  /** Pin positions in the dialog, in pixels of its frame. */
  function pins(dialog: HTMLElement) {
    return [...dialog.querySelectorAll('button[aria-pressed]')].map((el) => ({
      x: (Number.parseFloat((el as HTMLElement).style.left) / 100) * W,
      y: (Number.parseFloat((el as HTMLElement).style.top) / 100) * H,
    }))
  }
  const pointer = (id: number, x: number, y: number) => ({
    pointerId: id,
    clientX: x,
    clientY: y,
    button: 0,
  })

  it('drags the ground with the pointer', async () => {
    const { dialog, ground } = await open()
    const before = pins(dialog)
    fireEvent.pointerDown(ground, pointer(1, 100, 100))
    fireEvent.pointerMove(ground, pointer(1, 140, 110))
    fireEvent.pointerUp(ground, pointer(1, 140, 110))
    const after = pins(dialog)
    expect(after[0]!.x - before[0]!.x).toBeCloseTo(40, 6)
    expect(after[0]!.y - before[0]!.y).toBeCloseTo(10, 6)
  })

  it('a drag that starts slowly still moves the ground the whole way', async () => {
    const { dialog, ground } = await open()
    const before = pins(dialog)
    fireEvent.pointerDown(ground, pointer(1, 100, 100))
    fireEvent.pointerMove(ground, pointer(1, 104, 100))
    fireEvent.pointerMove(ground, pointer(1, 108, 100))
    fireEvent.pointerMove(ground, pointer(1, 115, 100))
    fireEvent.pointerUp(ground, pointer(1, 115, 100))
    expect(pins(dialog)[0]!.x - before[0]!.x).toBeCloseTo(15, 6)
  })

  it('a tap selects a pin; the click a drag leaves behind does not', async () => {
    const { dialog, ground, onSelect } = await open()
    const pin = within(dialog).getByRole('button', { name: /^North/ })
    fireEvent.pointerDown(pin, pointer(1, 50, 50))
    fireEvent.pointerUp(pin, pointer(1, 51, 50))
    fireEvent.click(pin)
    expect(onSelect).toHaveBeenCalledTimes(1)

    fireEvent.pointerDown(pin, pointer(1, 50, 50))
    fireEvent.pointerMove(ground, pointer(1, 80, 50))
    fireEvent.pointerUp(ground, pointer(1, 80, 50))
    fireEvent.click(pin)
    expect(onSelect).toHaveBeenCalledTimes(1)

    // And the swallowed click does not poison the next honest tap.
    fireEvent.pointerDown(pin, pointer(1, 50, 50))
    fireEvent.pointerUp(pin, pointer(1, 50, 50))
    fireEvent.click(pin)
    expect(onSelect).toHaveBeenCalledTimes(2)
  })

  it('a wheel zooms about the pointer, keeping the ground under it still', async () => {
    const { dialog, ground } = await open()
    const about = { x: 90, y: 160 }
    const before = pins(dialog)
    fireEvent.wheel(ground, { clientX: about.x, clientY: about.y, deltaY: -100 })
    const after = pins(dialog)
    const factor = Math.exp(100 * 0.0015)
    for (const [i, pin] of after.entries()) {
      expect(pin.x - about.x).toBeCloseTo((before[i]!.x - about.x) * factor, 6)
      expect(pin.y - about.y).toBeCloseTo((before[i]!.y - about.y) * factor, 6)
    }
  })

  it('a pinch zooms by the spread of the fingers and follows their midpoint', async () => {
    const { dialog, ground } = await open()
    const before = pins(dialog)
    fireEvent.pointerDown(ground, pointer(1, 100, 300))
    fireEvent.pointerDown(ground, pointer(2, 200, 300))
    // Second finger moves out: distance doubles, midpoint drifts 150 -> 200.
    fireEvent.pointerMove(ground, pointer(2, 300, 300))
    fireEvent.pointerUp(ground, pointer(2, 300, 300))
    fireEvent.pointerUp(ground, pointer(1, 100, 300))
    const after = pins(dialog)
    for (const [i, pin] of after.entries()) {
      expect(pin.x).toBeCloseTo(200 + (before[i]!.x - 150) * 2, 6)
      expect(pin.y).toBeCloseTo(300 + (before[i]!.y - 300) * 2, 6)
    }
  })

  it('the band itself does not drag', () => {
    const onSelect = vi.fn()
    render(
      <PlaceMap
        anchor={anchor}
        places={[north, east]}
        route={{ stops: [], total_minutes: null }}
        radiusM={8000}
        timezone={TZ}
        selectedId={null}
        onSelect={onSelect}
        onOpen={() => {}}
      />,
    )
    const ground = screen.getByRole('img').parentElement as HTMLElement
    const before = ground.querySelector('button[aria-pressed]')!.getAttribute('style')
    fireEvent.pointerDown(ground, pointer(1, 100, 100))
    fireEvent.pointerMove(ground, pointer(1, 160, 100))
    fireEvent.pointerUp(ground, pointer(1, 160, 100))
    expect(ground.querySelector('button[aria-pressed]')!.getAttribute('style')).toBe(before)
    expect(ground.style.touchAction).toBe('')
  })
})

/* Finer ground on zoom. The map only reports where the view settled and
 * draws whatever it is handed; the deciding is in useAreaDetail.test.tsx. */
describe('PlaceMap detail', () => {
  const north = place({ id: 'n', name: 'North', lat: 41.9, lng: -87.6252, walk_minutes: 7 })
  const noRoute: ExploreRoute = { stops: [], total_minutes: null }
  const base: Basemap = {
    radius_m: 5500,
    lat: 41.8924,
    lng: -87.6252,
    attribution: '© OpenStreetMap contributors',
    roads_major: [[41.885, -87.6252, 41.9, -87.6252]],
    roads_minor: [],
    water: [],
    parks: [],
    buildings: [],
  }
  // A block-sized cell a little north-east of the hotel, with one building.
  const fine: Basemap = {
    radius_m: 750,
    lat: 41.8954,
    lng: -87.6212,
    attribution: '© OpenStreetMap contributors',
    roads_major: [],
    roads_minor: [],
    water: [],
    parks: [],
    buildings: [[41.895, -87.622, 41.8952, -87.622, 41.8952, -87.6218, 41.895, -87.6218, 41.895, -87.622]],
  }

  async function open(over: Partial<ComponentProps<typeof PlaceMap>> = {}) {
    const result = render(
      <PlaceMap
        anchor={anchor}
        places={[north]}
        route={noRoute}
        radiusM={8000}
        timezone={TZ}
        selectedId={null}
        onSelect={() => {}}
        onOpen={() => {}}
        {...over}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Expand map' }))
    return result.container.querySelector('dialog') as HTMLDialogElement
  }

  it('reports the settled view in metres, and again after a zoom', async () => {
    const onView = vi.fn()
    const dialog = await open({ basemap: base, onView })
    expect(onView).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(onView).toHaveBeenCalledTimes(1))
    const first = onView.mock.calls[0]?.[0] as Rect
    // jsdom measures nothing, so the frame is the 360 x 640 fallback: the
    // long side is the short one times 640/360.
    expect(first.centerEastM).toBe(0)
    expect(first.centerNorthM).toBe(0)
    expect(first.halfHeightM).toBeCloseTo(first.halfWidthM * (640 / 360))

    await userEvent.click(within(dialog).getByRole('button', { name: 'Zoom in' }))
    await vi.waitFor(() => expect(onView).toHaveBeenCalledTimes(2))
    const second = onView.mock.calls[1]?.[0] as Rect
    expect(second.halfWidthM).toBeCloseTo(first.halfWidthM / 1.5)
  })

  it('draws a finer area over the base on its own patch of ground', async () => {
    const dialog = await open({ basemap: base, detail: [fine] })
    const ground = dialog.querySelector('[data-testid="area-ground"]') as SVGRectElement
    expect(ground).not.toBeNull()
    // The patch is the cell's square, in metres east and south of the hotel.
    expect(Number(ground.getAttribute('width'))).toBe(1500)
    expect(Number(ground.getAttribute('height'))).toBe(1500)
    const eastM = (fine.lng! - anchor.lng!) * 111_320 * Math.cos((anchor.lat! * Math.PI) / 180)
    const northM = (fine.lat! - anchor.lat!) * 111_320
    expect(Number(ground.getAttribute('x'))).toBeCloseTo(eastM - 750, 3)
    expect(Number(ground.getAttribute('y'))).toBeCloseTo(-northM - 750, 3)
    // Under the patch: the base's street. On it: the building.
    const baseRoad = dialog.querySelector('.stroke-map-road-major') as Element
    const building = dialog.querySelector('.fill-map-building') as Element
    expect(building).not.toBeNull()
    expect(baseRoad.compareDocumentPosition(ground) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(ground.compareDocumentPosition(building) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('a detail area alone is still real ground, not the dot grid', async () => {
    const dialog = await open({ detail: [fine] })
    expect(dialog.querySelector('[class*="map-texture"]')).toBeNull()
    expect(dialog.querySelector('.fill-map-building')).not.toBeNull()
  })
})
