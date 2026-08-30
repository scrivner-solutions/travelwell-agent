import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/client'
import { acceptAllPlanItems, planQueryOptions, type Trip } from '@/api/queries'
import { ReviewFlow } from './ReviewFlow'

/**
 * The proposed plan, as one offer rather than a list of cards.
 *
 * The items themselves are already on this screen, in the timeline under the
 * days they fill; repeating them here as a second, interactive list would ask
 * the reader to reconcile two versions of the same thing. So this card carries
 * only what the timeline cannot say - that a plan is being proposed, how it
 * was built, and the two ways to answer it. Design source: the "Proposed plan"
 * card in TravelWellPlan.dc.html.
 */
export function PlanSection({
  trip,
  onShowProvenance,
}: {
  trip: Trip
  onShowProvenance: (itemId: string) => void
}) {
  const plan = useQuery(planQueryOptions(trip.id))
  const queryClient = useQueryClient()
  const [reviewing, setReviewing] = useState(false)

  const acceptAll = useMutation({
    mutationFn: () => acceptAllPlanItems(trip.id),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ['trips', trip.id, 'plan'] })
      void queryClient.invalidateQueries({ queryKey: ['trips'] })
    },
  })

  // A trip with no plan yet is the normal case before the agent activates,
  // not a failure: `preparing` means one is being built right now.
  if (plan.error instanceof ApiError && plan.error.status === 404) {
    return (
      <section className="mt-6">
        <h2 className="text-label font-semibold uppercase tracking-wide text-muted">
          Plan
        </h2>
        <p className="mt-2 text-body-sm text-muted text-pretty">
          {trip.state === 'preparing'
            ? 'Your plan is being built. It lands here when it is ready.'
            : 'No plan yet. Planning starts a week before you go.'}
        </p>
      </section>
    )
  }

  if (plan.isPending || plan.data === undefined) return null

  const open = plan.data.items.filter(
    (i) => i.status === 'suggested' || i.status === 'awaiting_user',
  )

  // Nothing is being proposed, so there is no offer to make. The timeline is
  // already showing what the plan turned into.
  if (open.length === 0) return null

  return (
    <section className="mt-6">
      <div className="rounded-section border border-agent-soft bg-card p-[17px]">
        {/* text-eyebrow, not text-label + tracking-wide: the micro sizes carry
            their own tracking and are not interchangeable with the UI sizes. */}
        <p className="flex items-center gap-2 text-eyebrow font-semibold uppercase text-agent">
          <span className="size-dot rounded-full bg-agent-bright" aria-hidden />
          Proposed plan
        </p>
        <h2 className="mt-2.5 mb-1.5 font-display text-heading-sm text-balance">
          {plan.data.headline}
        </h2>
        {plan.data.provenance_summary !== undefined && (
          <p className="text-caption text-muted-soft text-pretty">
            {plan.data.provenance_summary}
          </p>
        )}

        <div className="mt-[15px] flex gap-[9px]">
          <button
            onClick={() => setReviewing(true)}
            className="h-control-inline flex-1 rounded-chip bg-primary text-body-sm font-semibold text-white hover:bg-primary-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            Review one by one
          </button>
          <button
            onClick={() => acceptAll.mutate()}
            disabled={acceptAll.isPending}
            className="h-control-inline flex-none rounded-chip border border-border bg-card px-4 text-body-sm font-semibold text-ink hover:bg-state-neutral-soft disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            {acceptAll.isPending ? 'Accepting…' : 'Accept all'}
          </button>
        </div>
        {acceptAll.isError && (
          <p className="mt-3 text-caption font-semibold text-state-attention">
            Could not accept the plan. Check your connection and retry.
          </p>
        )}
        <p className="mt-[11px] text-caption text-muted-soft text-pretty">
          Reservations still ask you first.
        </p>
      </div>

      {/* Mounted only while reviewing: the mount is what snapshots the queue,
          so closing and reopening starts a genuinely fresh pass. */}
      {reviewing && (
        <ReviewFlow
          onClose={() => setReviewing(false)}
          plan={plan.data}
          tripId={trip.id}
          tripName={trip.destination_name}
          timezone={trip.timezone}
          onShowProvenance={onShowProvenance}
        />
      )}
    </section>
  )
}
