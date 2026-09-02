import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getRouteApi } from '@tanstack/react-router'
import {
  basemapQueryOptions,
  basemapRadius,
  exploreQueryOptions,
  preferencesQueryOptions,
  tripsQueryOptions,
  type PlaceKind,
} from '@/api/queries'
import { focusTrip } from '@/lib/trips'
import { EmptyState, LoadingState } from '@/components/ui/ScreenState'
import { ProfileButton } from '@/components/ui/ProfileButton'
import { CategoryChips } from './CategoryChips'
import { FilterSheet } from './FilterSheet'
import { FiltersButton } from './FiltersButton'
import {
  DEFAULT_FILTERS,
  activeCount,
  constraintLine,
  passes,
  windowRange,
  type Filters,
} from './filters'
import { PlaceCard } from './PlaceCard'
import { PlaceMap } from './PlaceMap'
import { plotRadiusFor } from './projection'

const route = getRouteApi('/_shell/explore')

/* The design's section heading names the category in the user's language
 * rather than repeating the chip. There is no "All" in the design because it
 * opens on Workout; ours has one, and it says where rather than what. */
const HEADINGS: Partial<Record<PlaceKind, string>> = {
  workout: 'Ways to move',
  food: 'Places to eat',
  outdoor: 'Outside near you',
  recovery: 'Rest and recovery',
}

/* Eyebrow, then serif headline: the skeleton every screen in the design uses.
 * The anchor belongs up here rather than in a line under the title, because it
 * is what the whole screen is about, not a caption on the map. */
function Header({ eyebrow }: { eyebrow?: string }) {
  return (
    <header className="mb-4 flex items-center justify-between gap-3">
      <div className="min-w-0">
        {eyebrow !== undefined && (
          <p className="truncate text-eyebrow-wide font-semibold uppercase text-muted-soft">
            {eyebrow}
          </p>
        )}
        <h1 className={`font-display text-display ${eyebrow !== undefined ? 'mt-2' : ''}`}>
          Explore
        </h1>
      </div>
      <ProfileButton />
    </header>
  )
}

