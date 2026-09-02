import { useLayoutEffect, useState, type RefObject } from 'react'
import type { Size } from './projection'

/** The pixel size of the box a map is drawn into.

 *  Read before first paint and then observed, so the viewport can put its
 *  `radiusM` along whichever side is shorter. Falls back to `fallback` where
 *  there is no layout to measure (tests), and never reports a zero side. */
export function useFrameSize(ref: RefObject<HTMLElement | null>, fallback: Size): Size {
  const [size, setSize] = useState<Size>(fallback)

  useLayoutEffect(() => {
    const el = ref.current
    if (el === null) return
    const read = (width: number, height: number) => {
      const w = Math.round(width)
      const h = Math.round(height)
      if (w > 0 && h > 0) setSize((s) => (s.w === w && s.h === h ? s : { w, h }))
    }
    const rect = el.getBoundingClientRect()
    read(rect.width, rect.height)
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) read(entry.contentRect.width, entry.contentRect.height)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [ref])

  return size
}
