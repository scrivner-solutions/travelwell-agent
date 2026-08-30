import { EmptyState } from '@/components/ui/ScreenState'
import { ProfileButton } from '@/components/ui/ProfileButton'

// Placeholder until Phase 4 delivers the map-first Explore (ported
// marker/card sync, category chips, plan route overlay). It says so plainly:
// an honest not-built state, never simulated content.
export function ExploreScreen() {
  return (
    <>
      <header className="mb-4 flex items-center justify-between">
        <h1 className="font-display text-display">Explore</h1>
        <ProfileButton />
      </header>
      <EmptyState
        title="Explore isn't built yet"
        detail="The map with places picked around your schedule arrives in a later milestone (Phase 4)."
      />
    </>
  )
}
