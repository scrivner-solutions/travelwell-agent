import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'

/**
 * Bottom sheet on the native <dialog> element: focus trap, Esc, and inert
 * background come from the platform. Open/closed state is owned by the
 * caller - routes drive it from the ?sheet= search param so every sheet is
 * deep-linkable (swipe-dismiss lands with the interaction pass in Phase 2).
 */
export function Sheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title: string
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
      className="m-0 mt-auto w-full max-w-none rounded-t-panel bg-card p-0 shadow-[var(--shadow-sheet)] backdrop:bg-ink/40 open:translate-y-0"
    >
      <div className="mx-auto w-full max-w-lg p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
        <header className="mb-4 flex items-start justify-between gap-4">
          <h2 className="font-display text-display-sm text-balance">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-1.5 text-muted hover:bg-border-soft focus-visible:outline-2 focus-visible:outline-primary"
          >
            <X className="size-5" aria-hidden />
          </button>
        </header>
        {children}
      </div>
    </dialog>
  )
}
