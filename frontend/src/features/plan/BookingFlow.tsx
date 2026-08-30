import { ExternalLink, Minus, Plus } from 'lucide-react'
import type { PendingAction, PlanItem } from '@/api/queries'
import { formatTripDay, formatTripTime } from '@/lib/time'
import type { Booking } from './useBooking'

/**
 * Booking a table, from the offer to the outcome.
 *
 * Four states, and the order matters more than the styling: nothing is sent
 * until the confirm step, the confirm step shows what the *server* assembled
 * rather than what this screen guessed, and the running state exists because a
 * real booking is not finished when the request returns.
 *
 * Progress copy is derived here from the action and its reservation. The server
 * writes the same lines for the SSE stream (`_trace` in app/api/actions.py) and
 * the two should read alike; this screen polls, so it needs its own.
 */
/**
 * `summary` is a free-form object in the contract, so what comes out of it is
 * `unknown` and has to be checked rather than asserted. That is the right
 * trade: the server decides which rows the confirm sheet shows, and this screen
 * renders only the ones it recognises instead of trusting a shape.
 */
function text(bag: Record<string, unknown> | null | undefined, key: string) {
  const value = bag?.[key]
  return typeof value === 'string' ? value : undefined
}

function count(bag: Record<string, unknown> | null | undefined, key: string) {
  const value = bag?.[key]
  return typeof value === 'number' ? value : undefined
}

function progressLine(action: PendingAction | undefined, where: string): string {
  const status = action?.reservation?.status
  if (status === 'pending') return `Asking ${where} for the table…`
  if (status === 'holding') return `${where} is holding the table…`
  return 'Sending the request…'
}

function PartySize({
  value,
  onChange,
  disabled,
}: {
  value: number
  onChange: (next: number) => void
  disabled: boolean
}) {
  const step = (delta: number) => onChange(Math.min(20, Math.max(1, value + delta)))
  return (
    <div className="flex items-center gap-3">
      <span className="text-body-sm text-muted">Party of</span>
      <div className="flex items-center gap-1 rounded-chip border border-border bg-card">
        <button
          onClick={() => step(-1)}
          disabled={disabled || value <= 1}
          aria-label="One fewer"
          className="grid size-9 place-items-center rounded-chip text-muted hover:bg-state-neutral-soft disabled:opacity-40"
        >
          <Minus className="size-4" aria-hidden />
        </button>
        <span className="w-6 text-center text-body font-semibold tabular-nums">
          {value}
        </span>
        <button
          onClick={() => step(1)}
          disabled={disabled || value >= 20}
          aria-label="One more"
          className="grid size-9 place-items-center rounded-chip text-muted hover:bg-state-neutral-soft disabled:opacity-40"
        >
          <Plus className="size-4" aria-hidden />
        </button>
      </div>
    </div>
  )
}

export function BookingFlow({
  booking,
  item,
  timezone,
}: {
  booking: Booking
  item: PlanItem
  timezone: string
}) {
  const { action } = booking
  const where =
    text(action?.summary, 'where') ?? item.selected_option?.display_name ?? item.title
  const failure = action?.failure

  if (booking.settled && action?.status === 'failed') {
    return (
      <div className="mt-4 rounded-panel border border-border bg-card p-4">
        <p className="text-body-sm font-semibold text-state-attention text-pretty">
          {failure?.message ?? 'This booking did not go through.'}
        </p>
        {/* The honest offer: we could not, here is where you can. */}
        <div className="mt-3 flex flex-wrap gap-2">
          {failure?.external_url != null && (
            <a
              href={failure.external_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded-chip border border-border bg-card px-3.5 py-2 text-body-sm font-semibold text-primary hover:border-primary"
            >
              Book directly
              <ExternalLink className="size-3.5 flex-none" aria-hidden />
            </a>
          )}
          <button
            onClick={booking.reset}
            className="rounded-chip border border-border bg-card px-3.5 py-2 text-body-sm font-semibold text-muted hover:bg-state-neutral-soft"
          >
            Try again
          </button>
        </div>
      </div>
    )
  }

  if (booking.settled && action?.status === 'completed') {
    const reservation = action.reservation
    return (
      <div className="mt-4 rounded-panel border border-border bg-card p-4">
        <p className="text-body-sm font-semibold text-state-confirmed">
          {reservation?.confirmation_code != null
            ? `Booked · confirmation ${reservation.confirmation_code}`
            : 'Sent. Book it directly to finish.'}
        </p>
        {/* An external-link booking completes without a table being held, and
            saying "Booked" there would be a claim nobody made. */}
        {reservation?.confirmation_code == null && reservation?.external_url != null && (
          <a
            href={reservation.external_url}
            target="_blank"
            rel="noreferrer"
            className="mt-3 flex w-fit items-center gap-1.5 rounded-chip border border-border bg-card px-3.5 py-2 text-body-sm font-semibold text-primary hover:border-primary"
          >
            Open the booking page
            <ExternalLink className="size-3.5 flex-none" aria-hidden />
          </a>
        )}
      </div>
    )
  }

  if (booking.running) {
    return (
      <div className="mt-4 rounded-panel border border-border-confirmed bg-card p-4">
        <p className="text-body-sm font-medium text-muted text-pretty">
          {progressLine(action, where)}
        </p>
      </div>
    )
  }

  if (booking.awaitingConfirm && action != null) {
    const when = text(action.summary, 'when')
    return (
      <div className="mt-4 rounded-panel border border-agent-soft bg-card p-4">
        <p className="text-label font-semibold uppercase tracking-wide text-agent">
          Confirm this booking
        </p>
        <p className="mt-2 text-body font-semibold">{where}</p>
        <p className="mt-1 text-body-sm text-muted">
          {when != null && (
            <>
              {formatTripDay(when, timezone)} · {formatTripTime(when, timezone)} ·{' '}
            </>
          )}
          Party of {count(action.summary, 'party_size') ?? booking.partySize}
        </p>
        <div className="mt-4 flex gap-2.5">
          <button
            onClick={() => booking.confirm.mutate(action)}
            disabled={booking.pending}
            className="h-12 flex-1 rounded-chip bg-primary text-body-sm font-semibold text-white hover:bg-primary-deep disabled:opacity-60"
          >
            {booking.confirm.isPending ? 'Confirming…' : 'Confirm'}
          </button>
          <button
            onClick={booking.reset}
            disabled={booking.pending}
            className="h-12 flex-1 rounded-chip border border-border bg-card text-body-sm font-semibold text-muted hover:bg-state-neutral-soft disabled:opacity-60"
          >
            Not now
          </button>
        </div>
        <p className="mt-3 text-caption text-muted-soft text-pretty">
          Nothing is booked until you confirm.
        </p>
      </div>
    )
  }

  return (
    <div className="mt-4 flex flex-col gap-3">
      <PartySize
        value={booking.partySize}
        onChange={booking.setPartySize}
        disabled={booking.pending}
      />
      <button
        onClick={() => booking.propose.mutate()}
        disabled={booking.pending}
        className="h-12 w-full rounded-chip bg-primary text-body-sm font-semibold text-white hover:bg-primary-deep disabled:opacity-60"
      >
        {booking.propose.isPending ? 'Preparing…' : 'Book a table'}
      </button>
      {booking.error != null && (
        <p className="text-caption font-semibold text-state-attention">
          {booking.conflicted
            ? 'This changed on the server. Refresh and try again.'
            : 'Could not start that booking. Check your connection and retry.'}
        </p>
      )}
    </div>
  )
}
