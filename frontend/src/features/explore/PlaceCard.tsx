import type { ExplorePlace } from '@/api/queries'
import { CardButton } from '@/components/ui/Card'
import { hoursLabel } from './hours'

/** What a day pass costs, in the words the profile uses. */
function dayPassLabel(cents: number): string {
  return cents === 0 ? 'Free or with a membership' : `$${(cents / 100).toFixed(0)} day pass`
}

/* The design's 48px photo tile is absent on purpose: `photo_url` is a field the
 * Google provider never fills, so a tile would be an empty square on every live
 * row. It arrives with a real photo source, not before.
 *
 * The design's periwinkle line is here, holding a list rather than the
 * prototype's judgement ("Quietest lanes after 6 PM"), which we cannot write.
 * As chips these were five periwinkle boxes per card, and periwinkle means the
 * agent is proposing: five of them on every card spends the loudest colour in
 * the palette on the most ordinary fact on the screen. */

// 11px is the design's badge size and sits below the smallest type token.
const badgeClass =
  'rounded-tile px-2 py-1 text-[11px] font-semibold leading-none'

export interface PlaceCardProps {
  place: ExplorePlace
  timezone: string
  selected: boolean
  onSelect: () => void
}

export function PlaceCard({ place, timezone, selected, onSelect }: PlaceCardProps) {
  const hours = hoursLabel(place.hours, timezone)
  const overBudget = place.over_budget_reason != null

  // The summary usually carries the price ("Healthy American · $$"), so the
  // level is only worth a badge of its own when there is no summary.
  const priceBadge =
    place.day_pass_cents != null
      ? dayPassLabel(place.day_pass_cents)
      : place.summary == null && place.price_level != null
        ? '$'.repeat(place.price_level)
        : null

  return (
    <CardButton
      onClick={onSelect}
      aria-pressed={selected}
      className={`rounded-section ${selected ? 'border-primary bg-surface' : ''}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-body font-semibold">{place.name}</h3>

          {place.summary != null && (
            <p className="mt-1 text-caption text-muted">{place.summary}</p>
          )}

          {place.matched_preferences.length > 0 && (
            <p className="mt-1.5 text-label font-medium text-agent">
              {place.matched_preferences.join(' · ')}
            </p>
          )}

          {(hours != null || priceBadge != null) && (
            <ul className="mt-2 flex flex-wrap gap-[5px]">
              {hours != null && (
                <li
                  className={`${badgeClass} bg-state-neutral-soft ${
                    hours.tight ? 'text-ink' : 'text-muted-soft'
                  }`}
                >
                  {hours.text}
                </li>
              )}
              {priceBadge != null && (
                <li
                  className={`${badgeClass} ${
                    overBudget
                      ? 'bg-state-suggested-soft text-agent'
                      : 'bg-state-neutral-soft text-muted'
                  }`}
                >
                  {priceBadge}
                </li>
              )}
            </ul>
          )}
        </div>

        {place.walk_minutes != null && (
          <span className="flex-none whitespace-nowrap rounded-tile bg-state-neutral-soft px-2.5 py-1.5 text-label font-semibold">
            {place.walk_minutes === 0 ? 'In hotel' : `${place.walk_minutes} min`}
          </span>
        )}
      </div>

      {/* Muted prose, never a chip. A chip reads as something the place has,
          and these are the opposite: what nobody could tell us about it. Kept
          next to the chips on purpose, because "two matches" means something
          different when a third preference was unanswerable rather than unmet. */}
      {place.unknown_notes.length > 0 && (
        <p className="mt-3 text-caption text-muted-soft">
          {place.unknown_notes.join(' · ')}
        </p>
      )}

      {/* Shown, not hidden: the user set the limit and can decide to break it.
          The periwinkle price badge above is the scan target; this is the why. */}
      {place.over_budget_reason != null && (
        <p className="mt-2 text-caption text-muted">{place.over_budget_reason}</p>
      )}
    </CardButton>
  )
}
