import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { planQueryOptions, tripsQueryOptions } from '@/api/queries'
import { focusTrip } from '@/lib/trips'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { EmptyState, LoadingState } from '@/components/ui/ScreenState'
import { ProfileButton } from '@/components/ui/ProfileButton'
import { useAssistant } from './useAssistant'

/**
 * The escape hatch for what the fixed UI cannot express.
 *
 * Not a conversation: one utterance, one answer, and the plan behind it has
 * already moved by the time the answer renders. The prototype's agent screen is
 * the layout - eyebrow, query bubble, summary line, result cards, Try chips -
 * with two deliberate departures.
 *
 * The chips are the first. The prototype offers "Find dinner" and "Something
 * healthy nearby", and this build can do neither; a chip that types a sentence
 * the agent will decline is a worse surface than one fewer chip. They are
 * regenerated from the verb that exists when a second verb lands.
 *
 * The mic is the second. Voice is a transcription problem, not a backend one,
 * and until something transcribes there is nothing honest to put behind it.
 */

const TRY = [
  'I am tired today, skip the gym',
  'Not doing the early one tomorrow',
  'Drop the last thing on my plan',
]

export function AgentScreen() {
  const [draft, setDraft] = useState('')
  const trips = useQuery(tripsQueryOptions())
  const trip = trips.data ? focusTrip(trips.data) : undefined
  const plan = useQuery({
    ...planQueryOptions(trip?.id ?? ''),
    enabled: trip !== undefined,
  })
  const { ask, asked, turn } = useAssistant(trip?.id)

  // No past-trip branch: `focusTrip` only ever returns a live trip, so a
  // finished one arrives here as no trip at all. The 409 the server raises on a
  // past plan therefore has no path to reach this screen.
  const items = plan.data?.items ?? []
  const open = items.filter((i) => i.status !== 'skipped' && i.status !== 'removed')
  // Deliberately not gated on the plan query. Blocking the box until a second
  // request lands makes the surface unusable exactly when that request is slow,
  // and the server answers an utterance about a plan that is not there far
  // better than a disabled textarea explains itself.
  const ready = trip !== undefined

  const send = (utterance: string) => {
    const text = utterance.trim()
    if (text === '' || !ready || ask.isPending) return
    setDraft('')
    ask.mutate(text)
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    send(draft)
  }

  return (
    <>
      <header className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-eyebrow-wide font-semibold uppercase text-muted-soft">
            Ask TravelWell
          </p>
          <h1 className="font-display text-display">Agent</h1>
        </div>
        <ProfileButton />
      </header>

      {trips.isLoading && <LoadingState label="Finding your trip" />}

      {!trips.isLoading && trip === undefined && (
        <EmptyState
          title="No trip to change right now"
          detail="Trips that have ended keep their plan as a record. Add or confirm a trip and the agent can change its plan from here."
        />
      )}

      {trip !== undefined && (
        <>
          {asked !== '' && (
            <div className="mb-5">
              <div className="mb-3 flex justify-end">
                <p className="max-w-[80%] rounded-panel rounded-br-[4px] bg-primary px-4 py-2.5 text-body-sm font-medium text-white">
                  {asked}
                </p>
              </div>

              {ask.isPending && <LoadingState label="Reading your plan" />}

              {turn !== undefined && !ask.isPending && (
                <>
                  <p className="mx-0.5 mb-3 text-body-sm font-medium text-muted">
                    {turn.reply}
                  </p>
                  <div className="flex flex-col gap-2.5">
                    {turn.applied.map((change) => (
                      <Card key={change.item_id} className="flex items-start justify-between gap-3">
                        <p className="text-heading-sm text-ink">{change.name}</p>
                        <p className="flex-none rounded-control bg-surface px-2.5 py-1.5 text-caption font-semibold text-ink">
                          Skipped
                        </p>
                      </Card>
                    ))}
                  </div>
                </>
              )}

              {ask.isError && (
                <p className="mx-0.5 text-caption font-semibold text-state-attention">
                  That did not reach the agent, and nothing on the plan changed.
                  Try again.
                </p>
              )}
            </div>
          )}

          {asked === '' && plan.isSuccess && open.length === 0 && (
            <EmptyState
              title="Nothing on this plan to change"
              detail="Once this trip has a plan, saying what you want dropped will drop it."
            />
          )}

          {asked === '' && open.length > 0 && (
            <Card className="mb-5">
              <p className="text-eyebrow-wide font-semibold uppercase text-muted-soft">
                What this can do today
              </p>
              <p className="mt-3 text-body-sm text-muted">
                Say what you want taken off this trip's plan, in your own words,
                and it comes off. Adding, moving and booking are still done from
                the plan itself.
              </p>
            </Card>
          )}

          <div className="mb-4">
            <p className="mx-0.5 mb-2.5 text-label font-medium uppercase text-muted-soft">
              Try
            </p>
            <div className="flex flex-wrap gap-2">
              {TRY.map((text) => (
                <button
                  key={text}
                  type="button"
                  disabled={ask.isPending}
                  onClick={() => send(text)}
                  className="h-9 rounded-full border border-border bg-card px-3.5 text-body-sm font-medium text-ink hover:bg-surface disabled:text-muted-soft"
                >
                  {text}
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={submit} className="flex items-end gap-2">
            <label className="sr-only" htmlFor="utterance">
              What would you like changed?
            </label>
            <textarea
              id="utterance"
              rows={2}
              value={draft}
              disabled={!ready || ask.isPending}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="I am tired today, skip the gym"
              className="min-w-0 flex-1 resize-none rounded-card border border-border bg-card px-3.5 py-2.5 text-body placeholder:text-muted-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:text-muted-soft"
            />
            <Button type="submit" disabled={!ready || ask.isPending || draft.trim() === ''}>
              {ask.isPending ? 'Sending' : 'Send'}
            </Button>
          </form>
        </>
      )}
    </>
  )
}
