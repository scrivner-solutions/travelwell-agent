import type { Preferences, Trip } from '@/api/queries'
import type { components } from '@/api/schema'

type PlanProgress = components['schemas']['PlanProgress']
type NeedsYouKind = components['schemas']['NeedsYouKind']

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

// A trip that has ended gets a section rather than a badge, so tense never has
// to be read off a row. Set by the agent runtime, so it stays empty until then.
const pastStates: readonly Trip['state'][] = ['completed', 'archived']

export function isPast(trip: Trip): boolean {
  return pastStates.includes(trip.state)
}

export type Badge = { label: string; className: string }

// Two visual classes, and the difference survives greyscale: a working badge
// ends in an ellipsis and will change on its own, a settled badge is a fact.
// `none` renders nothing at all, because for a trip months out "no plan yet"
// is expected rather than news. Keyed by the generated enum, so a new contract
// value fails the typecheck until the design decides how to render it.
const progressBadges: Record<PlanProgress, Badge | null> = {
  none: null,
  preparing: {
    label: 'Preparing…',
    className: 'bg-state-working-soft text-state-working',
  },
  booking: {
    label: 'Booking…',
    className: 'bg-state-working-soft text-state-working',
  },
  planned: {
    label: 'Planned',
    className: 'bg-state-confirmed-soft text-state-confirmed',
  },
}

// Being on the trip outranks how far along its plan is: it is the one thing on
// the row that no date can tell you, so it takes the slot and the solid fill.
const nowBadge: Badge = { label: 'Now', className: 'bg-state-confirmed text-white' }

export function tripBadge(trip: Trip): Badge | null {
  // A finished trip's plan progress is history, and its section already says
  // where it sits, so nothing is left that the row needs to declare.
  if (isPast(trip)) return null
  if (trip.state === 'active') return nowBadge
  return progressBadges[trip.plan_progress]
}

// Naming the gate beats counting it: when scanning a list, what kind of work
// decides whether you open a trip. Mixed kinds fall back to the count, because
// no single phrase covers two gates honestly.
export function needsYouLabel(count: number, kind?: NeedsYouKind): string | null {
  if (count < 1) return null
  if (kind === 'plan') return 'Plan ready'
  if (kind === 'approval') return `${count} to approve`
  return `${count} ${count === 1 ? 'item needs' : 'items need'} you`
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

// The one-word lifecycle state, for the right-hand slot of a trip row where a
// full state_line ("Confirmed - will start preparing closer to the trip") will
// not fit. Keyed on the generated enum so a new state fails the typecheck.
// `upcoming` is dead in practice - see the trip enum audit - but stays keyed.
const stateWords: Record<Trip['state'], string> = {
  detected: 'Found for you',
  confirmed: 'Confirmed',
  upcoming: 'Upcoming',
  preparing: 'Preparing',
  active: 'Active',
  completed: 'Complete',
  archived: 'Archived',
  dismissed: 'Dismissed',
}

export function tripStateWord(trip: Trip): string {
  return stateWords[trip.state]
}

// The dot beside a trip's name, in the header switcher and on every sheet row.
// One hue per meaning, same as the badges: blue = the agent is on it now,
// periwinkle = it is thinking, warm grey = done and filed.
export function tripDot(trip: Trip): string {
  if (trip.state === 'active') return 'bg-state-confirmed'
  if (trip.state === 'preparing' || trip.state === 'detected')
    return 'bg-state-suggested'
  if (isPast(trip)) return 'bg-state-archived'
  return 'bg-muted-faint'
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

/**
 * One line of what is known about a trip. `muted` is a fact the agent expects
 * and does not have yet — a dashed tile and grey ink, so an absence reads as
 * an absence rather than as a row that failed to load. Nothing produces muted
 * rows today: the trips contract carries only evidence that exists, and the
 * missing-fact list arrives with the trip detail screen.
 */
export type FactRow = {
  tag: string
  title: string
  sub?: string
  source?: string
  muted?: boolean
}

export function evidenceRows(evidence: NonNullable<Trip['evidence']>): FactRow[] {
  return evidence.map((row) => ({
    tag: evidenceTag(row.kind),
    title: row.summary,
    sub: row.detail ?? undefined,
    source: sourceLabel(row.source),
  }))
}

/**
 * Your standing instructions as one more fact row ("Vegetarian · swim and
 * run"). It sits with the flights and hotels because it is the other half of
 * what a plan is built from, and the only half you can change - which is why
 * the source reads "Profile" rather than "Calendar".
 */
export function preferenceRow(prefs: Preferences | undefined): FactRow | null {
  if (prefs === undefined) return null
  const parts = [
    prefs.dietary.join(', '),
    joinNaturally(prefs.activities),
  ].filter((part) => part !== '')
  if (parts.length === 0) return null
  const text = parts.join(' · ')
  return {
    tag: 'PRF',
    title: text.charAt(0).toUpperCase() + text.slice(1),
    sub: 'From your profile',
    source: 'Profile',
  }
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

export function joinNaturally(words: string[]): string {
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

/**
 * Which day a trip opens on, in precedence order: today when the trip is
 * running, nothing while the timeline is still loading (a red-eye can add a day
 * outside the range, so we cannot yet know today is not a chip), then the first
 * day with something on it.
 *
 * That last rung was `days[0]`, which opens most future trips on a blank
 * timeline: an arrival day is empty on purpose - you land and check in - so the
 * trip's first day and its first day worth showing are rarely the same.
 */
export function openingDay(opts: {
  days: string[]
  todayIso: string
  dayHasEntries: (day: string) => boolean
  timelinePending: boolean
}): string | undefined {
  if (opts.days.includes(opts.todayIso)) return opts.todayIso
  if (opts.timelinePending) return undefined
  // Reached only when no day has entries, where `days` is just the trip range.
  return opts.days.find(opts.dayHasEntries) ?? opts.days[0]
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
