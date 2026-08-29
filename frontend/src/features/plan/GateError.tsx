import type { PlanItemGate } from './usePlanItem'

/**
 * What went wrong answering an item. A 409 is not a connection problem and must
 * not be reported as one: it means somebody else moved this item, the client
 * has refreshed, and trying again will now do what you meant.
 */
export function GateError({ gate }: { gate: PlanItemGate }) {
  if (gate.error === null) return null
  return (
    <p className="mt-3 text-caption font-semibold text-state-attention">
      {gate.conflicted
        ? 'This changed on the server. It has been refreshed; try again.'
        : 'Could not save that. Check your connection and retry.'}
    </p>
  )
}
