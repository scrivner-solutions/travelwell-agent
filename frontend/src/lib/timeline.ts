import type { ItemStatus, PlanItem, ReservationStatus } from '@/api/queries'

/**
 * One grammar for everything that sits on a day.
 *
 * A calendar commitment and a plan item are the same kind of object - a thing
 * happening at a time - so they get the same card, and the difference between
 * them is carried by surface rather than by shape: a commitment is filled
 * `--card-muted` with a `--state-existing` dot, which is the whole of how the
 * screen says "the agent did not put this here".
 *
 * These live in lib and not in the row component because two surfaces render
 * rows - the trip screen's day timeline and the detail screen's window list -
 * and the point of the slice is that they cannot disagree.
 */
export type RowChrome = {
  /** Border and fill. Border *style* rides along: dashed means not real yet. */
  frame: string
  dot: string
  name: string
}

/**
 * A commitment you put in your own calendar. No badge accompanies this: the
 * user placed it themselves, so there is nothing here they cannot already see.
 * If the fill and the dot turn out not to carry that on their own, `Existing`
 * comes back as a fifth badge - a browser question, not a source one.
 */
export const commitmentChrome: RowChrome = {
  frame: 'border-border-soft bg-card-muted',
  dot: 'bg-state-existing',
  name: 'text-ink',
}

/**
 * A plan item's frame, keyed on the generated enum so a new contract value
 * fails the typecheck rather than rendering an unstyled row.
 *
 * All 1px: Blink floors fractional widths, so the 1.5px these used to declare
 * painted exactly like a card's border. `--border-row-suggested` is the one
 * row-scale token left, darker rather than thicker to carry the same
 * distinction. Two of these are load-bearing beyond decoration - dashed
 * says a suggestion is not real yet, and full-ink says this one needs you,
 * which is the only marker `awaiting_user` has now that its badge is gone.
 */
const chromeByStatus: Record<ItemStatus, RowChrome> = {
  suggested: {
    frame: 'border-dashed border-border-row-suggested bg-card',
    dot: 'bg-state-suggested',
    name: 'text-ink',
  },
  awaiting_user: { frame: 'border-ink bg-card', dot: 'bg-ink', name: 'text-ink' },
  planned: {
    frame: 'border-border-confirmed bg-card',
    dot: 'bg-state-confirmed',
    name: 'text-ink',
  },
  confirmed: {
    frame: 'border-border-confirmed bg-card',
    dot: 'bg-state-confirmed',
    name: 'text-ink',
  },
  working: {
    frame: 'border-border-confirmed bg-card',
    dot: 'bg-state-working',
    name: 'text-ink',
  },
  changed: {
    frame: 'border-border-row-suggested bg-card',
    dot: 'bg-state-changed',
    name: 'text-ink',
  },
  // Spent. Only the retrospective renders these, and there they are history.
  skipped: {
    frame: 'border-border bg-card-muted',
    dot: 'bg-border-faint',
    name: 'text-muted-soft',
  },
  removed: {
    frame: 'border-border bg-card-muted',
    dot: 'bg-border-faint',
    name: 'text-muted-soft',
  },
}

export function rowChromeFor(status: ItemStatus): RowChrome {
  return chromeByStatus[status]
}

export type ItemBadge = { label: string; className: string }

/**
 * Four badges and silence everywhere else.
 *
 * A badge earns its place by saying something true that the user cannot act on
 * and would not otherwise know - which is why the three open statuses carry
 * none. An open gate is a place, not a label: it renders as a row you can tap
 * and a button you can press, and adding the word "Suggested" beside a dashed
 * card that is plainly a suggestion only repeats the card.
 *
 * The keys stay complete rather than being dropped, so a new contract value
 * still fails the typecheck instead of silently rendering nothing.
 */
const badgeByStatus: Record<ItemStatus, ItemBadge | null> = {
  suggested: null,
  awaiting_user: null,
  planned: null,
  confirmed: { label: 'Booked', className: 'text-state-confirmed' },
  working: { label: 'Booking…', className: 'text-state-working' },
  changed: { label: 'Changed', className: 'text-state-changed' },
  // Not on any live surface - the timeline deletes both. `skipped` reaches the
  // retrospective, where "what happened" is the question and it is an answer.
  skipped: { label: 'Skipped', className: 'text-state-neutral' },
  removed: { label: 'Removed', className: 'text-state-neutral' },
}

/** Chip classes: a state colour and its paired soft ground. */
export type ReservationNote = { label: string; className: string }

const NEUTRAL_CHIP = 'bg-state-neutral-soft text-muted'

/**
 * What the sheet says about this item's booking.
 *
 * Lives here beside `itemBadge` on purpose: both answer "what has happened to
 * this reservation", and while they were apart a row could badge `Booked` over
 * a sheet still asking for a table.
 */
const noteByStatus: Record<ReservationStatus, ReservationNote | null> = {
  pending: { label: 'Waiting to book', className: NEUTRAL_CHIP },
  holding: {
    label: 'Holding a table',
    className: 'bg-state-working-soft text-state-working',
  },
  confirmed: {
    label: 'Booked',
    className: 'bg-state-confirmed-soft text-state-confirmed',
  },
  // The one state the user may have to act on, so the sheet gives it a full
  // sentence rather than a chip. Chipping it too would say it twice.
  failed: null,
  canceled: { label: 'Reservation canceled', className: NEUTRAL_CHIP },
}

export function reservationNote(item: PlanItem): ReservationNote | null {
  const res = item.reservation
  // `needs_reservation` is the intent, the reservation is the fact. Once one
  // exists it answers for the item - otherwise the sheet keeps asking for a
  // table it already holds, which is what it did for every booked window.
  // == null, not === undefined: the server omits empty fields today, but the
  // contract types them nullable, and this holds either way.
  if (res == null) {
    return item.needs_reservation
      ? { label: 'Needs a reservation', className: NEUTRAL_CHIP }
      : null
  }
  const note = noteByStatus[res.status]
  if (note === null) return null
  // The code is the whole point of a confirmation, and the database guarantees
  // it is there iff confirmed - but the contract types it optional, so ask.
  return res.status === 'confirmed' && res.confirmation_code != null
    ? { ...note, label: `Booked · confirmation ${res.confirmation_code}` }
    : note
}

export function itemBadge(item: PlanItem): ItemBadge | null {
  // The one thing on this list the agent did and got wrong, so it outranks the
  // status: an item can be left `planned` or `removed` by a booking that failed.
  if (item.reservation?.status === 'failed') {
    return { label: "Couldn't book", className: 'text-state-failed' }
  }
  // "Booked" is a claim about a reservation. An item that never wanted one is
  // just settled, and settled is silence.
  if (item.status === 'confirmed' && !item.needs_reservation) return null
  return badgeByStatus[item.status]
}
