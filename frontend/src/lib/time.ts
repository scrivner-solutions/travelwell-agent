import { formatInTimeZone } from 'date-fns-tz'

/**
 * All trip times render in the trip's IANA timezone (trips.timezone), never
 * the device zone: a 5:30 PM Chicago workout must read 5:30 PM from a phone
 * still on San Francisco time. Every screen formats through these helpers.
 */

// The one sanctioned read of the device zone: it answers "where is the user
// now" - labelling trip times shown from another zone, dating the screens
// between trips - never "what time is this trip event".
export function deviceTimeZone(): string | undefined {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined
}

export function formatTripTime(iso: string, timeZone: string): string {
  return formatInTimeZone(iso, timeZone, 'h:mm a')
}

export function formatTripTimeRange(startIso: string, endIso: string, timeZone: string): string {
  return `${formatTripTime(startIso, timeZone)} - ${formatTripTime(endIso, timeZone)}`
}

export function formatTripDay(iso: string, timeZone: string): string {
  return formatInTimeZone(iso, timeZone, 'EEE, MMM d')
}

/** "Tue" alone, for a row that puts the weekday over the time in one column. */
export function formatTripWeekday(iso: string, timeZone: string): string {
  return formatInTimeZone(iso, timeZone, 'EEE')
}

/** Hour 0-23 in the trip's zone, for bucketing a time into part of the day. */
export function tripHour(iso: string, timeZone: string): number {
  return Number(formatInTimeZone(iso, timeZone, 'H'))
}

/**
 * "Aug 25–28", crossing months "Aug 30 – Sep 2" (design: header eyebrows and
 * trip rows never show raw ISO dates). Date-only strings are calendar dates,
 * so they format in UTC - no timezone math applies to them.
 */
export function formatDateRange(startsOn: string, endsOn: string): string {
  const start = new Date(`${startsOn}T00:00:00Z`)
  const end = new Date(`${endsOn}T00:00:00Z`)
  const month = (d: Date) =>
    d.toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' })
  if (
    start.getUTCMonth() === end.getUTCMonth() &&
    start.getUTCFullYear() === end.getUTCFullYear()
  ) {
    return `${month(start)} ${start.getUTCDate()}–${end.getUTCDate()}`
  }
  return `${month(start)} ${start.getUTCDate()} – ${month(end)} ${end.getUTCDate()}`
}

// "Synced 4 min ago" on the profile's source rows. Coarse on purpose: sync
// freshness needs minute resolution at most.
export function formatAgo(iso: string): string {
  const mins = Math.round((Date.now() - Date.parse(iso)) / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} hr ago`
  return `${Math.round(hours / 24)} days ago`
}
