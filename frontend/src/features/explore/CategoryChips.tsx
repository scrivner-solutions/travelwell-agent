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

export function CategoryChips({ kinds, selected, onSelect }: CategoryChipsProps) {
  const total = kinds.reduce((sum, k) => sum + k.count, 0)

  const chip = (active: boolean) =>
    `rounded-control px-3 py-1.5 text-body-sm font-medium ${
      active ? 'bg-ink text-card' : 'bg-surface text-muted hover:bg-state-neutral-soft'
    }`

  return (
    <ul className="flex flex-wrap gap-2">
      <li>
        <button type="button" className={chip(selected === undefined)} onClick={() => onSelect(undefined)}>
          All {total}
        </button>
      </li>
      {kinds.map(({ kind, count }) => (
        <li key={kind}>
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
