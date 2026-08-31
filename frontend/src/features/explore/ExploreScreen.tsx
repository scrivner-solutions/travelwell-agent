import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { exploreQueryOptions, tripsQueryOptions, type PlaceKind } from '@/api/queries'
import { focusTrip } from '@/lib/trips'
import { EmptyState, LoadingState } from '@/components/ui/ScreenState'
import { ProfileButton } from '@/components/ui/ProfileButton'
import { CategoryChips } from './CategoryChips'
import { PlaceCard } from './PlaceCard'
import { PlaceMap } from './PlaceMap'

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

  const header = (
    <header className="mb-4 flex items-center justify-between">
      <h1 className="font-display text-display">Explore</h1>
      <ProfileButton />
    </header>
  )

  if (trips.isPending || (trip !== undefined && explore.isPending)) {
    return (
      <>
        {header}
        <LoadingState label="Finding places near you" />
      </>
    )
  }

  if (trip === undefined) {
    return (
      <>
        {header}
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
        {header}
        <EmptyState
          title={`We don't know where ${trip.destination_name} is yet`}
          detail="Places appear once the trip has a location to measure from."
        />
      </>
    )
  }

  const anchor = data.anchor

  return (
    <>
      {header}

      <p className="mb-3 text-body-sm text-muted">
        {anchor.is_hotel ? `Around ${anchor.name}` : `Around central ${anchor.name}`}
      </p>

      <div className="mb-4">
        <CategoryChips kinds={data.kinds} selected={category} onSelect={setCategory} />
      </div>

      <PlaceMap
        anchor={anchor}
        places={data.places}
        radiusM={data.radius_m}
        selectedId={selectedId}
        onSelect={setSelectedId}
      />

      {data.places.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            title="Nothing cached here yet"
            detail="We have not looked around this destination for that category."
          />
        </div>
      ) : (
        <ul className="mt-4 space-y-3">
          {data.places.map((place) => (
            <li key={place.id}>
              <PlaceCard
                place={place}
                selected={place.id === selectedId}
                onSelect={() =>
                  setSelectedId(place.id === selectedId ? null : place.id)
                }
              />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
