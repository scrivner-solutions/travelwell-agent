import type { ExplorePlace } from '@/api/queries'
import { CardButton } from '@/components/ui/Card'

/** What a day pass costs, in the words the profile uses. */
function dayPassLabel(cents: number): string {
  return cents === 0 ? 'Free or with a membership' : `$${(cents / 100).toFixed(0)} day pass`
}

export interface PlaceCardProps {
  place: ExplorePlace
  selected: boolean
  onSelect: () => void
}

export function PlaceCard({ place, selected, onSelect }: PlaceCardProps) {
  // The walk is already in the corner, and the summary usually carries the
  // price ("Healthy American · $$"), so this line adds only what is missing.
  const facts = [
    place.day_pass_cents != null ? dayPassLabel(place.day_pass_cents) : null,
    place.summary == null && place.price_level != null
      ? '$'.repeat(place.price_level)
      : null,
  ].filter((f): f is string => f !== null)

  return (
    <CardButton
      onClick={onSelect}
      aria-pressed={selected}
      className={selected ? 'border-border-strong bg-surface' : ''}
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-body font-semibold">{place.name}</h3>
        {place.walk_minutes != null && (
          <span className="flex-none text-body-sm text-muted">
            {place.walk_minutes} min
          </span>
        )}
      </div>

      {place.summary != null && (
        <p className="mt-1 text-body-sm text-muted">{place.summary}</p>
      )}

      {facts.length > 0 && (
        <p className="mt-1 text-body-sm text-muted">{facts.join(' · ')}</p>
      )}

      {place.matched_preferences.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {place.matched_preferences.map((preference) => (
            <li
              key={preference}
              className="rounded-control bg-state-suggested-soft px-3 py-1.5 text-body-sm font-medium text-state-suggested"
            >
              {preference}
            </li>
          ))}
        </ul>
      )}

      {/* Shown, not hidden: the user set the limit and can decide to break it. */}
      {place.over_budget_reason != null && (
        <p className="mt-3 text-body-sm text-muted">{place.over_budget_reason}</p>
      )}
    </CardButton>
  )
}
