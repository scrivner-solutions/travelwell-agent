import type { Plan, PlanItem, Trip } from '@/api/queries'
import { isPast } from './trips'

/**
 * What a trip's detail screen is *about*. Not `trips.state`: a stage blends
 * the lifecycle with how far the plan has got, which is what the design
 * canvas's detail layouts actually distinguish.
 *
 * The canvas has a fifth, `needsInput` (Lisbon: dates, but no hotel). It is
 * absent here because the contract cannot express it — `Trip` carries no
 * lodging field and no missing-facts list — and a screen must not invent an
 * absence it has no way to see.
 */
export type TripStage = 'waiting' | 'proposed' | 'accepted' | 'done'

/** Items still waiting on a decision. The same test `PlanSection` applies. */
export function openPlanItems(plan: Plan): PlanItem[] {
  return plan.items.filter(
    (item) => item.status === 'suggested' || item.status === 'awaiting_user',
  )
}

export function tripStage(trip: Trip, plan?: Plan): TripStage {
  // Tense first: a finished trip is a retrospective whatever its plan says.
  if (isPast(trip)) return 'done'
  // A 404 from /plan is an answer, not a failure — it means "not planned yet".
  if (plan === undefined || plan.items.length === 0) return 'waiting'
  return openPlanItems(plan).length > 0 ? 'proposed' : 'accepted'
}

// The state card's 1px border and its chip's dot and ink, one set per stage.
// Traced from the canvas's `chipFor` map: grey is dormant, periwinkle is the
// agent proposing, blue is settled, warm grey is filed.
const chromeByStage: Record<TripStage, { border: string; dot: string; ink: string }> = {
  waiting: { border: 'border-border', dot: 'bg-muted-soft', ink: 'text-muted' },
  proposed: { border: 'border-agent-soft', dot: 'bg-agent-bright', ink: 'text-agent' },
  accepted: {
    border: 'border-border-confirmed',
    dot: 'bg-state-confirmed',
    ink: 'text-primary-deep',
  },
  done: { border: 'border-border', dot: 'bg-state-archived', ink: 'text-muted-soft' },
}

export function stageChrome(stage: TripStage) {
  return chromeByStage[stage]
}

/**
 * The line under the trip name. Lifecycle stages defer to `state_line`, which
 * the server authors ("Confirmed - will start preparing closer to the trip");
 * plan stages template their own, because `state_line` says nothing about a
 * plan and would read as a contradiction beside one.
 */
export function stageChip(trip: Trip, stage: TripStage, plan?: Plan): string {
  if (stage === 'proposed') {
    const open = plan ? openPlanItems(plan).length : 0
    return `Plan ready · ${open} to review`
  }
  if (stage === 'accepted') {
    return trip.plan_progress === 'booking' ? 'Plan accepted · booking' : 'Plan accepted'
  }
  return trip.state_line ?? ''
}

export type StageCopy = { head: string; body?: string; note: string }

/**
 * Head, body and note for the state card.
 *
 * Voice rule: never the agent's first person, and never narrative the app
 * cannot support. The two plan stages therefore hand the job to the server —
 * `plan.headline` and `plan.provenance_summary` are real, third-person, and
 * already shown on the trip screen — and only the two stages with no plan to
 * quote are templated here.
 */
