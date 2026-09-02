import { formatInTimeZone } from 'date-fns-tz'
import type { ExplorePlace } from '@/api/queries'

/*
 * The filter sheet's model, kept pure so the whole thing is tested without a
 * screen. Everything here narrows the places the server already sent: hours,
 * walk minutes, day-pass price and amenities are all in the payload, so no
 * filter costs a request and the chip counts stay put while the list narrows.
 *
 * The rule that shapes every clause: unknown keeps, it never hides. A place
 * whose hours or amenities the provider never gave passes, and its card says
 * what could not be judged. Hiding it would make a data gap look like a poor
 * match.
 */

export type TimeWindow = 'now' | 'next2h' | 'evening'
export const TIME_WINDOWS: TimeWindow[] = ['now', 'next2h', 'evening']
export const WINDOW_LABELS: Record<TimeWindow, string> = {
  now: 'Now',
  next2h: 'Next 2 hrs',
  evening: 'This evening',
}

/** Minutes, or null for no limit. */
export type WalkMax = 5 | 10 | 20 | null
export const WALK_OPTIONS: { label: string; value: WalkMax }[] = [
  { label: '5 min', value: 5 },
  { label: '10 min', value: 10 },
  { label: '20 min', value: 20 },
  { label: 'Any', value: null },
]

export interface Filters {
  window: TimeWindow
  walk: WalkMax
  /** Hide day passes above the profile's cap. */
  underCap: boolean
  /** Hide places whose amenities miss every one the profile asks for. */
  amenities: boolean
}

export const DEFAULT_FILTERS: Filters = {
  window: 'next2h',
  walk: null,
  underCap: false,
  amenities: false,
}

/** What the two toggles compare against. Undefined while the profile loads. */
export interface FilterPrefs {
  dayPassBudgetCents: number | null
  amenities: string[]
}

export interface FilterContext {
  prefs: FilterPrefs | undefined
  now: Date
  timezone: string
}

const DAY_MINUTES = 24 * 60
const EVENING: [number, number] = [18 * 60, 22 * 60]

function tripMinutes(now: Date, timezone: string): number {
  return (
    Number(formatInTimeZone(now, timezone, 'H')) * 60 +
    Number(formatInTimeZone(now, timezone, 'm'))
  )
}

/** The window as minutes of the trip-local day, or null once it is behind
 *  us: "this evening" after ten at night is not a filter, it is a fact, and
 *  the empty state says so instead of showing nothing for no reason. A window
 *  that would run past midnight stops there, meaning "for the rest of today". */
export function windowRange(
  window: TimeWindow,
  now: Date,
  timezone: string,
): [number, number] | null {
  const minutes = tripMinutes(now, timezone)
  switch (window) {
    case 'now':
      return [minutes, Math.min(minutes + 60, DAY_MINUTES)]
    case 'next2h':
      return [minutes, Math.min(minutes + 120, DAY_MINUTES)]
    case 'evening':
      return minutes >= EVENING[1] ? null : EVENING
  }
}

/** Open for the whole of the range, closed for some of it, or unknown. A day
 *  missing from hours we do have reads as closed, as the badge reads it. */
export function openThrough(
  hours: ExplorePlace['hours'],
  range: [number, number],
  now: Date,
  timezone: string,
): boolean | null {
  if (hours == null) return null
  const today = hours[formatInTimeZone(now, timezone, 'EEE').toLowerCase()]
  const open = today?.[0]
  const close = today?.[1]
  if (open === undefined || close === undefined) return false
  return open <= range[0] && close >= range[1]
}

export function passes(place: ExplorePlace, filters: Filters, ctx: FilterContext): boolean {
  const range = windowRange(filters.window, ctx.now, ctx.timezone)
  if (range === null) return false
  if (openThrough(place.hours, range, ctx.now, ctx.timezone) === false) return false

  if (filters.walk !== null && place.walk_minutes != null && place.walk_minutes > filters.walk) {
    return false
  }

  const cap = ctx.prefs?.dayPassBudgetCents ?? null
  if (filters.underCap && cap !== null && place.day_pass_cents != null && place.day_pass_cents > cap) {
    return false
  }

  const wanted = ctx.prefs?.amenities ?? []
  if (
    filters.amenities &&
    wanted.length > 0 &&
    place.amenities != null &&
    place.amenities.length > 0 &&
    !place.amenities.some((a) => wanted.includes(a))
  ) {
    return false
  }

  return true
}

/** How many controls are off their default: the badge on the Filters button. */
export function activeCount(filters: Filters): number {
  return (
    (filters.window !== DEFAULT_FILTERS.window ? 1 : 0) +
    (filters.walk !== null ? 1 : 0) +
    (filters.underCap ? 1 : 0) +
    (filters.amenities ? 1 : 0)
  )
}

/** "4 places · next 2 hrs · under 10 min walk": the count, the window, and
 *  then only what is narrowing it. */
export function constraintLine(count: number, filters: Filters): string {
  const parts = [
    count === 1 ? '1 place' : `${count} places`,
    WINDOW_LABELS[filters.window].toLowerCase(),
  ]
  if (filters.walk !== null) parts.push(`under ${filters.walk} min walk`)
  if (filters.underCap) parts.push('under your pass cap')
  if (filters.amenities) parts.push('with your amenities')
  return parts.join(' · ')
}
