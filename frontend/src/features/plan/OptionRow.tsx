import type { PlanItemOption } from '@/api/queries'

/**
 * One candidate. The chosen one is outlined; the rest are one tap away.
 *
 * Shared by the review flow and the item sheet so that choosing means the same
 * thing in both. Rejected candidates never reach this list; they live in
 * provenance with the reason they lost.
 */
export function OptionRow({
  option,
  chosen,
  onChoose,
  disabled,
}: {
  option: PlanItemOption
  chosen: boolean
  onChoose: () => void
  disabled: boolean
}) {
  return (
    <button
      role="radio"
      aria-checked={chosen}
      onClick={onChoose}
      disabled={disabled || chosen}
      className={`flex w-full items-start gap-3 rounded-control border-[1.5px] bg-card px-3.5 py-3.5 text-left disabled:cursor-default focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
        chosen ? 'border-primary' : 'border-border hover:border-primary disabled:opacity-60'
      }`}
    >
      <span className="min-w-0 flex-1">
        <span className="block text-body-sm font-semibold">{option.display_name}</span>
        {option.display_summary !== undefined && (
          <span className="mt-1 block text-label text-muted-soft">
            {option.display_summary}
          </span>
        )}
      </span>
      {option.distance_minutes !== undefined && (
        <span className="flex-none self-center text-label font-semibold text-muted tabular-nums">
          {option.distance_minutes === 0 ? 'Here' : `${option.distance_minutes} min`}
        </span>
      )}
    </button>
  )
}
