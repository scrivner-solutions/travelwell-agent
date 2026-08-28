import { queryOptions } from '@tanstack/react-query'
import { api, throwOnError } from './client'
import type { components } from './schema'

export type User = components['schemas']['User']
export type Trip = components['schemas']['Trip']
export type TodayView = components['schemas']['TodayView']
export type PlanItem = components['schemas']['PlanItem']
export type TripState = components['schemas']['TripState']
export type ItemStatus = components['schemas']['ItemStatus']
export type TimelineEntry = components['schemas']['TimelineEntry']
export type WellnessWindow = components['schemas']['WellnessWindow']

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

export function todayQueryOptions(tripId: string) {
  return queryOptions({
    queryKey: ['trips', tripId, 'today'],
    queryFn: async () => {
      const client = await api()
      return throwOnError<TodayView>(
        await client.GET('/trips/{tripId}/today', {
          params: { path: { tripId } },
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
        await client.GET('/trips/{tripId}/timeline', {
          params: { path: { tripId }, query: day ? { day } : {} },
        }),
      ).entries
    },
  })
}

export type TripCreate = components['schemas']['TripCreate']

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
    await client.POST('/trips/{tripId}/confirm', {
      params: { path: { tripId } },
      body: { updated_at: updatedAt },
    }),
  )
}

export async function dismissTrip(tripId: string, updatedAt: string): Promise<Trip> {
  const client = await api()
  return throwOnError<Trip>(
    await client.POST('/trips/{tripId}/dismiss', {
      params: { path: { tripId } },
      body: { updated_at: updatedAt },
    }),
  )
}

export async function logout(): Promise<void> {
  const client = await api()
  throwOnError(await client.POST('/auth/logout'))
}

export type Preferences = components['schemas']['Preferences']
export type PreferencesUpdate = components['schemas']['PreferencesUpdate']
export type ConnectedSource = components['schemas']['ConnectedSource']

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
