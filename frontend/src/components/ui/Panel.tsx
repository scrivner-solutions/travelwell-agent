import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'

/**
 * A full-screen surface that takes over the viewport, on the same <dialog>
 * element Sheet uses so the focus trap, Esc and inert background still come
 * from the platform. Sheet is for a decision you take beside the page; this is
 * for a flow that becomes the page, so the close control is a target in the
 * header rather than a dismissable backdrop.
 */
export function Panel({
  open,
  onClose,
  title,
  aside,
  closeLabel = 'Close',
  children,
}: {
  open: boolean
  onClose: () => void
  title: string
  /** Right-hand slot in the header, for progress or a counter. */
  aside?: ReactNode
  /** Name the surface when the body also carries a Close, so the two controls
      do not announce the same thing. */
  closeLabel?: string
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onCancel={onClose}
      className="m-0 h-full max-h-none w-full max-w-none bg-surface p-0"
    >
      <div className="flex h-full flex-col">
        <header className="flex flex-none items-center gap-3 border-b border-border bg-surface px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
          <button
            onClick={onClose}
            aria-label={closeLabel}
            className="grid size-10 flex-none place-items-center rounded-lg border border-border bg-card text-ink hover:bg-state-neutral-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            <X className="size-5" aria-hidden />
          </button>
          <h2 className="min-w-0 flex-1 truncate text-body font-semibold">{title}</h2>
          {aside}
        </header>
        <div className="flex-1 overflow-y-auto px-5 pb-[max(2rem,env(safe-area-inset-bottom))] pt-6">
          <div className="mx-auto w-full max-w-lg">{children}</div>
        </div>
      </div>
    </dialog>
  )
}
