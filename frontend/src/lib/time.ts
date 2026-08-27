import { formatInTimeZone } from 'date-fns-tz'

/**
 * All trip times render in the trip's IANA timezone (trips.timezone), never
 * the device zone: a 5:30 PM Chicago workout must read 5:30 PM from a phone
 * still on San Francisco time. Every screen formats through these helpers.
 */

export function formatTripTime(iso: string, timeZone: string): string {
  return formatInTimeZone(iso, timeZone, 'h:mm a')
}

export function formatTripTimeRange(startIso: string, endIso: string, timeZone: string): string {
  return `${formatTripTime(startIso, timeZone)} - ${formatTripTime(endIso, timeZone)}`
}

export function formatTripDay(iso: string, timeZone: string): string {
  return formatInTimeZone(iso, timeZone, 'EEE, MMM d')
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