export function ExploreScreen() {
  const [category, setCategory] = useState<PlaceKind | undefined>(undefined)
  /* Filters are the URL (see the route). Defaults are written back as
     `undefined`, which the router drops from the search string. */
  const search = route.useSearch()
  const navigate = route.useNavigate()
  const filters: Filters = {
    window: search.window ?? DEFAULT_FILTERS.window,
    walk: search.walk ?? DEFAULT_FILTERS.walk,
    underCap: search.cap ?? DEFAULT_FILTERS.underCap,
    amenities: search.amenities ?? DEFAULT_FILTERS.amenities,
  }
  const setFilters = (next: Filters) =>
    void navigate({
      replace: true,
      search: (prev) => ({
        ...prev,
        window: next.window === DEFAULT_FILTERS.window ? undefined : next.window,
        walk: next.walk ?? undefined,
        cap: next.underCap || undefined,
        amenities: next.amenities || undefined,
      }),
    })
  const setSheet = (open: boolean) =>
    void navigate({ replace: true, search: (prev) => ({ ...prev, sheet: open ? 'filters' : undefined }) })

  // One selection drives both surfaces, which is what keeps the pins and the
  // cards in step rather than each holding its own idea of "current".
  const [selectedId, setSelectedId] = useState<string | null>(null)
  // The callout's chevron leads to the card, which is where the actions are.
  const cards = useRef<Record<string, HTMLLIElement | null>>({})

  const trips = useQuery(tripsQueryOptions())
  const prefs = useQuery(preferencesQueryOptions())
  const trip = trips.data ? focusTrip(trips.data) : undefined
  const explore = useQuery({
    ...exploreQueryOptions(trip?.id ?? '', { category }),
    enabled: trip !== undefined,
  })

  /* Asked for after Explore answers, because the area to fetch is the area the
     map will draw, and that is decided by what came back. Deliberately not part
     of the loading gate below: the map renders on plain ground without it, and
     making the screen wait for geography would trade a working map for a
     slower one. */
  const drawnRadius =
    explore.data?.anchor != null
      ? plotRadiusFor(
          explore.data.anchor,
          explore.data.places,
          explore.data.route,
          explore.data.radius_m,
        )
      : null
  const basemap = useQuery({
    ...basemapQueryOptions(trip?.id ?? '', drawnRadius === null ? 0 : basemapRadius(drawnRadius)),
    enabled: trip !== undefined && drawnRadius !== null,
  })

  if (trips.isPending || (trip !== undefined && explore.isPending)) {
    return (
      <>
        <Header />
        <LoadingState label="Finding places near you" />
      </>
    )
  }

  if (trip === undefined) {
    return (
      <>
        <Header />
        <EmptyState
          title="No trip to explore yet"
          detail="Add a trip and this fills with places around where you are staying."
        />
      </>
    )
  }

  const data = explore.data
  if (data === undefined || data.anchor == null) {
    return (
      <>
        <Header eyebrow={trip.destination_name} />
        <EmptyState
          title={`We don't know where ${trip.destination_name} is yet`}
          detail="Places appear once the trip has a location to measure from."
        />
      </>
    )
  }

  const anchor = data.anchor
  const eyebrow = anchor.is_hotel
    ? `Near ${anchor.name} · ${trip.destination_name}`
    : `Central ${trip.destination_name}`
  const heading = category === undefined ? 'Places near you' : (HEADINGS[category] ?? 'Places near you')

  /* Filtering is on the client, over what the server sent: every fact the
     sheet asks about is already on the place. The basemap above is sized to
     ALL the places on purpose, so narrowing the list never asks for a new
     area. */
  const now = new Date()
  const filterPrefs = prefs.data
    ? { dayPassBudgetCents: prefs.data.day_pass_budget_cents ?? null, amenities: prefs.data.amenities }
    : undefined
  const shown = data.places.filter((place) =>
    passes(place, filters, { prefs: filterPrefs, now, timezone: trip.timezone }),
  )
  const windowOver = windowRange(filters.window, now, trip.timezone) === null
  const count = shown.length
  const filtersButton = <FiltersButton count={activeCount(filters)} onClick={() => setSheet(true)} />

  return (
    <>
      <Header eyebrow={eyebrow} />

      {/* Full bleed: the band is the screen's surface, not a card on it. The
          shell owns the gutter, so escaping it is this screen's business. */}
      <div className="-mx-4">
        <PlaceMap
          anchor={anchor}
          places={shown}
          basemap={basemap.data}
          radiusM={data.radius_m}
          timezone={trip.timezone}
          route={data.route}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onOpen={(id) =>
            cards.current[id]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
          }
          toolbar={filtersButton}
        >
          <CategoryChips kinds={data.kinds} selected={category} onSelect={setCategory} />
        </PlaceMap>
      </div>

      <section className="pt-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-display text-heading-sm">{heading}</h2>
          {filtersButton}
        </div>
        <p className="mt-1.5 text-label font-medium text-muted-soft">
          {constraintLine(count, filters)}
        </p>

        {data.places.length > 0 && count === 0 ? (
          <div className="mt-3 rounded-section border border-dashed border-border-faint bg-card p-5 text-center">
            <p className="text-body font-semibold">Nothing fits these filters</p>
            <p className="mt-1.5 text-caption text-muted-soft">
              {windowOver
                ? `It is past 10 PM in ${trip.destination_name}, so this evening is over.`
                : 'Try a wider window or a longer walk.'}
            </p>
            <button
              type="button"
              onClick={() => setFilters(DEFAULT_FILTERS)}
              className="mt-3.5 h-11 rounded-control border border-border bg-card px-4 text-body-sm font-semibold hover:bg-surface focus-visible:outline-2 focus-visible:outline-primary"
            >
              Reset filters
            </button>
          </div>
        ) : count === 0 ? (
          <div className="mt-3 rounded-section border border-dashed border-border-faint bg-card p-5 text-center">
            <p className="text-body font-semibold">Nothing cached here yet</p>
            <p className="mt-1.5 text-caption text-muted-soft">
              We have not looked around this destination for that category.
            </p>
            {category !== undefined && (
              <button
                type="button"
                onClick={() => setCategory(undefined)}
                className="mt-3.5 h-11 rounded-control border border-border bg-card px-4 text-body-sm font-semibold hover:bg-surface focus-visible:outline-2 focus-visible:outline-primary"
              >
                Show every category
              </button>
            )}
          </div>
        ) : (
          <ul className="mt-3 flex flex-col gap-[11px]">
            {shown.map((place) => (
              <li
                key={place.id}
                ref={(el) => {
                  cards.current[place.id] = el
                }}
              >
                <PlaceCard
                  place={place}
                  timezone={trip.timezone}
                  selected={place.id === selectedId}
                  onSelect={() =>
                    setSelectedId(place.id === selectedId ? null : place.id)
                  }
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <FilterSheet
        open={search.sheet === 'filters'}
        onClose={() => setSheet(false)}
        filters={filters}
        onChange={setFilters}
        prefs={filterPrefs}
        count={count}
        onStandingPreferences={() => void navigate({ to: '/profile' })}
      />
    </>
  )
}
