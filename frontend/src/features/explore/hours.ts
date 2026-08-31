import { formatInTimeZone } from 'date-fns-tz'
import type { ExplorePlace } from '@/api/queries'

/*
 * Opening hours are the one fact on a place card that changes while you look
 * at it, so they are read against the trip's clock rather than the device's -
 * the rule lib/time.ts sets for every other time in the app.
 */

type Hours = NonNullable<ExplorePlace['hours']>

/** "9 PM", "6:30 AM": minutes are dropped on the hour, as the design writes them. */
function clock(minutes: number): string {
  const hour24 = Math.floor(minutes / 60) % 24
  const minute = minutes % 60
  const hour = hour24 % 12 === 0 ? 12 : hour24 % 12
  const suffix = hour24 >= 12 ? 'PM' : 'AM'
  return `${hour}${minute ? `:${String(minute).padStart(2, '0')}` : ''} ${suffix}`
}

export interface HoursLabel {
  text: string
  /** Shut, not open yet, or closing within the hour: the badge earns full ink. */
  tight: boolean
}

/**
 * Null means the provider never told us, which the badge answers by not
 * rendering. A day missing from a map we do have is different: Google omits
 * the period entirely for a day a place is shut, so that reads as closed.
 */
export function hoursLabel(
  hours: Hours | null | undefined,
  timezone: string,
  now: Date = new Date(),
): HoursLabel | null {
  if (hours == null) return null

  const day = formatInTimeZone(now, timezone, 'EEE').toLowerCase()
  const today = hours[day]
  const open = today?.[0]
  const close = today?.[1]
  if (open === undefined || close === undefined) return { text: 'Closed today', tight: true }
  if (open === 0 && close === 1440) return { text: 'Open 24 hours', tight: false }

  const minutes =
    Number(formatInTimeZone(now, timezone, 'H')) * 60 +
    Number(formatInTimeZone(now, timezone, 'm'))

  if (minutes < open) return { text: `Opens ${clock(open)}`, tight: true }
  if (minutes >= close) return { text: 'Closed now', tight: true }
  if (close - minutes <= 90) return { text: `Closes in ${close - minutes} min`, tight: true }
  return { text: `Open till ${clock(close)}`, tight: false }
}
