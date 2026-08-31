import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { exploreQueryOptions, tripsQueryOptions, type PlaceKind } from '@/api/queries'
import { focusTrip } from '@/lib/trips'
import { EmptyState, LoadingState } from '@/components/ui/ScreenState'
import { ProfileButton } from '@/components/ui/ProfileButton'
import { CategoryChips } from './CategoryChips'
import { PlaceCard } from './PlaceCard'
import { PlaceMap } from './PlaceMap'

/* The design's section heading names the category in the user's language
 * rather than repeating the chip. There is no "All" in the design because it
 * opens on Workout; ours has one, and it says where rather than what. */
const HEADINGS: Partial<Record<PlaceKind, string>> = {
  workout: 'Ways to move',
  food: 'Places to eat',
  outdoor: 'Outside near you',
  recovery: 'Rest and recovery',
}

function radiusLabel(meters: number): string {
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${meters} m`
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
  // One selection drives both surfaces, which is what keeps the pins and the
  // cards in step rather than each holding its own idea of "current".
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const trips = useQuery(tripsQueryOptions())
  const trip = trips.data ? focusTrip(trips.data) : undefined
  const explore = useQuery({
    ...exploreQueryOptions(trip?.id ?? '', { category }),
    enabled: trip !== undefined,
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
  const count = data.places.length

  return (
    <>
      <Header eyebrow={eyebrow} />

      {/* Full bleed: the band is the screen's surface, not a card on it. The
          shell owns the gutter, so escaping it is this screen's business. */}
      <div className="-mx-4">
        <PlaceMap
          anchor={anchor}
          places={data.places}
          radiusM={data.radius_m}
          timezone={trip.timezone}
          selectedId={selectedId}
          onSelect={setSelectedId}
        >
          <CategoryChips kinds={data.kinds} selected={category} onSelect={setCategory} />
        </PlaceMap>
      </div>

      <section className="pt-4">
        <h2 className="font-display text-heading-sm">{heading}</h2>
        <p className="mt-1.5 text-label font-medium text-muted-soft">
          {count === 1 ? '1 place' : `${count} places`} · within {radiusLabel(data.radius_m)}
        </p>

        {count === 0 ? (
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
            {data.places.map((place) => (
              <li key={place.id}>
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
    </>
  )
}
