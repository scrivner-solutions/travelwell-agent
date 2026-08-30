import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/client'
import {
  actionQueryOptions,
  approveAction,
  createAction,
  isActionSettled,
  type PendingAction,
  type PlanItem,
} from '@/api/queries'

/**
 * Booking a table: propose, confirm, then watch it happen.
 *
 * Two steps rather than one because the server assembles what will actually be
 * sent, and the confirm sheet shows that rather than what the client guessed.
 * Proposing writes a row and books nothing; approving hands it to the executor
 * and returns immediately, which is why there is a third state at all — a real
 * booking is not finished when the request comes back.
 */
export function useBooking(tripId: string, item: PlanItem) {
  const queryClient = useQueryClient()
  const [actionId, setActionId] = useState<string | undefined>()
  const [partySize, setPartySize] = useState(2)
  // One key per attempt, held across retries: tapping twice is the same
  // booking arriving twice, and the server dedupes on exactly this.
  const attemptKey = useRef<string>(crypto.randomUUID())

  const { data: action } = useQuery(actionQueryOptions(actionId))

  const settled = isActionSettled(action)
  const refreshPlan = useCallback(() => {
    // The booking lives on the item, so the sheet behind this reads it from
    // the plan rather than from the action once it is over.
    void queryClient.invalidateQueries({ queryKey: ['trips', tripId, 'plan'] })
    void queryClient.invalidateQueries({ queryKey: ['trips'] })
  }, [queryClient, tripId])

  const propose = useMutation({
    mutationFn: () =>
      createAction(
        {
          action_type: 'make_reservation',
          trip_id: tripId,
          plan_item_id: item.id,
          payload: { party_size: partySize },
        },
        attemptKey.current,
      ),
    onSuccess: (created: PendingAction) => setActionId(created.id),
  })

  // The booking lands on the item, not on the action, so the plan has to be
  // refetched once it settles or the sheet keeps rendering the item as it was
  // before: "Needs a reservation" beside a confirmation code.
  useEffect(() => {
    if (settled) refreshPlan()
  }, [settled, refreshPlan])

  const confirm = useMutation({
    mutationFn: (target: PendingAction) =>
      approveAction(target.id, target.updated_at),
    onSuccess: (approved: PendingAction) => {
      // Seed the poll with what approve just returned, so the first render
      // after confirming is already the approved state rather than the stale one.
      queryClient.setQueryData(['actions', approved.id], approved)
      // Approving moves the item to `working` server-side, and the plan query
      // follows an item in that state on its own. Refetching here is what arms
      // that: without it the cached plan still says `planned`, nothing polls,
      // and closing this sheet would strand the row until the next navigation.
      refreshPlan()
    },
  })

  /** Start over: a refused booking can be tried again, and a retry is a new
   * action rather than a second run of the one that failed. */
  const reset = useCallback(() => {
    attemptKey.current = crypto.randomUUID()
    setActionId(undefined)
    propose.reset()
    confirm.reset()
    refreshPlan()
  }, [propose, confirm, refreshPlan])

  const error = propose.error ?? confirm.error
  return {
    action,
    partySize,
    setPartySize,
    propose,
    confirm,
    reset,
    settled,
    refreshPlan,
    /** Proposed and awaiting the user's yes. Nothing has been booked. */
    awaitingConfirm: action?.status === 'proposed',
    /** Handed to the executor: the provider is being asked. */
    running: action?.status === 'approved' || action?.status === 'executing',
    error,
    pending: propose.isPending || confirm.isPending,
    conflicted: error instanceof ApiError && error.status === 409,
  }
}

export type Booking = ReturnType<typeof useBooking>

/**
 * The gates are ordered, and booking is the third one.
 *
 * An item has to be kept before it can be booked: "accepting is not agreeing to
 * book" is the rule `accept_all_plan_items` states, and offering a table on a
 * suggestion nobody has answered would collapse two gates into one. These are
 * the same two states the executor will move onto the booking track
 * (`_BOOKING_TRACK_ENTRY`); if they disagree the button runs an action that
 * silently declines to move the row.
 */
const KEPT = new Set<PlanItem['status']>(['planned', 'changed'])

/**
 * Whether this item can be booked right now.
 *
 * A booking is offered when the item has been kept, wants a table, and does not
 * already hold one. A refused or cancelled attempt does not count as holding
 * one: that is the case the retry exists for, and the reason the reservation
 * now carries why it was refused.
 */
export function canBook(item: PlanItem, tripIsPast: boolean): boolean {
  if (tripIsPast || !item.needs_reservation || !KEPT.has(item.status)) return false
  const status = item.reservation?.status
  return status === undefined || status === 'failed' || status === 'canceled'
}
