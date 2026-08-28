import type { Trip } from '@/api/queries'

// The Today and Trip tabs surface the trip the agent is currently working:
// active beats preparing beats upcoming; the server orders /trips by start
// date, so the first match per state is the soonest.
const focusOrder: readonly Trip['state'][] = ['active', 'preparing', 'upcoming', 'confirmed']

export function focusTrip(trips: Trip[]): Trip | undefined {
  for (const state of focusOrder) {
    const match = trips.find((trip) => trip.state === state)
    if (match) return match
  }
  return undefined
}

// Design rule: state reads as a dot and a word, one hue per meaning.
// Blue = the agent is settled/active, periwinkle = it is thinking/preparing.
export const stateInk: Record<string, string> = {
  active: 'text-state-confirmed',
  confirmed: 'text-state-confirmed',
  upcoming: 'text-state-confirmed',
  preparing: 'text-state-suggested',
  detected: 'text-state-suggested',
}

// trip_evidence.kind -> the mono tag box on evidence rows (FLT/HTL/EVT per
// the design canvas). kind is open-ended, so unknown kinds get CAL.
const evidenceTags: Record<string, string> = {
  flight_event: 'FLT',
  hotel_email: 'HTL',
  conference_event: 'EVT',
  calendar_block: 'EVT',
}

export function evidenceTag(kind: string): string {
  return evidenceTags[kind] ?? 'CAL'
}

// source_kind enum -> the short human label on the right of evidence rows.
const sourceLabels: Record<string, string> = {
  google_calendar: 'Calendar',
  apple_calendar: 'Calendar',
  gmail: 'Email',
  manual_import: 'Manual',
}

export function sourceLabel(source: string): string {
  return sourceLabels[source] ?? source
}

// Trip-local calendar days as YYYY-MM-DD, for the day selector chips. Dates
// are date-only strings; no timezone math is needed or wanted here.
export function tripDays(startsOn: string, endsOn: string): string[] {
  const days: string[] = []
  const cursor = new Date(`${startsOn}T00:00:00Z`)
  const end = new Date(`${endsOn}T00:00:00Z`)
  while (cursor <= end && days.length < 60) {
    days.push(cursor.toISOString().slice(0, 10))
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return days
}

// Collapsed evidence-card copy. Voice rule: plain past-tense provenance
// ("Found in your calendar and email"), matching the server's state_line for
// detected trips; never first-person agent copy.
const evidenceSourceNouns: Record<string, string> = {
  google_calendar: 'calendar',
  apple_calendar: 'calendar',
  gmail: 'email',
  manual_import: 'imports',
}

const evidenceKindNouns: Record<string, string> = {
  flight_event: 'flight',
  hotel_email: 'hotel',
  conference_event: 'conference',
  calendar_block: 'calendar block',
}

function joinNaturally(words: string[]): string {
  if (words.length <= 1) return words[0] ?? ''
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`
}

export function evidenceSourceSummary(evidence: { source: string }[]): string {
  const nouns = [
    ...new Set(
      evidence.map(
        (e) => evidenceSourceNouns[e.source] ?? sourceLabel(e.source).toLowerCase(),
      ),
    ),
  ]
  return joinNaturally(nouns)
}

export function evidenceKindSummary(evidence: { kind: string }[]): string {
  const nouns = [
    ...new Set(evidence.map((e) => evidenceKindNouns[e.kind] ?? 'calendar item')),
  ]
  const joined = joinNaturally(nouns)
  return joined.charAt(0).toUpperCase() + joined.slice(1)
}

// Calendar-strip span: pad [first, last] out to full Sunday-to-Saturday weeks
// so the day selector reads like a slice of a real calendar, not a bare list.
export function calendarSpan(first: string, last: string): string[] {
  const start = new Date(`${first}T00:00:00Z`)
  start.setUTCDate(start.getUTCDate() - start.getUTCDay())
  const end = new Date(`${last}T00:00:00Z`)
  end.setUTCDate(end.getUTCDate() + (6 - end.getUTCDay()))
  return tripDays(
    start.toISOString().slice(0, 10),
    end.toISOString().slice(0, 10),
  )
}

// Profile identity subline: "4 trips this year · 18 nights away". Real data
// from /trips, never a canned figure; dismissed detections don't count.
export function travelStats(trips: Trip[]): { tripsThisYear: number; nightsAway: number } {
  const year = new Date().getFullYear()
  const counted = trips.filter(
    (trip) =>
      trip.state !== 'dismissed' &&
      new Date(`${trip.starts_on}T00:00:00Z`).getUTCFullYear() === year,
  )
  const nightsAway = counted.reduce(
    (sum, trip) =>
      sum +
      Math.max(
        0,
        Math.round(
          (Date.parse(`${trip.ends_on}T00:00:00Z`) -
            Date.parse(`${trip.starts_on}T00:00:00Z`)) /
            86_400_000,
        ),
      ),
    0,
  )
  return { tripsThisYear: counted.length, nightsAway }
}
