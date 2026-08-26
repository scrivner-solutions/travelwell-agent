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
