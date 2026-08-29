import { Sheet } from '@/components/ui/Sheet'
import type { Trip } from '@/api/queries'
import { isPast } from '@/lib/trips'
import { TripListRow } from './TripListRow'

/**
 * Every trip, one tap from the header. This replaced two accordions at the
 * foot of the trip screen: switching trips is navigation, and navigation that
 * costs a scroll and an expand is navigation nobody finds.
 *
 * Past trips live here rather than on the screen, which is the one thing that
 * should collapse — an archive is content, and old content at that.
 */
export function TripsSheet({
  open,
  onClose,
  trips,
  selectedId,
  onSelect,
  onAddTrip,
}: {
  open: boolean
  onClose: () => void
  trips: Trip[]
  selectedId?: string
  onSelect: (id: string) => void
  onAddTrip: () => void
}) {
  // Ahead of you before behind you. The server already orders each group by
  // start date, so partitioning is all the ordering this needs.
  const ordered = [...trips.filter((t) => !isPast(t)), ...trips.filter(isPast)]

  return (
    <Sheet open={open} onClose={onClose} title="Your trips">
      <ul className="flex flex-col gap-2.5">
        {ordered.map((trip) => (
          <li key={trip.id}>
            <TripListRow
              trip={trip}
              current={trip.id === selectedId}
              onSelect={onSelect}
              className={`border-[1.5px] ${
                trip.id === selectedId ? 'border-primary' : 'border-border'
              }`}
            />
          </li>
        ))}
      </ul>

      {/* The only way to add a trip once you have one, so it is a row here and
          not a plus in the header competing with the trip you came to read. */}
      <button
        onClick={onAddTrip}
        className="mt-4 h-[var(--control-height)] w-full rounded-control border border-dashed border-border-faint text-body-sm font-semibold text-muted hover:bg-card focus-visible:outline-2 focus-visible:outline-primary"
      >
        Add a trip manually
      </button>
    </Sheet>
  )
}
