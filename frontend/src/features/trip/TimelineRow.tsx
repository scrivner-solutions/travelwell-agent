import type { ReactNode } from 'react'
import type { CalendarEventSummary, PlanItem } from '@/api/queries'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { commitmentChrome, rowChromeFor, type RowChrome } from '@/lib/timeline'
import { formatTripTime, formatTripWeekday } from '@/lib/time'

/**
 * One thing on a day: a time in the gutter, then a bordered card.
 *
 * The gutter is outside the card because when something happens is a property
 * of the day, not of the thing - which is also why a commitment and a plan item
 * share this shape exactly. They are the same kind of object, and the screen
 * should not need two layouts to say so.
 *
 * Design source: the timeline row in TravelWellPlan.dc.html.
 */
function TimelineRow({
  gutter,
  chrome,
  title,
  sub,
  note,
  badge,
  onSelect,
  selectLabel,
}: {
  gutter: ReactNode
  chrome: RowChrome
  title: string
  sub?: string
  note?: string
  badge?: ReactNode
  /** Tappable when given. A row with nothing behind it must not look tappable. */
  onSelect?: () => void
  selectLabel?: string
}) {
  const body = (
    <>
      <span className={`size-2 flex-none rounded-full ${chrome.dot}`} aria-hidden />
      <span className="min-w-0 flex-1">
        <span className={`block text-body-sm font-semibold ${chrome.name}`}>{title}</span>
        {sub !== undefined && (
          <span className="mt-[3px] block text-label text-muted-soft">{sub}</span>
        )}
        {/* Why this slot and not another. Server-authored, and the only answer
            the row has to "why here?" without being opened. */}
        {note !== undefined && (
          <span className="mt-1 block text-label text-muted-soft text-pretty">{note}</span>
        )}
      </span>
      {badge}
    </>
  )
  const frame = `flex min-w-0 flex-1 items-center gap-[11px] rounded-control border px-3.5 py-[13px] text-left ${chrome.frame}`

  return (
    <li className="flex items-stretch gap-3">
      {/* 64px, not 56: a two-digit hour ("12:00 PM") measures ~60 and wraps
          below that. The canvas gutter is 62. */}
      <div className="w-16 flex-none pt-3.5 text-right text-label font-semibold text-muted-soft">
        {gutter}
      </div>
      {onSelect === undefined ? (
        <div className={frame}>{body}</div>
      ) : (
        <button
          onClick={onSelect}
          aria-label={selectLabel}
          className={`${frame} hover:border-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary`}
        >
          {body}
        </button>
      )}
    </li>
  )
}

/** The gutter's two shapes: a time alone within a day, a weekday over it across days. */
function Gutter({
  at,
  timezone,
  withWeekday,
}: {
  at: string
  timezone: string
  withWeekday: boolean
}) {
  if (!withWeekday) return <>{formatTripTime(at, timezone)}</>
  return (
    <>
      <span className="block">{formatTripWeekday(at, timezone)}</span>
      <span className="mt-1 block font-normal tabular-nums">
        {formatTripTime(at, timezone)}
      </span>
    </>
  )
}

/**
 * A commitment you put in your own calendar. It gets no badge: you placed it,
 * so there is nothing here you cannot already see. The muted fill and the grey
 * dot are the whole statement that the agent did not put it there.
 */
export function CommitmentRow({
  event,
  at,
  timezone,
  withWeekday = false,
}: {
  event: CalendarEventSummary
  at: string
  timezone: string
  withWeekday?: boolean
}) {
  return (
    <TimelineRow
      gutter={<Gutter at={at} timezone={timezone} withWeekday={withWeekday} />}
      chrome={commitmentChrome}
      title={event.title}
      sub={event.location_name ?? undefined}
    />
  )
}

export function PlanItemRow({
  item,
  at,
  timezone,
  withWeekday = false,
  onSelect,
}: {
  item: PlanItem
  /** The timeline's own time, which can differ from the item after a replan. */
  at?: string
  timezone: string
  withWeekday?: boolean
  onSelect?: (itemId: string) => void
}) {
  return (
    <TimelineRow
      gutter={
        <Gutter at={at ?? item.starts_at} timezone={timezone} withWeekday={withWeekday} />
      }
      chrome={rowChromeFor(item.status)}
      title={item.selected_option?.display_name ?? item.title}
      sub={item.selected_option?.display_summary ?? undefined}
      note={item.window?.gap_explanation ?? undefined}
      badge={<StatusBadge item={item} />}
      onSelect={onSelect === undefined ? undefined : () => onSelect(item.id)}
      selectLabel={`${item.title}. Open details`}
    />
  )
}
