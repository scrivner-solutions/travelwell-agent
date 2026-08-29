import type { components } from '@/api/schema'
import { itemBadge } from '@/lib/timeline'

type PlanItem = components['schemas']['PlanItem']

/**
 * The only place an item's status becomes a word.
 *
 * Renders nothing for most items, which is the point: a badge is reserved for
 * something true that the user cannot act on and would not otherwise know, so
 * only a booking in flight, a booking done, a booking refused and a plan the
 * agent changed under them get one. Everything else is a place they can go or
 * a state they already chose, and those say nothing.
 *
 * It takes the whole item rather than the status because two of the four
 * badges are not decidable from the status alone - `confirmed` is only "Booked"
 * if a reservation was ever wanted, and "Couldn't book" lives on the
 * reservation. The decision itself is in `lib/timeline`, where it is tested.
 *
 * A badge is ink on the page, never a chip: colour carries the state, and a
 * background would make it compete with the row it annotates.
 */
export function StatusBadge({ item }: { item: PlanItem }) {
  const badge = itemBadge(item)
  if (badge === null) return null
  return (
    <span
      className={`flex-none self-center whitespace-nowrap text-badge font-semibold uppercase ${badge.className}`}
    >
      {badge.label}
    </span>
  )
}
