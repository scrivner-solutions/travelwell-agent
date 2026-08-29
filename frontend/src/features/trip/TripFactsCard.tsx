import { Check } from 'lucide-react'
import type { ConnectedSource } from '@/api/queries'
import { connectedSourceLine } from '@/lib/sources'
import type { FactRow } from '@/lib/trips'

/** A fact row on its own, for the detection cards, which show the same rows
 * outside the card frame. */
export function FactRowView({
  row,
  className = '',
}: {
  row: FactRow
  className?: string
}) {
  return (
    <li className={`flex items-center gap-3 ${className}`}>
      <span
        className={`grid size-8 flex-none place-items-center rounded-tile font-mono text-[11px] font-semibold ${
          row.muted
            ? 'border border-dashed border-border bg-card text-muted-soft'
            : 'bg-state-neutral-soft text-muted'
        }`}
      >
        {row.tag}
      </span>
      <span className="min-w-0 flex-1">
        <span
          className={`block text-body-sm font-semibold ${row.muted ? 'text-muted-soft' : 'text-ink'}`}
        >
          {row.title}
        </span>
        {row.sub !== undefined && (
          <span className="mt-0.5 block text-caption text-muted-soft text-pretty">
            {row.sub}
          </span>
        )}
      </span>
      {row.source !== undefined && (
        <span className="flex-none text-label text-muted-soft">{row.source}</span>
      )}
    </li>
  )
}

/**
 * What is known about a trip, always open. It was collapsed behind "Found in
 * your calendar and email", which hid the only answer to "does it have this
 * right?" — the question a user actually opens a trip with.
 *
 * Shared with the trip detail screen, which passes a label and may pass muted
 * rows; the trip screen passes neither.
 */
export function TripFactsCard({
  rows,
  label,
  sources,
}: {
  rows: FactRow[]
  label?: string
  sources?: ConnectedSource[]
}) {
  const strip = sources ? connectedSourceLine(sources) : null
  if (rows.length === 0 && strip === null) return null

  return (
    <div className="overflow-hidden rounded-section border border-border bg-card">
      {label !== undefined && (
        <p className="px-4 pt-4 text-section font-semibold uppercase text-muted-soft">
          {label}
        </p>
      )}
      <ul>
        {rows.map((row, i) => (
          <FactRowView
            key={i}
            row={row}
            className="border-b border-border-soft px-4 py-3.5"
          />
        ))}
      </ul>
      {/* Inset by fill, not by shadow: the strip reports on the card above it
          rather than being another fact in the list. */}
      {strip !== null && (
        <p className="flex items-center gap-2 bg-card-muted px-4 py-3 text-caption text-muted">
          <Check className="size-4 flex-none text-primary" strokeWidth={2.6} aria-hidden />
          {strip}
        </p>
      )}
    </div>
  )
}
