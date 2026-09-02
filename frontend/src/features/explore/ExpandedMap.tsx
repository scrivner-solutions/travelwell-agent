import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { X } from 'lucide-react'
import type { Basemap, ExploreAnchor, ExplorePlace, ExploreRoute } from '@/api/queries'
import { PlaceCard } from './PlaceCard'
import { MapCanvas } from './MapCanvas'
import { spurTarget } from './spur'
import { MapControls } from './MapControls'
import { RouteStrip, SpurPill } from './RouteStrip'
import { visibleRect, type Rect } from './areas'
import { fit, pan, zoomAt, zoomBoundsFor, type Viewport } from './projection'
import { useFrameSize } from './useFrameSize'
import { useMapGestures } from './useMapGestures'

/* One button press or key. 1.5 is a step you can see without losing where you
 * were; 48 px is a thumb's width of ground. */
const ZOOM_STEP = 1.5
const PAN_STEP_PX = 48

/* How long the view must hold still before it counts as somewhere the user
 * meant to look, and finer ground may be asked for. Shorter and a pan across
 * town asks for every cell it crosses. */
const SETTLE_MS = 300

const KEY_PAN: Record<string, [number, number]> = {
  ArrowLeft: [PAN_STEP_PX, 0],
  ArrowRight: [-PAN_STEP_PX, 0],
  ArrowUp: [0, PAN_STEP_PX],
  ArrowDown: [0, -PAN_STEP_PX],
}

export interface ExpandedMapProps {
  anchor: ExploreAnchor
  places: ExplorePlace[]
  route: ExploreRoute
  basemap?: Basemap
  /** Areas drawn over the base for the view that settled, coarsest first. */
  detail?: Basemap[]
  radiusM: number
  timezone: string
  selectedId: string | null
  onSelect: (id: string | null) => void
  onClose: () => void
  /** Called once the view has held still: what is on screen, in metres from
   *  the anchor. Whoever holds the queries decides whether to fetch for it. */
  onView?: (rect: Rect) => void
  /** The category chips, floated over the map exactly as on the band. */
  children?: ReactNode
  toolbar?: ReactNode
}

/** The map on the whole screen, where looking around is allowed.

 *  A native modal <dialog>, like the sheets: the platform supplies the focus
 *  trap, Escape and the inert page behind. Gestures are gated behind this
 *  mode on purpose. A map that drags inside a scrolling page steals the
 *  scroll, and every embedded map, Google's included, solves that by making
 *  the user enter it first. */
export function ExpandedMap({
  anchor,
  places,
  route,
  basemap,
  detail,
  radiusM,
  timezone,
  selectedId,
  onSelect,
  onClose,
  onView,
  children,
  toolbar,
}: ExpandedMapProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const frameRef = useRef<HTMLDivElement>(null)
  const size = useFrameSize(frameRef, { w: 360, h: 640 })

  const fitted = useMemo(() => fit(anchor, places, route, radiusM), [anchor, places, route, radiusM])
  const bounds = useMemo(() => zoomBoundsFor(fitted), [fitted])
  const [viewport, setViewport] = useState<Viewport>(fitted)

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  const gestures = useMapGestures({ size, bounds, onChange: setViewport })

  useEffect(() => {
    if (onView === undefined) return
    const timer = setTimeout(() => onView(visibleRect(viewport, size)), SETTLE_MS)
    return () => clearTimeout(timer)
  }, [viewport, size, onView])

  const centre = { x: size.w / 2, y: size.h / 2 }
  const zoom = (factor: number) =>
    setViewport((vp) => zoomAt(vp, factor, centre, size, bounds))
  const canZoomIn = viewport.radiusM > bounds.minRadiusM
  const canZoomOut = viewport.radiusM < bounds.maxRadiusM

  const onKeyDown = (event: KeyboardEvent<HTMLDialogElement>) => {
    const step = KEY_PAN[event.key]
    if (step !== undefined) {
      event.preventDefault()
      setViewport((vp) => pan(vp, step[0], step[1], size))
    } else if (event.key === '+' || event.key === '=') {
      event.preventDefault()
      zoom(ZOOM_STEP)
    } else if (event.key === '-' || event.key === '_') {
      event.preventDefault()
      zoom(1 / ZOOM_STEP)
    }
  }

  const selected = places.find((place) => place.id === selectedId) ?? null
  const spur = spurTarget(places, route, selectedId)

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      onCancel={onClose}
      onKeyDown={onKeyDown}
      aria-label={`Map of places around ${anchor.name}`}
      className="m-0 h-[100dvh] max-h-none w-screen max-w-none overscroll-contain bg-map-ground p-0 backdrop:bg-ink/40"
    >
      {/* Focusable so that a tap on the ground keeps the keyboard's focus in
          the map, where the arrow keys mean something. */}
      <div ref={frameRef} tabIndex={-1} className="relative h-full w-full select-none overflow-hidden outline-none">
        <MapCanvas
          anchor={anchor}
          places={places}
          route={route}
          basemap={basemap}
          detail={detail}
          viewport={viewport}
          size={size}
          timezone={timezone}
          selectedId={selectedId}
          onSelect={onSelect}
          groundProps={gestures}
        />

        <div className="absolute inset-x-4 top-[max(0.875rem,env(safe-area-inset-top))] z-30 flex items-start gap-2">
          <div className="min-w-0 flex-1">{children}</div>
          {toolbar}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close map"
            className="grid size-9 flex-none place-items-center rounded-full border border-border bg-card text-ink shadow-[var(--shadow-chip)] hover:bg-surface focus-visible:outline-2 focus-visible:outline-primary"
          >
            <X className="size-5" aria-hidden />
          </button>
        </div>

        {/* ODbL requires the credit wherever the geometry is shown. */}
        {(basemap ?? detail?.[0]) !== undefined && (
          <p className="pointer-events-none absolute right-1.5 top-[calc(max(0.875rem,env(safe-area-inset-top))+2.5rem)] z-10 text-[9px] leading-none text-muted-faint">
            {(basemap ?? detail?.[0])?.attribution}
          </p>
        )}

        {/* Controls sit directly above whatever the bottom is showing, so a
            card sliding in pushes them up rather than under. */}
        <div className="pointer-events-none absolute inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-20 flex flex-col items-stretch gap-2">
          <div className="pointer-events-auto flex justify-end">
            <MapControls
              onZoomIn={() => zoom(ZOOM_STEP)}
              onZoomOut={() => zoom(1 / ZOOM_STEP)}
              onRecentre={() => setViewport(fitted)}
              canZoomIn={canZoomIn}
              canZoomOut={canZoomOut}
            />
          </div>
          <div className="pointer-events-auto flex flex-col items-start gap-1.5">
            {spur !== null && <SpurPill place={spur} anchor={anchor} />}
            {selected !== null ? (
              <div className="w-full">
                <PlaceCard
                  place={selected}
                  timezone={timezone}
                  selected
                  onSelect={() => onSelect(null)}
                />
              </div>
            ) : (
              <RouteStrip route={route} />
            )}
          </div>
        </div>
      </div>
    </dialog>
  )
}

