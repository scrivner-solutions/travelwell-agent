import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { SignInScreen } from '@/features/onboarding/SignInScreen'

/**
 * URL contract: /sign-in?error=oauth_failed|not_allowed — the OAuth callback
 * redirects here with an error code instead of a session cookie.
 */
export const Route = createFileRoute('/sign-in')({
  validateSearch: z.object({
    error: z.enum(['oauth_failed', 'not_allowed']).optional().catch(undefined),
  }),
  component: SignInScreen,
})
