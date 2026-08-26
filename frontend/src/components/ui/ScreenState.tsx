import type { ReactNode } from 'react'
import { CloudOff } from 'lucide-react'

/**
 * Shared surfaces for the non-success states every screen must design
 * (loading / empty / degraded). Degraded is visible, never simulated: when
 * the backend is unreachable the user sees this, not stand-in data.
 */

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-muted" role="status">
      <span className="size-6 animate-spin rounded-full border-2 border-border border-t-primary" aria-hidden />
      <p className="text-body-sm">{label}</p>
    </div>
  )
}

export function EmptyState({
  title,
  detail,
  action,
}: {
  title: string
  detail?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-center">
      <p className="font-display text-display-sm font-medium text-balance">{title}</p>
      {detail !== undefined && <p className="max-w-xs text-body-sm text-muted">{detail}</p>}
      {action !== undefined && <div className="mt-3">{action}</div>}
    </div>
  )
}

export function DegradedState({
  title,
  detail,
  onRetry,
}: {
  title: string
  detail?: string
  onRetry?: () => void
}) {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-center" role="alert">
      <CloudOff className="size-6 text-muted-soft" aria-hidden />
      <p className="text-body font-semibold">{title}</p>
      {detail !== undefined && <p className="max-w-xs text-body-sm text-muted">{detail}</p>}
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 rounded-control border border-border px-4 py-2 text-body-sm font-semibold text-primary hover:border-primary focus-visible:outline-2 focus-visible:outline-primary"
        >
          Try again
        </button>
      )}
    </div>
  )
}
