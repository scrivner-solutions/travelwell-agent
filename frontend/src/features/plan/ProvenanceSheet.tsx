import { useQuery } from '@tanstack/react-query'
import { Sheet } from '@/components/ui/Sheet'
import { provenanceQueryOptions } from '@/api/queries'

/**
 * "How I got here": the opening the agent was filling, what it matched, and
 * the candidates it ruled out with the reason each lost.
 *
 * Everything here is read-only, which is what makes the rejected candidates
 * safe to show: selecting one would have to clear the very reason this panel
 * exists to display, so the API refuses it (422).
 */
export function ProvenanceSheet({
  itemId,
  onClose,
}: {
  itemId: string | undefined
  onClose: () => void
}) {
  const provenance = useQuery({
    ...provenanceQueryOptions(itemId ?? ''),
    enabled: itemId !== undefined,
  })
  const window = provenance.data?.window
  const considered = provenance.data?.considered ?? []
  const ruledOut = considered.filter((o) => o.state === 'rejected')
  const matched = considered.find((o) => o.state === 'selected')?.matched_preferences

  return (
    <Sheet open={itemId !== undefined} onClose={onClose} title="Why this">
      {provenance.isPending && itemId !== undefined && (
        <p className="text-body-sm text-muted">Loading…</p>
      )}

      {window != null && (
        <section>
          <h3 className="text-caption font-semibold uppercase tracking-wide text-muted">
            The opening
          </h3>
          <p className="mt-1 text-body font-semibold">{window.label}</p>
          {window.gap_explanation != null && (
            <p className="mt-1 text-body-sm text-muted text-pretty">
              {window.gap_explanation}
            </p>
          )}
          <ul className="mt-3 flex flex-col gap-2">
            {window.bounds.map((bound, i) => (
              <li
                key={i}
                className="flex items-start gap-3 rounded-panel border border-border px-3 py-2"
              >
                <span className="flex-none font-mono text-label font-semibold text-muted">
                  {bound.tag}
                </span>
                <span className="min-w-0">
                  <span className="block text-body-sm font-semibold">{bound.title}</span>
                  {bound.detail !== undefined && (
                    <span className="block text-caption text-muted">{bound.detail}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {matched !== undefined && matched.length > 0 && (
        <section className="mt-5">
          <h3 className="text-caption font-semibold uppercase tracking-wide text-muted">
            Matched from your profile
          </h3>
          <ul className="mt-2 flex flex-wrap gap-2">
            {matched.map((preference) => (
              <li
                key={preference}
                className="rounded-control bg-state-suggested-soft px-3 py-1.5 text-body-sm font-medium text-state-suggested"
              >
                {preference}
              </li>
            ))}
          </ul>
        </section>
      )}

      {ruledOut.length > 0 && (
        <section className="mt-5">
          <h3 className="text-caption font-semibold uppercase tracking-wide text-muted">
            Also considered
          </h3>
          <ul className="mt-2 flex flex-col gap-2">
            {ruledOut.map((option) => (
              <li
                key={option.id}
                className="rounded-panel border border-border px-3 py-2.5"
              >
                <p className="text-body-sm font-semibold text-muted">
                  {option.display_name}
                </p>
                {option.rejection_reason !== undefined && (
                  <p className="mt-0.5 text-caption text-muted text-pretty">
                    {option.rejection_reason}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </Sheet>
  )
}
