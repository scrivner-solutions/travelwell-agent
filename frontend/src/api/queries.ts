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
  })
}

export type Plan = components['schemas']['PlanOut']
export type PlanItemOption = components['schemas']['PlanItemOptionOut']
export type Provenance = components['schemas']['ProvenanceOut']
export type ReservationStatus = components['schemas']['ReservationStatus']

export function planQueryOptions(tripId: string) {
  return queryOptions({
    queryKey: ['trips', tripId, 'plan'],
    queryFn: async () => {
      const client = await api()
      return throwOnError<Plan>(
        await client.GET('/trips/{trip_id}/plan', { params: { path: { trip_id: tripId } } }),
      )
    },
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

export async function logout(): Promise<void> {
  const client = await api()
  throwOnError(await client.POST('/auth/logout'))
}

export type Preferences = components['schemas']['PreferencesOut']
export type PreferencesUpdate = components['schemas']['PreferencesUpdateIn']
export type ConnectedSource = components['schemas']['ConnectedSourceOut']

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
      return throwOnError(await client.GET('/me/sources')).sources
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
