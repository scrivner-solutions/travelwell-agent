import type { PlaceKind } from '@/api/queries'

/* The brief's four categories, in its order. Lodging is never a chip: the
 * hotel is the anchor the other places are measured from. */
const LABELS: Partial<Record<PlaceKind, string>> = {
  workout: 'Workout',
  food: 'Food',
  outdoor: 'Outdoor',
  recovery: 'Recovery',
}

export interface CategoryChipsProps {
  kinds: { kind: PlaceKind; count: number }[]
  selected: PlaceKind | undefined
  onSelect: (kind: PlaceKind | undefined) => void
}

/* These sit on the map rather than above it, which is what makes the band read
 * as the screen's surface instead of one more card in a list. They carry the
 * only shadow on the screen for the same reason: they are floating over ground. */
export function CategoryChips({ kinds, selected, onSelect }: CategoryChipsProps) {
  const total = kinds.reduce((sum, k) => sum + k.count, 0)

  const chip = (active: boolean) =>
    `flex h-9 flex-none items-center rounded-full border px-[15px] text-caption font-semibold shadow-[var(--shadow-chip)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-55 disabled:shadow-none ${
      active ? 'border-ink bg-ink text-card' : 'border-border bg-card/95 text-ink'
    }`

  return (
    <ul className="flex gap-[7px] overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      <li className="flex-none">
        <button type="button" className={chip(selected === undefined)} onClick={() => onSelect(undefined)}>
          All {total}
        </button>
      </li>
      {kinds.map(({ kind, count }) => (
        <li key={kind} className="flex-none">
          <button
            type="button"
            className={chip(selected === kind)}
            onClick={() => onSelect(selected === kind ? undefined : kind)}
            // A category with nothing in it is still the truth about this trip.
            disabled={count === 0}
            aria-disabled={count === 0}
          >
            {LABELS[kind] ?? kind} {count}
          </button>
        </li>
      ))}
    </ul>
  )
}
