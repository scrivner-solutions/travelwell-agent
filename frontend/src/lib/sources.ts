import type { ConnectedSource } from '@/api/queries'
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

export const SOURCE_STATE: Record<ConnectedSource['status'], { text: string; ink: string }> =
  {
    connected: { text: 'Connected', ink: 'text-primary-deep' },
    error: { text: 'Needs attention', ink: 'text-state-attention' },
    revoked: { text: 'Reconnect', ink: 'text-agent' },
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
