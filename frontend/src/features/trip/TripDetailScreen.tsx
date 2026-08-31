import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getRouteApi } from '@tanstack/react-router'
import { ChevronLeft } from 'lucide-react'
import { ApiError } from '@/api/client'
import {
  acceptAllPlanItems,
  planQueryOptions,
  preferencesQueryOptions,
  sourcesQueryOptions,
  tripQueryOptions,
  tripsQueryOptions,
} from '@/api/queries'
import { DegradedState, LoadingState } from '@/components/ui/ScreenState'
import { ProfileButton } from '@/components/ui/ProfileButton'
import { formatDateRange } from '@/lib/time'
import { evidenceRows, isPast, preferenceRow } from '@/lib/trips'
import { stageChip, stageChrome, tripStage } from '@/lib/tripStage'
import { ReviewFlow } from '@/features/plan/ReviewFlow'
import { PlanItemSheet } from '@/features/plan/PlanItemSheet'
import { ProvenanceSheet } from '@/features/plan/ProvenanceSheet'
import { TripFactsCard } from './TripFactsCard'
import { TripListRow } from './TripListRow'
import { TripStateCard } from './TripStateCard'
import { TripWindows } from './TripWindows'

const route = getRouteApi('/_shell/trip_/$tripId')

/** The in-card button pair: 46px, equal width, primary then outline. */
function CardButton({
  onClick,
  variant,
  disabled = false,
  children,
}: {
  onClick: () => void
  variant: 'primary' | 'outline'
  disabled?: boolean
  children: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`h-control-inline flex-1 rounded-chip px-3.5 text-body-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-60 ${
        variant === 'primary'
          ? 'bg-primary text-white hover:bg-primary-deep'
          : 'border border-border bg-card text-ink hover:bg-state-neutral-soft'
      }`}
    >
      {children}
    </button>
  )
}

/**
 * One trip, whole. The trip tab is a working surface for the trip you are on -
 * a day strip and a timeline - and it was answering for every other trip too,
 * so a finished trip got an empty day strip. This is where the other trips go:
 * what is known, what stage the plan is at, which windows it holds, and the
 * way back out to the rest of them.
 *
 * Design source: the detail screen in TravelWellPlan.dc.html.
 */
