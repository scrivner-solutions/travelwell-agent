import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/client'
import {
  acceptPlanItem,
  selectPlanItemOption,
  skipPlanItem,
  type PlanItem,
} from '@/api/queries'

/**
 * Every way a single plan item can be answered, in one place.
 *
 * Two surfaces answer items - the review flow, one at a time, and the item
 * sheet, reached by tapping a row - and they must agree about what a 409 means
 * and about what moves afterwards. Both the plan and the trip row move:
 * answering the last open item flips the trip's badge from bare to Planned.
 */
export function usePlanItem(
  tripId: string,
  item: PlanItem,
  /** Fired once a Keep, Skip or Remove succeeds, so a queue can advance. */
  onDecided?: () => void,
) {
  const queryClient = useQueryClient()
  const onSettled = () => {
    void queryClient.invalidateQueries({ queryKey: ['trips', tripId, 'plan'] })
    void queryClient.invalidateQueries({ queryKey: ['trips'] })
  }
  // Only answering the gate advances a review; swapping an option does not,
  // and neither does a 409, which has to stay on screen to be read.
  const accept = useMutation({
    mutationFn: () => acceptPlanItem(item.id, item.updated_at),
    onSuccess: onDecided,
    onSettled,
  })
  const skip = useMutation({
    mutationFn: () => skipPlanItem(item.id, item.updated_at),
    onSuccess: onDecided,
    onSettled,
  })
  // Skip and remove are the same endpoint and different acts: skipping says
  // this one will not happen, removing says it should not have been offered.
  // The retrospective keeps the first and never shows the second.
  const remove = useMutation({
    mutationFn: () => skipPlanItem(item.id, item.updated_at, true),
    onSuccess: onDecided,
    onSettled,
  })
  const choose = useMutation({
    mutationFn: (optionId: string) =>
      selectPlanItemOption(item.id, optionId, item.updated_at),
    onSettled,
  })
  const error = accept.error ?? skip.error ?? remove.error ?? choose.error
  return {
    accept,
    skip,
    remove,
    choose,
    error,
    pending:
      accept.isPending || skip.isPending || remove.isPending || choose.isPending,
    conflicted: error instanceof ApiError && error.status === 409,
  }
}

export type PlanItemGate = ReturnType<typeof usePlanItem>

/** The gates an item can still be answered at; past these it is held by a
 * booking or already declined, and the server refuses with 409. */
const OPEN_TO_DECISION = new Set(['suggested', 'awaiting_user', 'planned', 'changed'])

export function isOpenToDecision(item: PlanItem): boolean {
  return OPEN_TO_DECISION.has(item.status)
}

/**
 * Whether a surface may offer to change this item. Two axes, and both have to
 * pass: the item has to still be answerable, and the trip must not be over.
 *
 * The second is not a nicety. A finished trip's plan is a record of what
 * happened, and the retrospective filters `removed` rows out — so a removal
 * there would delete the user's own history rather than edit a plan. The item's
 * status cannot see this: a past trip can still hold a `planned` item, which is
 * exactly the London dinner whose booking was refused.
 */
export function isEditable(item: PlanItem, tripIsPast: boolean): boolean {
  return !tripIsPast && isOpenToDecision(item)
}
