import { queryOptions } from '@tanstack/react-query'
import { api, throwOnError } from './client'
import type { components } from './schema'

// The schema names are FastAPI's, which names them after the Pydantic classes
// (ADR 004). These aliases are the domain names the app uses, so the rest of
// the frontend never sees the Out/In suffixes.
export type User = components['schemas']['UserOut']
export type Trip = components['schemas']['TripOut']
export type TodayView = components['schemas']['TodayViewOut']
export type PlanItem = components['schemas']['PlanItemOut']
export type TripState = components['schemas']['TripState']
export type ItemStatus = components['schemas']['ItemStatus']
export type TimelineEntry = components['schemas']['TimelineEntryOut']
export type CalendarEventSummary = components['schemas']['CalendarEventSummaryOut']
export type WellnessWindow = components['schemas']['WellnessWindowOut']
export type Explore = components['schemas']['ExploreOut']
export type ExplorePlace = components['schemas']['ExplorePlaceOut']
export type ExploreAnchor = components['schemas']['ExploreAnchorOut']
export type PlaceKind = components['schemas']['PlaceKind']

export function meQueryOptions() {
  return queryOptions({
    queryKey: ['me'],
    queryFn: async () => {
      const client = await api()
      return throwOnError<User>(await client.GET('/me'))
    },
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}

export function tripsQueryOptions(state?: TripState) {
  return queryOptions({
    queryKey: ['trips', state ?? 'all'],
    queryFn: async () => {
      const client = await api()
      return throwOnError(
        await client.GET('/trips', { params: { query: state ? { state } : {} } }),
      ).trips
    },
  })
}

// One trip by id, for the detail route. Deliberately not a lookup in the
// /trips list: the detail screen is where an archived or dismissed trip is
// read, and a deep link to one must resolve whatever the list happens to
// carry. Same cache key prefix, so a confirm still invalidates both.
export function tripQueryOptions(tripId: string) {
  return queryOptions({
    queryKey: ['trips', tripId],
    queryFn: async () => {
      const client = await api()
      return throwOnError<Trip>(
        await client.GET('/trips/{trip_id}', { params: { path: { trip_id: tripId } } }),
      )
    },
  })
}

export function todayQueryOptions(tripId: string) {
  return queryOptions({
    queryKey: ['trips', tripId, 'today'],
    queryFn: async () => {
      const client = await api()
      return throwOnError<TodayView>(
        await client.GET('/trips/{trip_id}/today', {
          params: { path: { trip_id: tripId } },
        }),
      )
    },
  })
}

export function timelineQueryOptions(tripId: string, day?: string) {
  return queryOptions({
    queryKey: ['trips', tripId, 'timeline', day ?? 'all'],
    queryFn: async () => {
      const client = await api()
      return throwOnError(
        await client.GET('/trips/{trip_id}/timeline', {
          params: { path: { trip_id: tripId }, query: day ? { day } : {} },
        }),
      ).entries
    },
    // The day rows live here, so this is the query a booking is usually watched
    // through. See pollWhileBooking.
    refetchInterval: pollWhileBooking<TimelineEntry[]>((entries) =>
      entries.map((entry) => entry.plan_item),
    ),
  })
}

export type Plan = components['schemas']['PlanOut']
export type PlanItemOption = components['schemas']['PlanItemOptionOut']
export type Provenance = components['schemas']['ProvenanceOut']
export type ReservationStatus = components['schemas']['ReservationStatus']

/**
 * `working` means a booking is in flight, so anything showing that item follows
 * it until it lands.
 *
 * The alternative was to let whichever component started the booking do the
 * polling, and a sheet closed mid-booking is what exposed that: the executor
 * finished, the row went on saying "Booking…", and the screen only caught up on
 * the next navigation. The server already knows — the item sits at `working`
 * from the moment the user approves until the provider answers — so the query
 * asks while that is true and stops when it is not. Costs nothing when nothing
 * is being booked, and it is right no matter which surface is open or which one
 * started it.
 *
 * Both queries need it, and for the same reason: the trip screen's day rows
 * come from the timeline, the review surfaces from the plan, and a booking can
 * be watched from either.
 */
const BOOKING_POLL_MS = 1000

function anyBookingInFlight(items: (PlanItem | null | undefined)[]): boolean {
  return items.some((item) => item?.status === 'working')
}

function pollWhileBooking<T>(select: (data: T) => (PlanItem | null | undefined)[]) {
  return (query: { state: { data?: unknown } }) => {
    const data = query.state.data as T | undefined
    if (data === undefined) return false as const
    return anyBookingInFlight(select(data)) ? BOOKING_POLL_MS : (false as const)
  }
}

export function planQueryOptions(tripId: string) {
  return queryOptions({
    queryKey: ['trips', tripId, 'plan'],
    queryFn: async () => {
      const client = await api()
      return throwOnError<Plan>(
        await client.GET('/trips/{trip_id}/plan', { params: { path: { trip_id: tripId } } }),
      )
    },
    refetchInterval: pollWhileBooking<Plan>((plan) => plan.items),
    // A trip the agent has not planned yet answers 404, which is an answer,
    // not a transient failure worth retrying.
    retry: false,
  })
}

export function provenanceQueryOptions(itemId: string) {
  return queryOptions({
    queryKey: ['plan-items', itemId, 'provenance'],
    queryFn: async () => {
      const client = await api()
      return throwOnError<Provenance>(
        await client.GET('/plan-items/{item_id}/provenance', {
          params: { path: { item_id: itemId } },
        }),
      )
    },
  })
}

export async function acceptPlanItem(
  itemId: string,
  updatedAt: string,
): Promise<PlanItem> {
  const client = await api()
  return throwOnError<PlanItem>(
    await client.POST('/plan-items/{item_id}/accept', {
      params: { path: { item_id: itemId } },
      body: { updated_at: updatedAt },
    }),
  )
}

export async function acceptAllPlanItems(tripId: string): Promise<Plan> {
  const client = await api()
  // No token: the server accepts whatever is open at the moment it runs, so
  // there is nothing here for the client to hold a stale copy of.
  return throwOnError<Plan>(
    await client.POST('/trips/{trip_id}/plan/accept-all', {
      params: { path: { trip_id: tripId } },
    }),
  )
}

export async function selectPlanItemOption(
  itemId: string,
  optionId: string,
  updatedAt: string,
): Promise<PlanItem> {
  const client = await api()
  return throwOnError<PlanItem>(
    await client.POST('/plan-items/{item_id}/select-option', {
      params: { path: { item_id: itemId } },
      body: { option_id: optionId, updated_at: updatedAt },
    }),
  )
}

export async function skipPlanItem(
  itemId: string,
  updatedAt: string,
  remove = false,
): Promise<PlanItem> {
  const client = await api()
  return throwOnError<PlanItem>(
    await client.POST('/plan-items/{item_id}/skip', {
      params: { path: { item_id: itemId } },
      body: { updated_at: updatedAt, remove },
    }),
  )
}

// --- Actions (booking, cancelling) ---------------------------------------

export type PendingAction = components['schemas']['PendingActionOut']
export type ActionType = components['schemas']['ActionType']
export type ActionStatus = components['schemas']['ActionStatus']
export type Reservation = components['schemas']['ReservationOut']

/** Nothing more will happen to an action in one of these. */
const TERMINAL_ACTIONS = new Set<ActionStatus>(['completed', 'failed', 'canceled'])

export function isActionSettled(action: PendingAction | undefined): boolean {
  return action !== undefined && TERMINAL_ACTIONS.has(action.status)
}

/**
 * One action, polled while it is still moving.
 *
 * The contract also serves `GET /actions/{id}/events` as SSE, and this is the
 * polling fallback it names. Polling is what the screen uses today because it
 * survives the nginx proxy and a reconnect without any code of its own; the
 * stream is the upgrade when the cost of asking every second is real.
 */
export function actionQueryOptions(actionId: string | undefined) {
  return queryOptions({
    queryKey: ['actions', actionId],
    queryFn: async () => {
      const client = await api()
      return throwOnError<PendingAction>(
        await client.GET('/actions/{action_id}', {
          params: { path: { action_id: actionId as string } },
        }),
      )
    },
    enabled: actionId !== undefined,
    // Stop asking once it has settled: the answer cannot change again.
    refetchInterval: (query) =>
      isActionSettled(query.state.data as PendingAction | undefined) ? false : 1000,
  })
}

export async function createAction(
  body: components['schemas']['ActionCreateIn'],
  idempotencyKey: string,
): Promise<PendingAction> {
  const client = await api()
  return throwOnError<PendingAction>(
    await client.POST('/actions', {
      body,
      params: { header: { 'Idempotency-Key': idempotencyKey } },
    }),
  )
}

export async function approveAction(
  actionId: string,
  updatedAt: string,
): Promise<PendingAction> {
  const client = await api()
  return throwOnError<PendingAction>(
    await client.POST('/actions/{action_id}/approve', {
      params: { path: { action_id: actionId } },
      body: { updated_at: updatedAt },
    }),
  )
}

export type TripCreate = components['schemas']['TripCreateIn']

// The key must be stable across retries of the same logical create (the
// server contract dedupes on it, even though dedup itself lands later).
export async function createTrip(
  body: TripCreate,
  idempotencyKey: string,
): Promise<Trip> {
  const client = await api()
  return throwOnError<Trip>(
    await client.POST('/trips', {
      body,
      params: { header: { 'Idempotency-Key': idempotencyKey } },
    }),
  )
}

export async function confirmTrip(tripId: string, updatedAt: string): Promise<Trip> {
  const client = await api()
  return throwOnError<Trip>(
    await client.POST('/trips/{trip_id}/confirm', {
      params: { path: { trip_id: tripId } },
      body: { updated_at: updatedAt },
    }),
  )
}

export async function dismissTrip(tripId: string, updatedAt: string): Promise<Trip> {
  const client = await api()
  return throwOnError<Trip>(
    await client.POST('/trips/{trip_id}/dismiss', {
      params: { path: { trip_id: tripId } },
      body: { updated_at: updatedAt },
    }),
  )
}

/** Deletes our stored token and marks the grant revoked. The row survives, so
 * the profile can say "disconnected" rather than silently showing nothing. */
export async function disconnectSource(kind: SourceKind): Promise<void> {
  const client = await api()
  throwOnError(
    await client.DELETE('/me/sources/{kind}', { params: { path: { kind } } }),
  )
}

export async function logout(): Promise<void> {
  const client = await api()
  throwOnError(await client.POST('/auth/logout'))
}

export type Preferences = components['schemas']['PreferencesOut']
export type PreferencesUpdate = components['schemas']['PreferencesUpdateIn']
export type ConnectedSource = components['schemas']['ConnectedSourceOut']
export type SourceKind = ConnectedSource['kind']

export function preferencesQueryOptions() {
  return queryOptions({
    queryKey: ['me', 'preferences'],
    queryFn: async () => {
      const client = await api()
      return throwOnError<Preferences>(await client.GET('/me/preferences'))
    },
  })
}

export function sourcesQueryOptions() {
  return queryOptions({
    queryKey: ['me', 'sources'],
    queryFn: async () => {
      const client = await api()
      // The whole payload, not just the rows: `connectable` is what says a
      // Connect button may be offered for a kind the user has no row for.
      return throwOnError(await client.GET('/me/sources'))
    },
  })
}

export async function updatePreferences(
  patch: PreferencesUpdate,
): Promise<Preferences> {
  const client = await api()
  return throwOnError<Preferences>(
    await client.PATCH('/me/preferences', { body: patch }),
  )
}

export interface ExploreFilters {
  category?: PlaceKind
  query?: string
  radiusM?: number
}

/** Explore for one trip. The filters are in the key, so switching a category
 *  chip reads from cache on the way back rather than re-fetching. */
export function exploreQueryOptions(tripId: string, filters: ExploreFilters = {}) {
  const { category, query, radiusM } = filters
  return queryOptions({
    queryKey: ['trips', tripId, 'explore', category ?? 'all', query ?? '', radiusM ?? 0],
    queryFn: async () => {
      const client = await api()
      return throwOnError<Explore>(
        await client.GET('/explore', {
          params: {
            query: {
              trip_id: tripId,
              ...(category ? { category } : {}),
              ...(query ? { query } : {}),
              ...(radiusM ? { radius_m: radiusM } : {}),
            },
          },
        }),
      )
    },
  })
}

// --- Assistant (one utterance, applied to this trip's plan) ---------------

export type AssistantTurn = components['schemas']['AssistantTurnOut']

/**
 * Say something about a trip's plan and have the agent act on it.
 *
 * The key is the caller's, not generated here: a retry of a lost response has
 * to send the same one, or the traveler pays for a second model call and may
 * get a second answer to a question they asked once.
 */
export async function askAssistant(
  tripId: string,
  utterance: string,
  idempotencyKey: string,
): Promise<AssistantTurn> {
  const client = await api()
  return throwOnError<AssistantTurn>(
    await client.POST('/trips/{trip_id}/assistant', {
      params: {
        path: { trip_id: tripId },
        header: { 'Idempotency-Key': idempotencyKey },
      },
      body: { utterance },
    }),
  )
}