export function TripDetailScreen() {
  const { tripId } = route.useParams()
  const navigate = route.useNavigate()
  const queryClient = useQueryClient()
  const [reviewing, setReviewing] = useState(false)
  const [provenanceItem, setProvenanceItem] = useState<string | undefined>(undefined)
  const [openItem, setOpenItem] = useState<string | undefined>(undefined)

  const trip = useQuery(tripQueryOptions(tripId))
  const plan = useQuery(planQueryOptions(tripId))
  const trips = useQuery(tripsQueryOptions())
  // Both degrade to absence rather than blocking the screen: the facts on the
  // card are true whether or not the strip can say where they came from.
  const sources = useQuery(sourcesQueryOptions())
  const prefs = useQuery(preferencesQueryOptions())

  const acceptAll = useMutation({
    mutationFn: () => acceptAllPlanItems(tripId),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ['trips'] })
    },
  })

  // A trip with no plan answers 404, which is an answer. Anything else is a
  // real failure and must not be read as "not planned yet".
  const planMissing = plan.error instanceof ApiError && plan.error.status === 404
  const planData = plan.data
  const openDetail = useCallback(
    (id: string) => void navigate({ to: '/trip/$tripId', params: { tripId: id } }),
    [navigate],
  )

  if (trip.isPending) return <LoadingState label="Loading this trip" />
  if (trip.isError || trip.data === undefined) {
    return (
      <DegradedState
        title="Can't load this trip"
        detail="It may have been dismissed, or TravelWell is unreachable."
        onRetry={() => void trip.refetch()}
      />
    )
  }

  const current = trip.data
  // The stage is undecided until the plan query settles: showing "nothing to
  // do yet" and then swapping in a ready plan would be the screen changing its
  // mind in front of the reader.
  const planSettled = planData !== undefined || planMissing
  const stage = tripStage(current, planData)
  const chip = stageChip(current, stage, planData)
  const { dot, ink } = stageChrome(stage)

  // Your standing instructions, listed with the flights: absent until the
  // profile answers, and absent for good if you have set none.
  const prefRow = preferenceRow(prefs.data)
  const preferenceFacts = prefRow === null ? [] : [prefRow]

  const others = (trips.data ?? []).filter(
    (t) => t.id !== current.id && t.state !== 'detected' && !isPast(t),
  )
  const past = (trips.data ?? []).filter((t) => t.id !== current.id && isPast(t))

  const seeTheDays = (
    <CardButton
      variant="outline"
      onClick={() => void navigate({ to: '/trip', search: { trip: current.id } })}
    >
      See the day by day
    </CardButton>
  )

  return (
    <>
      <header className="flex items-center justify-between gap-3">
        {/* Back to the list, not browser-back: this screen is reachable from a
            notification and from a deep link, where there is nothing behind. */}
        <button
          onClick={() => void navigate({ to: '/trip' })}
          className="-ml-1 flex items-center gap-1.5 rounded-control p-1 text-body-sm font-semibold text-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-primary"
        >
          <ChevronLeft className="size-4" strokeWidth={2.4} aria-hidden />
          Trips
        </button>
        <ProfileButton />
      </header>

      <div className="mt-4">
        <p className="text-eyebrow-wide font-semibold uppercase text-muted-soft">
          {formatDateRange(current.starts_on, current.ends_on)}
          {current.label !== undefined && ` · ${current.label}`}
        </p>
        <h1 className="mt-2.5 font-display text-display-xl">
          {current.destination_name.split(',')[0]}
        </h1>
        {/* Held back until the plan query settles. The stage is what the chip
            names, and a chip that says "Confirmed" and then says "Plan ready"
            has told the reader something untrue on the way past. */}
        {planSettled && chip !== '' && (
          <p className={`mt-3 flex items-center gap-2 text-eyebrow font-semibold uppercase ${ink}`}>
            <span className={`size-dot flex-none rounded-full ${dot}`} aria-hidden />
            {chip}
          </p>
        )}
      </div>

      <div className="mt-5">
        {/* Labelled here and not on the trip screen: there the card is the
            only thing above the fold and needs no introduction, here it is one
            of three cards and has to say which question it answers. */}
        <TripFactsCard
          label="What this is based on"
          rows={[...evidenceRows(current.evidence ?? []), ...preferenceFacts]}
          sources={sources.data?.sources}
        />
      </div>

      <div className="mt-4">
        {plan.isPending && <LoadingState label="Loading the plan" />}
        {plan.isError && !planMissing && (
          <DegradedState
            title="Can't load this trip's plan"
            onRetry={() => void plan.refetch()}
          />
        )}
        {planSettled && (
          <TripStateCard
            trip={current}
            stage={stage}
            plan={planData}
            actions={
              stage === 'proposed' ? (
                <>
                  <CardButton variant="primary" onClick={() => setReviewing(true)}>
                    Review one by one
                  </CardButton>
                  <CardButton
                    variant="outline"
                    disabled={acceptAll.isPending}
                    onClick={() => acceptAll.mutate()}
                  >
                    {acceptAll.isPending ? 'Accepting…' : 'Accept all'}
                  </CardButton>
                </>
              ) : (
                seeTheDays
              )
            }
            error={
              acceptAll.isError ? (
                <p className="mt-3 text-caption font-semibold text-state-attention">
                  Could not accept the plan. Check your connection and retry.
                </p>
              ) : undefined
            }
          />
        )}
      </div>

      {planSettled && (
        <TripWindows
          plan={planData}
          stage={stage}
          timezone={current.timezone}
          onOpenItem={setOpenItem}
        />
      )}

      {others.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-3 text-section font-semibold uppercase text-muted-soft">
            Other trips
          </h2>
          <ul className="flex flex-col gap-2.5">
            {others.map((t) => (
              <li key={t.id}>
                <TripListRow
                  trip={t}
                  onSelect={openDetail}
                  className="border border-border"
                />
              </li>
            ))}
          </ul>
        </section>
      )}

      {past.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-3 text-section font-semibold uppercase text-muted-soft">
            Archive
          </h2>
          <ul className="flex flex-col gap-2.5">
            {past.map((t) => (
              <li key={t.id}>
                {/* No fill: an archived trip is the one row on this screen that
                    is not a live surface, and the canvas says so by leaving the
                    card out rather than by adding a word. */}
                <TripListRow
                  trip={t}
                  onSelect={openDetail}
                  muted
                  className="border border-border-soft"
                />
              </li>
            ))}
          </ul>
        </section>
      )}

      {reviewing && planData !== undefined && (
        <ReviewFlow
          onClose={() => setReviewing(false)}
          plan={planData}
          tripId={current.id}
          tripName={current.destination_name}
          timezone={current.timezone}
          onShowProvenance={setProvenanceItem}
        />
      )}

      {/* Read from the live plan, not captured at tap: a swap made inside the
          sheet has to be visible in the sheet that made it. */}
      <PlanItemSheet
        item={planData?.items.find((i) => i.id === openItem)}
        tripId={current.id}
        timezone={current.timezone}
        tripIsPast={isPast(current)}
        onClose={() => setOpenItem(undefined)}
        onShowProvenance={setProvenanceItem}
      />

      <ProvenanceSheet
        itemId={provenanceItem}
        onClose={() => setProvenanceItem(undefined)}
      />
    </>
  )
}