export function stageCopy(
  trip: Trip,
  stage: TripStage,
  plan: Plan | undefined,
  stats: RetroStat[],
): StageCopy {
  if (stage === 'waiting') {
    // Wording shared with PlanSection's no-plan-yet state, so the two surfaces
    // cannot describe the same wait differently.
    return trip.plan_progress === 'preparing'
      ? {
          head: 'Your plan is being built',
          body: 'It lands here when it is ready. Nothing to do until then.',
          note: 'You will get one notification when the plan is ready. Nothing before that.',
        }
      : {
          head: 'Nothing to do yet',
          body: 'Planning starts about a week before you go, once the calendar for these days has settled.',
          note: 'You will get one notification when the plan is ready. Nothing before that.',
        }
  }

  if (stage === 'proposed') {
    const open = plan ? openPlanItems(plan).length : 0
    return {
      head: plan?.headline ?? `${open} ${open === 1 ? 'window' : 'windows'} to review`,
      body: plan?.provenance_summary,
      note: 'Reservations still ask you first.',
    }
  }

  if (stage === 'accepted') {
    // Counts the list it sits above, rather than holding its own opinion: its
    // own filter kept `skipped`, so the head read one higher than the rows.
    const live = windowItems(plan, stage).length
    return {
      head: `${live} ${live === 1 ? 'window is' : 'windows are'} in your plan`,
      body: plan?.provenance_summary,
      note: 'Reservations still ask you first.',
    }
  }

  // done. The numbers are the story, and they are in the stat tiles directly
  // below — so this states what they add up to and stops. No body: anything
  // longer would be narrative about a trip nothing in the app watched.
  const kept = stats.find((s) => s.label === 'kept')?.n ?? 0
  const failed = stats.find((s) => s.label === 'failed')?.n ?? 0
  const skipped = stats.find((s) => s.label === 'skipped')?.n ?? 0
  const total = kept + failed + skipped
  return {
    head:
      total === 0
        ? 'Nothing was planned for this trip'
        : // `kept === total`, not `skipped === 0`: a window can also fail to be
          // kept by failing to book, and the old test called that every window.
          kept === total
          ? 'You kept every window'
          : kept === 0
            ? 'None of these windows happened'
            : `You kept ${kept} of ${total} windows`,
    note: 'Archived trips are read-only.',
  }
}

export type RetroStat = { n: number; label: string }

/**
 * The retrospective's tiles: `kept` and `skipped` always, the two reservation
 * outcomes only when there were any. `label` doubles as the key `stageCopy`
 * reads, so the headline and the tiles can never disagree about the count.
 *
 * `removed` is in no tile: Q4's scope is that a removed item was withdrawn
 * before it could happen, which is not the same as skipping it.
 */
export function retrospectiveStats(plan: Plan | undefined): RetroStat[] {
  if (plan === undefined) return []
  const stood = (i: PlanItem) =>
    i.status === 'confirmed' || i.status === 'planned' || i.status === 'changed'
  // Whether it happened is the reservation's answer, not the status's: a
  // `planned` dinner nobody could book did not happen, and counting it as kept
  // headed a retrospective "You kept every window" over a COULDN'T BOOK row.
  const failed = plan.items.filter(
    (i) => stood(i) && i.reservation?.status === 'failed',
  ).length
  const kept = plan.items.filter(
    (i) => stood(i) && i.reservation?.status !== 'failed',
  ).length
  const skipped = plan.items.filter((i) => i.status === 'skipped').length
  const booked = plan.items.filter((i) => i.reservation?.status === 'confirmed').length
  // Both reservation tiles appear only when there were any: a "0 booked" tile on
  // a trip that never wanted a reservation reports on a thing never in question.
  const tiles: RetroStat[] = [{ n: kept, label: 'kept' }]
  if (booked > 0) tiles.push({ n: booked, label: 'booked' })
  if (failed > 0) tiles.push({ n: failed, label: 'failed' })
  tiles.push({ n: skipped, label: 'skipped' })
  return tiles
}

export function windowsTitle(stage: TripStage): string {
  if (stage === 'proposed') return 'Proposed windows'
  if (stage === 'accepted') return 'In your plan'
  return 'What happened'
}

/**
 * Which plan items the windows list shows, in time order.
 *
 * This is Q4's missing scope. Q4 deletes `skipped` and `removed` rows rather
 * than badging them — but that rule was written for the live timeline, which
 * answers "what is happening". The retrospective answers "what happened", and
 * a skipped window is part of that answer. So skipped rows survive here and
 * only here; `removed` survives nowhere, because the user took it out.
 */
export function windowItems(plan: Plan | undefined, stage: TripStage): PlanItem[] {
  if (plan === undefined) return []
  const shown = plan.items.filter((item) =>
    stage === 'done'
      ? item.status !== 'removed'
      : item.status !== 'removed' && item.status !== 'skipped',
  )
  return [...shown].sort((a, b) => a.starts_at.localeCompare(b.starts_at))
}
