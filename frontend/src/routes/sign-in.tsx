import { createFileRoute } from '@tanstack/react-router'
import { SignInScreen } from '@/features/onboarding/SignInScreen'

export const Route = createFileRoute('/sign-in')({
  component: SignInScreen,
})
