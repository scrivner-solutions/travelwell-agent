import { SlidersHorizontal } from 'lucide-react'

/** Opens the filter sheet, and wears how many filters are on. Ink-filled when
 *  any is, so a narrowed list never looks like all there is. */
export function FiltersButton({ count, onClick }: { count: number; onClick: () => void }) {
  const active = count > 0
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex h-9 flex-none items-center gap-[7px] rounded-[11px] border px-[13px] text-caption font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
        active ? 'border-ink bg-ink text-map-road' : 'border-border bg-card text-ink hover:bg-surface'
      }`}
    >
      <SlidersHorizontal className="size-[15px]" aria-hidden />
      {active ? `Filters · ${count}` : 'Filters'}
    </button>
  )
}
