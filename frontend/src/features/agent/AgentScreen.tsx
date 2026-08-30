import { EmptyState } from '@/components/ui/ScreenState'
import { ProfileButton } from '@/components/ui/ProfileButton'

// Placeholder until Phase 5 delivers the agent surface (voice and text into
// POST /events, live SSE run stream, structured results). Honest not-built
// state; no simulated conversations.
export function AgentScreen() {
  return (
    <>
      <header className="mb-4 flex items-center justify-between">
        <h1 className="font-display text-display">Agent</h1>
        <ProfileButton />
      </header>
      <EmptyState
        title="The agent surface isn't built yet"
        detail="Talking to TravelWell by voice or text arrives in a later milestone (Phase 5)."
      />
    </>
  )
}
