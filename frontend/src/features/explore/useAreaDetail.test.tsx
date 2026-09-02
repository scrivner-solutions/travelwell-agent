import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BASEMAP_FETCH_CAP, type Basemap, type ExploreAnchor } from '@/api/queries'
import { areaCovering, snap, type Rect } from './areas'
import { useAreaDetail } from './useAreaDetail'

const GET = vi.fn()
vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  api: async () => ({ GET }),
}))

const anchor: ExploreAnchor = { name: 'The Gwen', is_hotel: true, lat: 41.8924, lng: -87.6252 }
const ATTRIBUTION = '© OpenStreetMap contributors'

function area(over: Partial<Basemap>): Basemap {
  return {
    radius_m: 750,
    lat: 41.8924,
    lng: -87.6252,
    attribution: ATTRIBUTION,
    roads_major: [],
    roads_minor: [],
    water: [],
    parks: [],
    buildings: [],
    ...over,
  }
}

/** The base area the band fetched: the city cell around the hotel. */
const base = area({ ...snap(41.8924, -87.6252, 5500), radius_m: 5500, roads_major: [[41.88, -87.63, 41.9, -87.62]] })

function rect(over: Partial<Rect> = {}): Rect {
  return { centerEastM: 0, centerNorthM: 0, halfWidthM: 300, halfHeightM: 500, ...over }
}

function answer(body: Basemap) {
  GET.mockResolvedValueOnce({ data: body, response: { ok: true, status: 200 } as Response })
}

let trips = 0
function mount(baseArea: Basemap | undefined = base) {
  const tripId = `trip-${++trips}`
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const hook = renderHook(() => useAreaDetail(tripId, anchor, baseArea), { wrapper })
  return { ...hook, tripId }
}

function askedFor() {
  return GET.mock.calls.map(([, opts]) => (opts as { params: { query: Record<string, number | string> } }).params.query)
}

