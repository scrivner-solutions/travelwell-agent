import type { ReactNode } from 'react'
import type { Plan, Trip } from '@/api/queries'
import {
  retrospectiveStats,
  stageChrome,
  stageCopy,
  type TripStage,
} from '@/lib/tripStage'

/**
 * The one card that says what this trip is currently about: a stage-coloured
 * border, a serif headline, a sentence, an optional block of numbers, the
 * actions, and a note on what happens without you.
 *
 * It carries no state of its own. What it says comes from `stageCopy`, which
 * quotes the server where the server has words and templates where it does
 * not; what its buttons do is the caller's, because the actions differ per
 * stage and every one of them is a real mutation or a real navigation.
 */
export function TripStateCard({
  trip,
  stage,
  plan,
  actions,
  error,
}: {
  trip: Trip
  stage: TripStage
  plan?: Plan
  actions?: ReactNode
  error?: ReactNode
}) {
  const stats = stage === 'done' ? retrospectiveStats(plan) : []
  const { head, body, note } = stageCopy(trip, stage, plan, stats)
  const { border } = stageChrome(stage)

  return (
    <div className={`rounded-section border bg-card p-[18px] ${border}`}>
      <p className="font-display text-heading text-pretty">{head}</p>
      {body !== undefined && (
        <p className="mt-2 text-body text-muted text-pretty">{body}</p>
      )}

      {stats.length > 0 && (
        <dl className="mt-4 flex gap-2.5">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className="flex-1 rounded-control border border-border-soft bg-card-muted px-3 py-3.5"
            >
              <dd className="font-display text-display-sm tabular-nums">{stat.n}</dd>
              <dt className="mt-1.5 text-caption text-muted-soft">
                {/* "windows kept", but "2 skipped" needs no noun and "booked"
                    means reservations - so the noun rides with the label. */}
                {stat.label === 'kept'
                  ? `window${stat.n === 1 ? '' : 's'} kept`
                  : stat.label === 'booked'
                    ? `reservation${stat.n === 1 ? '' : 's'}`
                    : 'skipped'}
              </dt>
            </div>
          ))}
        </dl>
      )}

      {actions !== undefined && <div className="mt-[17px] flex gap-[9px]">{actions}</div>}
      {error}
      <p className="mt-3 text-caption text-muted-soft text-pretty">{note}</p>
    </div>
  )
}
