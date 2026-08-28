import type { components } from '@/api/schema'

type ItemStatus = components['schemas']['ItemStatus']

/**
 * The only source of status pills. Driven by the generated item_status enum:
 * when the contract gains a value, this Record fails the typecheck until the
 * design decides how to render it. Labels match the canvas badges.
 */
const config: Record<ItemStatus, { label: string; className: string }> = {
  suggested: {
    label: 'Suggested',
    className: 'bg-state-suggested-soft text-state-suggested',
  },
  awaiting_user: {
    label: 'Needs you',
    className: 'bg-state-attention-soft text-state-attention',
  },
  planned: {
    label: 'In plan',
    className: 'bg-state-working-soft text-state-working',
  },
  confirmed: {
    label: 'Confirmed',
    className: 'bg-state-confirmed-soft text-state-confirmed',
  },
  working: {
    label: 'Working',
    className: 'bg-state-working-soft text-state-working',
  },
  changed: {
    label: 'Changed',
    className: 'bg-state-changed-soft text-state-changed',
  },
  skipped: {
    label: 'Skipped',
    className: 'bg-state-neutral-soft text-state-neutral',
  },
  removed: {
    label: 'Removed',
    className: 'bg-state-neutral-soft text-state-neutral',
  },
}

/** The app's one pill shape. Never shrinks or wraps: a truncated status lies. */
export function Pill({ label, className }: { label: string; className: string }) {
  return (
    <span
      className={`inline-flex flex-none items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-label font-semibold uppercase tracking-wide ${className}`}
    >
      {label}
    </span>
  )
}

export function StatusBadge({ status }: { status: ItemStatus }) {
  return <Pill {...config[status]} />
}
