import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Panel } from '@/components/ui/Panel'
import { preferencesQueryOptions, type Plan, type PlanItem } from '@/api/queries'
import { formatTripDay, formatTripTime, tripHour } from '@/lib/time'
import { ReviewStep } from './ReviewStep'

/**
 * The review flow: the open items one at a time, then what it added up to.
 *
 * The queue is frozen when the flow opens but each card is looked up in the
 * live plan, which is the only way both halves stay right: keeping an item
 * takes it out of "undecided", so a queue recomputed from live data would
 * renumber itself under the reader, while a frozen *copy* of the items would
 * hand the next mutation a concurrency token that a swap has already rotated.
 *
 * The prototype held every Keep in local state and committed the lot from the
 * summary. Each decision is written as it is made here instead, so closing the
 * app four items in does not throw away four answers. That is also why the
 * summary ends on Done rather than Accept: by then there is nothing left to
 * commit, only the standing reservations to name.
 */

const UNDECIDED = new Set(['suggested', 'awaiting_user'])
const DROPPED = new Set(['skipped', 'removed'])

function timeOfDay(iso: string, timezone: string): string {
  const hour = tripHour(iso, timezone)
  if (hour < 12) return 'morning'
  return hour < 17 ? 'afternoon' : 'evening'
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

function Summary({
  kept,
  skipped,
  timezone,
  onClose,
}: {
  kept: PlanItem[]
  skipped: number
  timezone: string
  onClose: () => void
}) {
  const prefs = useQuery(preferencesQueryOptions())
  const days = new Set(kept.map((i) => formatTripDay(i.starts_at, timezone))).size
  const reservations = kept.filter((i) => i.needs_reservation === true).length
  const calendar = kept.length - reservations

  const spread = ['morning', 'afternoon', 'evening']
    .map((part) => ({
      part,
      n: kept.filter((i) => timeOfDay(i.starts_at, timezone) === part).length,
    }))
    .filter((p) => p.n > 0)
    .map((p) => plural(p.n, p.part))

  if (kept.length === 0) {
    return (
      <>
        <h3 className="font-display text-display font-normal text-balance">
          Nothing left in this plan
        </h3>
        <p className="mt-2 text-body-sm text-muted text-pretty">
          {skipped > 0
            ? 'Everything here was skipped. Planning runs again tomorrow morning.'
            : 'There was nothing waiting on you.'}
        </p>
        <button
          onClick={onClose}
          className="mt-6 h-13 w-full rounded-panel border border-border bg-card text-body font-semibold text-ink hover:bg-state-neutral-soft"
        >
          Close
        </button>
      </>
    )
  }

  return (
    <>
      <h3 className="font-display text-display font-normal text-balance">
        {plural(kept.length, 'addition')} across {plural(days, 'day')}
      </h3>
      <p className="mt-2 text-body-sm text-muted text-pretty">
        {spread.join(', ')}
        {skipped > 0 ? `. ${skipped} skipped.` : '.'}
      </p>

      <ul className="mt-5 overflow-hidden rounded-panel border border-border bg-card">
        {kept.map((item) => (
          <li
            key={item.id}
            className="flex items-center gap-3 border-b border-border-soft px-4 py-3.5 last:border-b-0"
          >
            <span
              className={`size-2 flex-none rounded-full ${
                item.needs_reservation === true
                  ? 'bg-state-attention'
                  : 'bg-state-confirmed'
              }`}
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-body-sm font-semibold">
                {item.title}
              </span>
              <span className="mt-0.5 block text-caption text-muted">
                {formatTripDay(item.starts_at, timezone)} ·{' '}
                {formatTripTime(item.starts_at, timezone)}
              </span>
            </span>
            <span
              className={`flex-none text-label font-semibold ${
                item.needs_reservation === true
                  ? 'text-state-attention'
                  : 'text-state-confirmed'
              }`}
            >
              {item.needs_reservation === true ? 'Reservation' : 'Plan item'}
            </span>
          </li>
        ))}
      </ul>

      <p className="mb-3 mt-6 text-label font-semibold uppercase tracking-wide text-muted">
        What this needs from you
      </p>
      <div className="flex flex-col gap-2">
        {reservations > 0 && (
          <NeedRow
            title={`${plural(reservations, 'reservation')} to confirm`}
            detail="You see the times and say yes before anything is booked."
            attention
          />
        )}
        {calendar > 0 && (
          <NeedRow
            title={
              prefs.data?.allow_calendar_write === true
                ? `${plural(calendar, 'event')} added to your calendar`
                : 'Your calendar stays untouched'
            }
            detail={
              prefs.data?.allow_calendar_write === true
                ? 'You allowed this in your profile. Turn it off any time.'
                : 'Turn on calendar writing in your profile to have these added.'
            }
          />
        )}
      </div>

      <button
        onClick={onClose}
        className="mt-6 h-13 w-full rounded-panel bg-primary text-body font-semibold text-white hover:bg-primary-deep"
      >
        Done
      </button>
    </>
  )
}

function NeedRow({
  title,
  detail,
  attention = false,
}: {
  title: string
  detail: string
  attention?: boolean
}) {
  return (
    <div className="flex items-start gap-3 rounded-panel border border-border bg-card px-4 py-3">
      <span
        className={`mt-1.5 size-1.5 flex-none rounded-full ${
          attention ? 'bg-state-attention' : 'bg-state-confirmed'
        }`}
      />
      <div className="min-w-0">
        <p className="text-body-sm font-semibold">{title}</p>
        <p className="mt-0.5 text-caption text-muted text-pretty">{detail}</p>
      </div>
    </div>
  )
}

export function ReviewFlow({
  onClose,
  plan,
  tripId,
  tripName,
  timezone,
  onShowProvenance,
}: {
  onClose: () => void
  plan: Plan
  tripId: string
  tripName: string
  timezone: string
  onShowProvenance: (itemId: string) => void
}) {
  // Mounting is the snapshot: the caller mounts this only when a review
  // starts, so the queue is captured once and each new review gets a new one.
  const [queue] = useState(() =>
    plan.items.filter((i) => UNDECIDED.has(i.status)).map((i) => i.id),
  )
  const [index, setIndex] = useState(0)

  const current = plan.items.find((i) => i.id === queue[index])
  const done = index >= queue.length

  // Read the outcome back off the plan rather than counting taps, so a change
  // someone made in another tab cannot make this lie.
  const reviewed = queue
    .map((id) => plan.items.find((i) => i.id === id))
    .filter((i): i is PlanItem => i !== undefined)
  const kept = reviewed.filter(
    (i) => !UNDECIDED.has(i.status) && !DROPPED.has(i.status),
  )
  const skipped = reviewed.filter((i) => DROPPED.has(i.status)).length

  return (
    <Panel
      open
      onClose={onClose}
      title={done ? 'That is the plan' : `Your ${tripName} plan`}
      closeLabel="Close review"
      aside={
        <span className="flex-none text-caption font-medium text-muted tabular-nums">
          {done ? 'Summary' : `${index + 1} of ${queue.length}`}
        </span>
      }
    >
      {!done && current !== undefined && (
        <ReviewStep
          // Keyed so the next item mounts clean instead of inheriting the
          // previous card's mutation and error state.
          key={current.id}
          item={current}
          tripId={tripId}
          timezone={timezone}
          onShowProvenance={onShowProvenance}
          onDecided={() => setIndex((i) => i + 1)}
        />
      )}
      {done && (
        <Summary
          kept={kept}
          skipped={skipped}
          timezone={timezone}
          onClose={onClose}
        />
      )}
    </Panel>
  )
}
