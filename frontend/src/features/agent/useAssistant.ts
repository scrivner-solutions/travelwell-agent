import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { askAssistant, type AssistantTurn } from '@/api/queries'

/**
 * One utterance, sent once, with the answer kept on screen after it lands.
 *
 * The idempotency key is minted when the traveler sends, not per attempt, so a
 * retry after a dropped response replays the turn that already happened rather
 * than paying for a second one. React Query's own retry would otherwise turn a
 * flaky network into two model calls and possibly two different answers.
 */
export function useAssistant(tripId: string | undefined) {
  const queryClient = useQueryClient()
  const [asked, setAsked] = useState<string>('')

  const ask = useMutation<AssistantTurn, Error, string>({
    mutationFn: (utterance: string) => {
      if (tripId === undefined) throw new Error('no trip in focus')
      return askAssistant(tripId, utterance, crypto.randomUUID())
    },
    onMutate: (utterance) => {
      setAsked(utterance)
    },
    onSuccess: (turn) => {
      // Only invalidate when something moved. A turn that changed nothing
      // should not make the plan flicker as though it had.
      if (turn.applied.length === 0) return
      void queryClient.invalidateQueries({ queryKey: ['trips', tripId, 'plan'] })
      void queryClient.invalidateQueries({ queryKey: ['trips', tripId, 'today'] })
      void queryClient.invalidateQueries({ queryKey: ['trips'] })
    },
  })

  return { ask, asked, turn: ask.data, error: ask.error }
}
