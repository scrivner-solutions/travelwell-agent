import { queryOptions } from '@tanstack/react-query'
import { api, throwOnError } from './client'
import type { components } from './schema'

export type User = components['schemas']['User']
export type Trip = components['schemas']['Trip']
export type TodayView = components['schemas']['TodayView']
export type PlanItem = components['schemas']['PlanItem']
export type TripState = components['schemas']['TripState']
export type ItemStatus = components['schemas']['ItemStatus']

export function meQueryOptions() {
  return queryOptions({
    queryKey: ['me'],
    queryFn: async () => throwOnError<User>(await api().GET('/me')),
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}

export function tripsQueryOptions(state?: TripState) {
  return queryOptions({
    queryKey: ['trips', state ?? 'all'],
    queryFn: async () =>
      throwOnError(
        await api().GET('/trips', { params: { query: state ? { state } : {} } }),
      ).trips,
  })
}

export function todayQueryOptions(tripId: string) {
  return queryOptions({
    queryKey: ['trips', tripId, 'today'],
    queryFn: async () =>
      throwOnError<TodayView>(
        await api().GET('/trips/{tripId}/today', {
          params: { path: { tripId } },
        }),
      ),
  })
}
