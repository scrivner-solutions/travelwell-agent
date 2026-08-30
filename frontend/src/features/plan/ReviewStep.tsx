import { Info } from 'lucide-react'
import type { PlanItem } from '@/api/queries'
import {
  formatTripDay,
  formatTripTime,
  formatTripTimeRange,
  tripHour,
} from '@/lib/time'
import { GateError } from './GateError'
import { OptionRow } from './OptionRow'
import { isOpenToDecision, usePlanItem } from './usePlanItem'

/**
 * One item as the review flow presents it: the opening first, then what fills
 * it, then the decision.
 *
 * The order is the argument. Leading with the window says the agent found a
 * gap in your days and is offering to use it; leading with the restaurant
 * would just be a recommendation. Design source: the review card in
 * TravelWellPlan.dc.html.
 *
 * The prototype offered a single "Swap · <next>" button. Options render as a
 * list here instead, because choosing is a comparison and a toggle makes you
 * hold in your head the thing you cannot see. Rejected candidates never reach
 * this list; they live in provenance with the reason they lost.
 */

/**
 * Heading for an item that fills no opening. A meal is placed against the day
 * rather than against a gap the agent had to find, so calling its slot "free"
 * would describe an evening nobody was worried about.
 */
function unplacedHeading(item: PlanItem, timezone: string): string {
  const at = formatTripTime(item.starts_at, timezone)
  if (item.kind !== 'meal') return `${at}, free`
  const hour = tripHour(item.starts_at, timezone)
  const meal = hour < 11 ? 'Breakfast' : hour < 16 ? 'Lunch' : 'Dinner'
  return `${meal} at ${at}`
}

export function ReviewStep({
  item,
  tripId,
  timezone,
  onShowProvenance,
  onDecided,
}: {
  item: PlanItem
  tripId: string
  timezone: string
  onShowProvenance: (itemId: string) => void
  /** Fired once a Keep or Skip succeeds, so the review can advance. */
  onDecided: () => void
}) {
  const gate = usePlanItem(tripId, item, onDecided)
  const options = item.options ?? []
  const selected = options.find((o) => o.state === 'selected')
  const open = isOpenToDecision(item)
  const undecided = item.status === 'suggested' || item.status === 'awaiting_user'
  const window = item.window

  return (
    <div>
      {/* The opening, before the thing that fills it. */}
      <p className="text-label font-semibold uppercase tracking-wide text-agent">
        {formatTripDay(item.starts_at, timezone)}
      </p>
      <h3 className="mt-3 font-display text-display font-normal text-balance">
        {window?.label ?? unplacedHeading(item, timezone)}
      </h3>
      {window?.gap_explanation !== undefined && (
        <p className="mt-2 text-body-sm text-muted text-pretty">
          {window.gap_explanation}
        </p>
      )}

      <div className="mt-5 rounded-panel border border-border bg-card p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-body font-semibold">
              {selected?.display_name ?? item.title}
            </p>
            {selected?.display_summary !== undefined && (
              <p className="mt-1 text-body-sm text-muted text-pretty">
                {selected.display_summary}
              </p>
            )}
          </div>
          <span className="flex-none rounded-lg bg-state-neutral-soft px-2.5 py-1.5 text-caption font-semibold text-ink tabular-nums">
            {window != null
              ? formatTripTimeRange(item.starts_at, window.ends_at, timezone)
              : formatTripTime(item.starts_at, timezone)}
          </span>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={() => onShowProvenance(item.id)}
            className="flex items-center gap-1.5 rounded-lg border border-agent-soft bg-state-suggested-soft px-2.5 py-1.5 text-caption font-medium text-agent hover:border-agent-bright focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {selected?.reason ?? 'Why this'}
            <Info className="size-3.5 flex-none text-agent-bright" aria-hidden />
          </button>
          {item.needs_reservation === true && (
            <span className="rounded-lg bg-state-neutral-soft px-2.5 py-1.5 text-caption font-medium text-muted">
              Needs a reservation
            </span>
          )}
        </div>

        {/* Alternatives sit beside the selection, not behind a toggle. */}
        {open && options.length > 1 && (
          <div role="radiogroup" aria-label="Options" className="mt-4 flex flex-col gap-2">
            {options.map((option) => (
              <OptionRow
                key={option.id}
                option={option}
                chosen={option.state === 'selected'}
                disabled={gate.pending}
                onChoose={() => gate.choose.mutate(option.id)}
              />
            ))}
          </div>
        )}

        {open && (
          <button
            onClick={() => gate.skip.mutate()}
            disabled={gate.pending}
            className="mt-4 h-11 w-full rounded-panel border border-border bg-card text-body-sm font-semibold text-muted hover:bg-state-neutral-soft disabled:opacity-60"
          >
            {gate.skip.isPending ? 'Skipping…' : 'Skip this'}
          </button>
        )}
      </div>

      {undecided && (
        <button
          onClick={() => gate.accept.mutate()}
          disabled={gate.pending}
          className="mt-4 h-13 w-full rounded-panel bg-primary text-body font-semibold text-white hover:bg-primary-deep disabled:opacity-60"
        >
          {gate.accept.isPending ? 'Keeping…' : 'Keep this'}
        </button>
      )}

      <GateError gate={gate} />

      <p className="mt-3 text-center text-caption text-muted">Nothing is booked yet.</p>
    </div>
  )
}
