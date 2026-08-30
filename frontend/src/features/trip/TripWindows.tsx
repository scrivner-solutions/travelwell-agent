import type { Plan } from '@/api/queries'
import { windowItems, windowsTitle, type TripStage } from '@/lib/tripStage'
import { PlanItemRow } from './TimelineRow'

/**
 * Every window this trip's plan holds, titled by what the reader is looking
 * at: an offer, a plan, or a record. The three titles are the whole difference
 * between the stages here — the rows themselves are identical, because a window
 * is the same object whichever tense you read it in, and identical to the day
 * timeline's rows for exactly the same reason.
 */
export function TripWindows({
  plan,
  stage,
  timezone,
  onOpenItem,
}: {
  plan?: Plan
  stage: TripStage
  timezone: string
  onOpenItem: (itemId: string) => void
}) {
  const items = windowItems(plan, stage)
  if (items.length === 0) return null

  return (
    <section className="mt-6">
      <div className="mb-3 flex items-baseline justify-between gap-3 px-0.5">
        <h2 className="font-display text-heading-sm">{windowsTitle(stage)}</h2>
        <p className="flex-none text-caption text-muted-soft">
          {items.length} {items.length === 1 ? 'window' : 'windows'}
        </p>
      </div>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          // Tappable at every stage, including the retrospective: reading why a
          // window was there is legitimate after the fact, and the sheet gates
          // its own actions on whether the item can still be changed.
          <PlanItemRow
            key={item.id}
            item={item}
            timezone={timezone}
            withWeekday
            onSelect={onOpenItem}
          />
        ))}
      </ul>
    </section>
  )
}
