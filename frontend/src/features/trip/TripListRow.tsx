import type { Trip } from '@/api/queries'
import { needsYouLabel, tripDot, tripStateWord } from '@/lib/trips'
import { formatDateRange } from '@/lib/time'

/**
 * One trip in a list: dot, name, dates, and a single right-hand phrase. Used
 * by the trips sheet and by "Other trips" on the trip screen, so the two can
 * never describe the same trip differently.
 *
 * Border utilities are the caller's, not the base: the sheet marks the current
 * trip with a 1.5px blue edge and the screen's list does not, and Tailwind
 * gives no reliable way to override one border class with another. `muted` is
 * a prop for the same reason - the archive drops the fill entirely, which is a
 * swap of the base rather than something a caller can layer over it.
 */
export function TripListRow({
  trip,
  onSelect,
  current = false,
  muted = false,
  className = '',
}: {
  trip: Trip
  onSelect: (id: string) => void
  current?: boolean
  muted?: boolean
  className?: string
}) {
  // The gate outranks the lifecycle word: one is work waiting on you, the
  // other is a fact you can do nothing about.
  const needsYou = needsYouLabel(trip.needs_you_count, trip.needs_you_kind ?? undefined)

  return (
    <button
      onClick={() => onSelect(trip.id)}
      aria-current={current || undefined}
      className={`flex w-full items-center gap-3 rounded-panel px-4 py-3.5 text-left hover:bg-surface focus-visible:outline-2 focus-visible:outline-primary ${muted ? 'bg-transparent' : 'bg-card'} ${className}`}
    >
      <span className={`size-2 flex-none rounded-full ${tripDot(trip)}`} aria-hidden />
      <span className="min-w-0 flex-1">
        <span
          className={`block truncate text-body font-semibold ${muted ? 'text-muted' : ''}`}
        >
          {trip.destination_name}
        </span>
        <span className="mt-1 block truncate text-caption text-muted-soft">
          {formatDateRange(trip.starts_on, trip.ends_on)}
          {trip.label !== undefined && ` · ${trip.label}`}
        </span>
      </span>
      <span
        className={`max-w-[7.5rem] flex-none text-right text-label ${
          needsYou !== null ? 'font-semibold text-state-attention' : 'text-muted-soft'
        }`}
      >
        {needsYou ?? tripStateWord(trip)}
      </span>
    </button>
  )
}
