import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Button } from '@/components/ui/Button'
import { api, throwOnError, ApiError } from '@/api/client'
import { loadRuntimeConfig } from '@/lib/config'

function errorCopy(error: unknown): string {
  if (error instanceof ApiError) {
    // A wrong or expired code answers 400 code_invalid.
    if (
      error.problem?.code === 'code_invalid' ||
      error.status === 401 ||
      error.status === 403
    ) {
      return 'That code did not match. Check the newest email and try again.'
    }
    return error.problem?.detail ?? 'Sign-in is unavailable right now. Try again in a moment.'
  }
  return 'TravelWell is unreachable. Check your connection and try again.'
}

export function SignInScreen() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')

  const requestCode = useMutation({
    mutationFn: async () => {
      const client = await api()
      throwOnError(await client.POST('/auth/email-code', { body: { email } }))
    },
  })

  const verifyCode = useMutation({
    mutationFn: async () => {
      const client = await api()
      return throwOnError(
        await client.POST('/auth/email-code/verify', { body: { email, code } }),
      )
    },
    onSuccess: () => void navigate({ to: '/today' }),
  })

  const startOauth = async (provider: 'google') => {
    // Same-origin fallback if config.json is unreachable; that is the
    // deployed default anyway.
    const { apiBaseUrl } = await loadRuntimeConfig().catch(() => ({ apiBaseUrl: '' }))
    window.location.href = `${apiBaseUrl}/api/v1/auth/oauth/${provider}/start`
  }

  const codeSent = requestCode.isSuccess

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-6 px-6">
      <header>
        <h1 className="font-display text-display font-medium">TravelWell</h1>
        <p className="mt-1 text-body text-muted">
          Wellness that travels with your calendar.
        </p>
      </header>

      <div className="flex flex-col gap-3">
        <Button variant="secondary" onClick={() => void startOauth('google')}>
          Continue with Google
        </Button>
      </div>

      <div className="flex items-center gap-3 text-caption text-muted-soft">
        <span className="h-px flex-1 bg-border" aria-hidden />
        or use email
        <span className="h-px flex-1 bg-border" aria-hidden />
      </div>

      {!codeSent ? (
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            requestCode.mutate()
          }}
        >
          <label className="text-body-sm font-medium" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="h-[var(--control-height)] rounded-control border border-border bg-card px-4 text-body focus-visible:outline-2 focus-visible:outline-primary"
          />
          <Button type="submit" disabled={requestCode.isPending}>
            {requestCode.isPending ? 'Sending code…' : 'Email me a code'}
          </Button>
          {requestCode.isError && (
            <p role="alert" className="text-body-sm text-state-failed">
              {errorCopy(requestCode.error)}
            </p>
          )}
        </form>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault()
            verifyCode.mutate()
          }}
        >
          <p className="text-body-sm text-muted">
            We sent a code to <span className="font-semibold text-ink">{email}</span>.
          </p>
          <label className="text-body-sm font-medium" htmlFor="code">
            Code
          </label>
          <input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            value={code}
            onChange={(event) => setCode(event.target.value)}
            className="h-[var(--control-height)] rounded-control border border-border bg-card px-4 text-body tracking-widest focus-visible:outline-2 focus-visible:outline-primary"
          />
          <Button type="submit" disabled={verifyCode.isPending}>
            {verifyCode.isPending ? 'Signing in…' : 'Sign in'}
          </Button>
          {verifyCode.isError && (
            <p role="alert" className="text-body-sm text-state-failed">
              {errorCopy(verifyCode.error)}
            </p>
          )}
        </form>
      )}
    </main>
  )
}
