import { LocateFixed, Minus, Plus } from 'lucide-react'

export interface MapControlsProps {
  onZoomIn: () => void
  onZoomOut: () => void
  onRecentre: () => void
  canZoomIn: boolean
  canZoomOut: boolean
}

const control =
  'grid size-10 place-items-center bg-card text-ink hover:bg-surface disabled:text-muted-faint focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary'

/** Zoom and recentre, for anyone without a wheel or a second finger. Stacked
 *  the way every map app stacks them, so nobody has to learn ours. */
export function MapControls({ onZoomIn, onZoomOut, onRecentre, canZoomIn, canZoomOut }: MapControlsProps) {
  return (
    <div className="flex flex-col overflow-hidden rounded-control border border-border shadow-[var(--shadow-chip)]">
      <button type="button" aria-label="Zoom in" onClick={onZoomIn} disabled={!canZoomIn} className={control}>
        <Plus className="size-5" aria-hidden />
      </button>
      <button
        type="button"
        aria-label="Zoom out"
        onClick={onZoomOut}
        disabled={!canZoomOut}
        className={`${control} border-t border-border`}
      >
        <Minus className="size-5" aria-hidden />
      </button>
      <button
        type="button"
        aria-label="Recentre"
        onClick={onRecentre}
        className={`${control} border-t border-border`}
      >
        <LocateFixed className="size-5" aria-hidden />
      </button>
    </div>
  )
}
