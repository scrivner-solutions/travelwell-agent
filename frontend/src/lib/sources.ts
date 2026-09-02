import { ApiError } from '@/api/client'
import type { ConnectedSource, SyncResult } from '@/api/queries'
import { formatAgo } from '@/lib/time'
import { joinNaturally, sourceLabel } from '@/lib/trips'

/** source_kind -> how a connected source presents itself. Shared by the
 * profile's source list and the trip facts card's trust strip. */
export const SOURCE_META: Record<string, { tag: string; name: string; sub?: string }> = {
  google_calendar: { tag: 'CAL', name: 'Google Calendar' },
  gmail: { tag: 'MAI', name: 'Email receipts', sub: 'Flights and hotels only' },
  apple_calendar: { tag: 'CAL', name: 'Apple Calendar' },
  manual_import: { tag: 'IMP', name: 'Manual import' },
}

// States, not invitations: the action a row offers is a button now, so
// `revoked` reads as the condition it is rather than the fix for it.
export const SOURCE_STATE: Record<ConnectedSource['status'], { text: string; ink: string }> =
  {
    connected: { text: 'Connected', ink: 'text-primary-deep' },
    error: { text: 'Needs attention', ink: 'text-state-attention' },
    revoked: { text: 'Disconnected', ink: 'text-muted' },
  }

export type SourceAction = 'connect' | 'reconnect' | 'disconnect'

export const SOURCE_ACTION_LABEL: Record<SourceAction, string> = {
  connect: 'Connect',
  reconnect: 'Reconnect',
  disconnect: 'Disconnect',
}

/**
 * What a row offers, or null for nothing. A kind this build cannot put through
 * an OAuth handshake gets no button rather than one that 404s: /me/sources
 * returns rows for kinds that are no longer (or not yet) connectable, and the
 * backend refuses connect, callback and disconnect alike for them.
 */
export function sourceAction(
  status: ConnectedSource['status'] | null,
  connectable: boolean,
): SourceAction | null {
  if (!connectable) return null
  if (status === null) return 'connect'
  return status === 'connected' ? 'disconnect' : 'reconnect'
}

/** The callback redirects to /profile?connect_error=<code> rather than
 * rendering anything itself, so this is the only place those codes are read. */
export const CONNECT_ERROR_COPY: Record<string, string> = {
  scope_declined:
    'Calendar access was not granted. Try again and leave the calendar permission checked.',
  no_refresh_token:
    'Google did not return a durable grant, so the connection would have expired within the hour. Nothing was saved.',
  oauth_failed: 'Google did not complete the connection. Try again.',
  token_store_unconfigured:
    'This environment cannot store the connection yet. Nothing was saved.',
}

export function sourceName(kind: string): string {
  return SOURCE_META[kind]?.name ?? kind
}

/**
 * The trust strip under the facts card: which sources fed it, and how fresh
 * they are. Null when nothing is connected — the facts on the card are still
 * true, and "nothing is connected" is the profile's message, not this card's.
 */
export function connectedSourceLine(sources: ConnectedSource[]): string | null {
  const live = sources.filter((source) => source.status === 'connected')
  const [only] = live
  if (only === undefined) return null
  // One source names itself in full, as the canvas does. Several collapse to
  // nouns, because "Google Calendar and Email receipts" is not a sentence.
  const names =
    live.length === 1
      ? sourceName(only.kind)
      : joinNaturally([
          ...new Set(live.map((source) => sourceLabel(source.kind).toLowerCase())),
        ]).replace(/^./, (c) => c.toUpperCase())
  // The freshest sync of the set: the strip claims the card is current, and
  // the newest source is the only one that can support that claim.
  const synced = live
    .map((source) => source.last_synced_at)
    .filter((iso): iso is string => iso !== undefined)
    .sort()
    .at(-1)
  return synced === undefined
    ? `${names} connected`
    : `${names} connected · synced ${formatAgo(synced)}`
}

/**
 * Whether the profile's "Done" may use history.back(). After the OAuth callback
 * the preceding entries belong to Google, so back lands on the consent screen.
 * `history.length` cannot tell the two arrivals apart: it counts every origin.
 */
export function canGoBackInApp(arrivedFromOAuth: boolean, historyLength: number): boolean {
  return !arrivedFromOAuth && historyLength > 1
}

/**
 * What a finished sync says. Counts, not a checkmark: the endpoint separates
 * "nothing changed" from "nothing came back", and only one of those is fine.
 */
export function syncOutcomeMessage(result: SyncResult): string {
  const changes = [
    result.created > 0 ? `${result.created} added` : null,
    result.updated > 0 ? `${result.updated} updated` : null,
  ].filter((part): part is string => part !== null)
  return changes.length === 0 ? 'Already up to date' : joinNaturally(changes)
}

/**
 * Why a sync failed, in the server's own words where it has them. Swallowing
 * this is the one thing the button must not do: the 409s are the actionable
 * cases, and they name the fix ("Connect it again before syncing.").
 */
export function syncFailureMessage(error: unknown): string {
  const problem = error instanceof ApiError ? error.problem : undefined
  if (problem === undefined) return 'Sync failed. Check your connection and retry.'
  return problem.detail == null ? problem.title : `${problem.title}. ${problem.detail}`
}
