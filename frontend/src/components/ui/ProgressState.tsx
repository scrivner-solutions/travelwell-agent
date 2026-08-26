import { Loader2, CheckCircle2, XCircle } from 'lucide-react'

export type ProgressPhase = 'working' | 'done' | 'failed'

/**
 * The shared live-progress surface: purposeful copy ("Checking reservation
 * availability...") fed by SSE trace events, with honest terminal states.
 * Because every working/terminal state renders through this component, faking
 * completion is structurally hard: `done` and `failed` come from the server's
 * terminal event, never from a client timer.
 */
export function ProgressState({
  phase,
  label,
  detail,
}: {
  phase: ProgressPhase
  label: string
  detail?: string
}) {
  return (
    <div className="flex items-start gap-3" role="status" aria-live="polite">
      {phase === 'working' && (
        <Loader2 className="mt-0.5 size-5 shrink-0 animate-spin text-state-working" aria-hidden />
      )}
      {phase === 'done' && (
        <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-state-confirmed" aria-hidden />
      )}
      {phase === 'failed' && (
        <XCircle className="mt-0.5 size-5 shrink-0 text-state-failed" aria-hidden />
      )}
      <div>
        <p className="text-body-sm font-medium">{label}</p>
        {detail !== undefined && <p className="text-caption text-muted">{detail}</p>}
      </div>
    </div>
  )
}