describe('useAreaDetail', () => {
  // Reset, not clear: a queued answer nobody asked for must not leak forward.
  beforeEach(() => GET.mockReset())

  it('fetches the finer cell a settled view needs, and draws it', async () => {
    const fine = area({ ...areaCovering(anchor, rect())!, buildings: [[41.892, -87.625, 41.893, -87.625, 41.893, -87.624, 41.892, -87.625]] })
    answer(fine)
    const { result, tripId } = mount()
    act(() => result.current.onView(rect()))
    await vi.waitFor(() => expect(result.current.layers).toHaveLength(1))
    expect(askedFor()).toEqual([{ trip_id: tripId, radius_m: fine.radius_m, lat: fine.lat, lng: fine.lng }])
    expect(result.current.layers[0]).toBe(fine)
  })

  it('does not ask for what the base already covers at that size', async () => {
    const { result } = mount()
    // A view a bit narrower than the city cell: the cell it wants is the one it has.
    act(() => result.current.onView(rect({ halfWidthM: 3000, halfHeightM: 3000 })))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(GET).not.toHaveBeenCalled()
    expect(result.current.layers).toEqual([])
  })

  it('asks wider when the frame runs past the base, and paints that beneath the fine one', async () => {
    const tall = rect({ halfWidthM: 5000, halfHeightM: 7000 })
    const wide = area({ ...areaCovering(anchor, tall)!, water: [[41.8, -87.7, 41.9, -87.7, 41.9, -87.6, 41.8, -87.7]] })
    expect(wide.radius_m).toBeGreaterThan(base.radius_m)
    answer(wide)
    const { result } = mount()
    act(() => result.current.onView(tall))
    await vi.waitFor(() => expect(result.current.layers).toHaveLength(1))

    const fine = area({ ...areaCovering(anchor, rect())!, buildings: [[41.892, -87.625, 41.893, -87.625, 41.893, -87.624, 41.892, -87.625]] })
    answer(fine)
    act(() => result.current.onView(rect()))
    await vi.waitFor(() => expect(result.current.layers).toHaveLength(2))
    expect(result.current.layers.map((layer) => layer.radius_m)).toEqual([wide.radius_m, fine.radius_m])
  })

  it('one cell, however many times the view settles in it, is one request', async () => {
    answer(area({ ...areaCovering(anchor, rect())!, parks: [[41.892, -87.625, 41.893, -87.625, 41.893, -87.624, 41.892, -87.625]] }))
    const { result } = mount()
    act(() => result.current.onView(rect()))
    await vi.waitFor(() => expect(result.current.layers).toHaveLength(1))
    act(() => result.current.onView(rect({ centerEastM: 40 })))
    act(() => result.current.onView(rect({ centerNorthM: -40 })))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(GET).toHaveBeenCalledTimes(1)
  })

  it('one step finer than what is drawn is not worth a request; two is', async () => {
    const { result } = mount()
    const views = [rect({ halfWidthM: 1300, halfHeightM: 1300 }), rect({ halfWidthM: 800, halfHeightM: 800 }), rect({ halfWidthM: 600, halfHeightM: 600 })]
    const buckets = views.map((view) => areaCovering(anchor, view)!.radius_m)
    expect(buckets).toEqual([2000, 1000, 750])
    const requests: number[] = []
    for (const view of views) {
      answer(area({ ...areaCovering(anchor, view)!, roads_minor: [[41.892, -87.625, 41.893, -87.625]] }))
      act(() => result.current.onView(view))
      await new Promise((resolve) => setTimeout(resolve, 20))
      requests.push(GET.mock.calls.length)
    }
    expect(requests).toEqual([1, 2, 2])
  })

  it('a phone frame asks for the cell that covers its width and middle, not its full height', async () => {
    // Four zoom steps in on a 390 x 844 frame over a 5.5 km base.
    const tall = rect({ halfWidthM: 950, halfHeightM: 2050 })
    const wholeFrame = areaCovering(anchor, tall)!
    const wanted = areaCovering(anchor, rect({ halfWidthM: 950, halfHeightM: 1425 }))!
    expect(wanted.radius_m).toBeLessThan(wholeFrame.radius_m)
    expect(wanted.radius_m).toBeLessThanOrEqual(2000)
    answer(area({ ...wanted, buildings: [[41.892, -87.625, 41.893, -87.625, 41.893, -87.624, 41.892, -87.625]] }))
    const { result } = mount()
    act(() => result.current.onView(tall))
    await vi.waitFor(() => expect(result.current.layers).toHaveLength(1))
    expect(askedFor()[0]).toMatchObject({ radius_m: wanted.radius_m, lat: wanted.lat, lng: wanted.lng })
  })

  it('an answer with nothing in it is not a layer', async () => {
    answer(area({ ...areaCovering(anchor, rect())! }))
    const { result } = mount()
    act(() => result.current.onView(rect()))
    await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(1))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(result.current.layers).toEqual([])
  })

  it('a failed fetch leaves what was drawn alone', async () => {
    const fine = area({ ...areaCovering(anchor, rect())!, roads_minor: [[41.892, -87.625, 41.893, -87.625]] })
    answer(fine)
    const { result } = mount()
    act(() => result.current.onView(rect()))
    await vi.waitFor(() => expect(result.current.layers).toHaveLength(1))
    GET.mockResolvedValueOnce({ data: undefined, error: { title: 'down' }, response: { ok: false, status: 503 } as Response })
    act(() => result.current.onView(rect({ centerEastM: 2000 })))
    await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(2))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(result.current.layers).toEqual([fine])
  })

  it('a base with no geography means the server has nothing here: it stops asking', async () => {
    const { result } = mount(area({ radius_m: 5500 }))
    act(() => result.current.onView(rect()))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(GET).not.toHaveBeenCalled()
  })

  it('stops at the session budget and says nothing', async () => {
    const { result } = mount()
    for (let step = 0; step <= BASEMAP_FETCH_CAP; step += 1) {
      // Each step is a new block east: a new cell at the finest bucket.
      const view = rect({ centerEastM: step * 1000 })
      answer(area({ ...areaCovering(anchor, view)!, roads_minor: [[41.892, -87.625, 41.893, -87.625]] }))
      act(() => result.current.onView(view))
      await new Promise((resolve) => setTimeout(resolve, 20))
    }
    expect(GET).toHaveBeenCalledTimes(BASEMAP_FETCH_CAP)
  })
})

describe('useAreaDetail on the wire', () => {
  beforeEach(() => GET.mockReset())

  function neverAnswer() {
    let signal: AbortSignal | undefined
    GET.mockImplementationOnce((_path: string, opts: { signal?: AbortSignal }) => {
      signal = opts.signal
      return new Promise(() => {})
    })
    return () => signal
  }

  it('a view that moves on before its answer arrives cancels the ask', async () => {
    const first = neverAnswer()
    const { result } = mount()
    act(() => result.current.onView(rect()))
    await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(1))
    expect(first()).toBeInstanceOf(AbortSignal)
    expect(first()?.aborted).toBe(false)

    answer(area({ radius_m: 750, roads_major: [[41.89, -87.62, 41.9, -87.62]] }))
    act(() => result.current.onView(rect({ centerEastM: 2000 })))
    await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(2))
    await vi.waitFor(() => expect(first()?.aborted).toBe(true))
  })

  it('what has been drawn stays when the pending ask is replaced', async () => {
    answer(area({ radius_m: 750, roads_major: [[41.89, -87.62, 41.9, -87.62]] }))
    const { result } = mount()
    act(() => result.current.onView(rect()))
    await vi.waitFor(() => expect(result.current.layers).toHaveLength(1))

    const second = neverAnswer()
    act(() => result.current.onView(rect({ centerEastM: 2000 })))
    await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(2))
    answer(area({ radius_m: 750, roads_major: [[41.89, -87.6, 41.9, -87.6]] }))
    act(() => result.current.onView(rect({ centerEastM: 4000 })))
    await vi.waitFor(() => expect(result.current.layers).toHaveLength(2))
    expect(second()?.aborted).toBe(true)
    expect(GET).toHaveBeenCalledTimes(3)
  })
})
