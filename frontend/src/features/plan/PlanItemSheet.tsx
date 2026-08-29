import { Info } from 'lucide-react'
import type { PlanItem } from '@/api/queries'
import { Sheet } from '@/components/ui/Sheet'
import { formatTripDay, formatTripTime, formatTripTimeRange } from '@/lib/time'
import { GateError } from './GateError'
import { OptionRow } from './OptionRow'
import { isEditable, usePlanItem } from './usePlanItem'

/**
 * One plan item, opened from its row on a timeline.
 *
 * This is the only route outside the review flow to swap what fills a window or
 * take it out of the plan, and it exists because a row you can see but cannot
 * answer is a dead end: the review flow is a queue over everything still open,
 * and answering *this one* is a different act from working through all of them.
 *
 * What it deliberately does not carry is the keep/skip gate. That lives in the
 * review flow, and a gate answered in two places is a gate that can be answered
 * twice differently. Design source: `isItem` in TravelWellPlan.dc.html.
 */
function SheetBody({
  item,
  tripId,
  timezone,
  tripIsPast,
  onShowProvenance,
  onClose,
}: {
  item: PlanItem
  tripId: string
  timezone: string
  tripIsPast: boolean
  onShowProvenance: (itemId: string) => void
  onClose: () => void
}) {
  const gate = usePlanItem(tripId, item, onClose)
  const options = item.options ?? []
  const open = isEditable(item, tripIsPast)
  const selected = options.find((o) => o.state === 'selected')

  return (
    <>
      <p className="text-label font-semibold uppercase tracking-wide text-muted-soft">
        {formatTripDay(item.starts_at, timezone)}
      </p>
      <p className="mt-1.5 text-body text-muted">
        {item.ends_at !== undefined
          ? formatTripTimeRange(item.starts_at, item.ends_at, timezone)
          : formatTripTime(item.starts_at, timezone)}
        {selected?.display_summary !== undefined && ` · ${selected.display_summary}`}
      </p>

      <div className="mt-3.5 flex flex-wrap gap-1.5">
        <button
          onClick={() => onShowProvenance(item.id)}
          className="flex items-center gap-1.5 rounded-tile border border-agent-soft bg-state-suggested-soft px-2.5 py-1.5 text-label font-medium text-agent hover:border-agent-bright focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          {selected?.reason ?? 'Why this'}
          <Info className="size-3.5 flex-none text-agent-bright" aria-hidden />
        </button>
        {item.needs_reservation && (
          <span className="rounded-tile bg-state-neutral-soft px-2.5 py-1.5 text-label font-medium text-muted">
            Needs a reservation
          </span>
        )}
      </div>

      {/* All the app can say about a refused booking: the contract carries the
          status but not the provider's reason, and retrying is the reservation
          flow's job, which is not built. Saying less would hide it entirely. */}
      {item.reservation?.status === 'failed' && (
        <p className="mt-3.5 text-body-sm font-semibold text-state-attention">
          This booking was refused and was not made.
        </p>
      )}

      {open && options.length > 1 && (
        <>
          <p className="mt-5 mb-2.5 text-label font-semibold uppercase tracking-wide text-muted-soft">
            Other options
          </p>
          <div role="radiogroup" aria-label="Options" className="flex flex-col gap-2.5">
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
        </>
      )}

      {open && (
        <button
          onClick={() => gate.remove.mutate()}
          disabled={gate.pending}
          className="mt-3.5 h-12 w-full rounded-chip border border-border bg-card text-body-sm font-semibold text-muted hover:bg-state-neutral-soft disabled:opacity-60"
        >
          {gate.remove.isPending ? 'Removing…' : 'Remove from plan'}
        </button>
      )}

      {/* Closed, and the server would refuse a change with 409. Say so rather
          than showing buttons that cannot work. The two reasons are different
          and read differently: a live plan can still be changed by the agent,
          a finished trip cannot be changed by anyone. */}
      {!open && (
        <p className="mt-4 text-caption text-muted-soft text-pretty">
          {tripIsPast
            ? 'This trip has ended. Its plan is a record of what happened.'
            : 'This one is settled. Changes to it now go through the agent.'}
        </p>
      )}

      <GateError gate={gate} />
    </>
  )
}

export function PlanItemSheet({
  item,
  tripId,
  timezone,
  tripIsPast,
  onClose,
  onShowProvenance,
}: {
  item: PlanItem | undefined
  tripId: string
  timezone: string
  /** A finished trip's plan is a record: it opens to read, never to change. */
  tripIsPast: boolean
  onClose: () => void
  onShowProvenance: (itemId: string) => void
}) {
  return (
    <Sheet
      open={item !== undefined}
      onClose={onClose}
      title={item ? (item.selected_option?.display_name ?? item.title) : ''}
    >
      {/* Mounted only while open, so a failed remove cannot still be on screen
          the next time a row is tapped. */}
      {item !== undefined && (
        <SheetBody
          item={item}
          tripId={tripId}
          timezone={timezone}
          tripIsPast={tripIsPast}
          onShowProvenance={onShowProvenance}
          onClose={onClose}
        />
      )}
    </Sheet>
  )
}
