import { useEffect, useRef, type MouseEvent, type PointerEvent, type Ref } from 'react'
import { pan, zoomAt, type Point, type Size, type Viewport, type ZoomBounds } from './projection'

/* A press that ends within this distance and time is a tap and reaches the
 * pin; anything else is a drag and its click is swallowed. */
const TAP_MAX_PX = 6
const TAP_MAX_MS = 300

/* A wheel notch of ~100 px zooms by about 16%; a trackpad's small deltas add
 * up to a smooth glide. Line-mode wheels report in lines, not pixels. */
const WHEEL_ZOOM_RATE = 0.0015
const PX_PER_WHEEL_LINE = 16

export interface MapGestureOptions {
  size: Size
  bounds: ZoomBounds
  onChange: (update: (vp: Viewport) => Viewport) => void
}

export interface GroundProps {
  ref: Ref<HTMLDivElement>
  onPointerDown: (e: PointerEvent<HTMLDivElement>) => void
  onPointerMove: (e: PointerEvent<HTMLDivElement>) => void
  onPointerUp: (e: PointerEvent<HTMLDivElement>) => void
  onPointerCancel: (e: PointerEvent<HTMLDivElement>) => void
  onClickCapture: (e: MouseEvent<HTMLDivElement>) => void
  style: { touchAction: 'none' }
}

/** Drag to pan, wheel and pinch to zoom about the pointer, on Pointer Events
 *  so mouse and touch are one code path. No animation-frame batching: the
 *  browser already delivers `pointermove` once per frame.
 *
 *  Pointer capture is taken only once a press has become a drag. Taking it
 *  on pointerdown would make the ground the target of the pointerup, and the
 *  click a tap on a pin is waiting for would then never reach the pin. */
export function useMapGestures({ size, bounds, onChange }: MapGestureOptions): GroundProps {
  const ground = useRef<HTMLDivElement | null>(null)
  const pointers = useRef(new Map<number, Point>())
  const press = useRef<{ at: Point; t: number } | null>(null)
  const dragging = useRef(false)
  const swallowClick = useRef(false)

  const local = (e: { clientX: number; clientY: number }): Point => {
    const rect = ground.current?.getBoundingClientRect()
    return { x: e.clientX - (rect?.left ?? 0), y: e.clientY - (rect?.top ?? 0) }
  }

  /* React registers wheel listeners as passive, so preventDefault() through a
     prop is a no-op and a trackpad pinch would zoom the page. Bound natively. */
  useEffect(() => {
    const el = ground.current
    if (el === null) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const delta = e.deltaMode === 1 ? e.deltaY * PX_PER_WHEEL_LINE : e.deltaY
      const factor = Math.exp(-delta * WHEEL_ZOOM_RATE)
      const about = local(e)
      onChange((vp) => zoomAt(vp, factor, about, size, bounds))
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  })

  const capture = (e: PointerEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    if (typeof el.setPointerCapture === 'function' && !el.hasPointerCapture?.(e.pointerId)) {
      el.setPointerCapture(e.pointerId)
    }
  }

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    swallowClick.current = false
    const at = local(e)
    pointers.current.set(e.pointerId, at)
    if (pointers.current.size === 1) {
      press.current = { at, t: performance.now() }
      dragging.current = false
    } else {
      // A second finger is never a tap.
      dragging.current = true
      capture(e)
    }
  }

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const was = pointers.current.get(e.pointerId)
    if (was === undefined) return
    const now = local(e)
    const others = [...pointers.current.entries()].filter(([id]) => id !== e.pointerId)
    pointers.current.set(e.pointerId, now)

    if (others.length === 0) {
      if (!dragging.current) {
        const from = press.current?.at ?? was
        if (Math.hypot(now.x - from.x, now.y - from.y) < TAP_MAX_PX) return
        dragging.current = true
        capture(e)
      }
      onChange((vp) => pan(vp, now.x - was.x, now.y - was.y, size))
      return
    }

    /* Pinch: the distance between the two fingers is the zoom, their midpoint
       is what it zooms about, and its drift is a pan on top. */
    const other = others[0]![1]
    const wasDist = Math.hypot(was.x - other.x, was.y - other.y)
    const nowDist = Math.hypot(now.x - other.x, now.y - other.y)
    const wasMid = { x: (was.x + other.x) / 2, y: (was.y + other.y) / 2 }
    const nowMid = { x: (now.x + other.x) / 2, y: (now.y + other.y) / 2 }
    const factor = wasDist > 0 ? nowDist / wasDist : 1
    onChange((vp) =>
      pan(zoomAt(vp, factor, wasMid, size, bounds), nowMid.x - wasMid.x, nowMid.y - wasMid.y, size),
    )
  }

  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    if (!pointers.current.delete(e.pointerId)) return
    if (pointers.current.size > 0) return
    const held = press.current === null ? 0 : performance.now() - press.current.t
    if (dragging.current || held > TAP_MAX_MS) swallowClick.current = true
    dragging.current = false
    press.current = null
  }

  /* The click a drag leaves behind must not select the pin it ended on. */
  const onClickCapture = (e: MouseEvent<HTMLDivElement>) => {
    if (!swallowClick.current) return
    swallowClick.current = false
    e.stopPropagation()
    e.preventDefault()
  }

  return {
    ref: ground,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerCancel: onPointerUp,
    onClickCapture,
    style: { touchAction: 'none' },
  }
}
