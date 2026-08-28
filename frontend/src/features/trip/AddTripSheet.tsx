import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Sheet } from '@/components/ui/Sheet'
import { Button } from '@/components/ui/Button'
import { createTrip, type Trip } from '@/api/queries'

const inputClass =
  'h-[var(--control-height)] w-full rounded-control border border-border bg-card px-4 text-body focus-visible:outline-2 focus-visible:outline-primary'

/** Manual trip entry ("New trip" in the design): the fallback when nothing
 * was detected. Creates a confirmed manual trip via POST /trips. */
export function AddTripSheet({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (trip: Trip) => void
}) {
  const [destination, setDestination] = useState('')
  const [startsOn, setStartsOn] = useState('')
  const [endsOn, setEndsOn] = useState('')
  const [lodging, setLodging] = useState('')
  const [purpose, setPurpose] = useState('')
  // One key per logical create: retries after a network failure reuse it, a
  // new form after success gets a fresh one.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID())

  const queryClient = useQueryClient()
  const create = useMutation({
    mutationFn: () =>
      createTrip(
        {
          destination_name: destination.trim(),
          starts_on: startsOn,
          ends_on: endsOn,
          lodging_name: lodging.trim() || undefined,
          label: purpose.trim() || undefined,
        },
        idempotencyKey,
      ),
    onSuccess: (trip) => {
      void queryClient.invalidateQueries({ queryKey: ['trips'] })
      setDestination('')
      setStartsOn('')
      setEndsOn('')
      setLodging('')
      setPurpose('')
      setIdempotencyKey(crypto.randomUUID())
      onCreated(trip)
    },
  })

  const ready =
    destination.trim() !== '' &&
    startsOn !== '' &&
    endsOn !== '' &&
    startsOn <= endsOn

  return (
    <Sheet open={open} onClose={onClose} title="New trip">
      <form
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault()
          create.mutate()
        }}
      >
        <label className="text-body-sm font-medium" htmlFor="trip-where">
          Where
        </label>
        <input
          id="trip-where"
          required
          maxLength={120}
          placeholder="Austin, TX"
          value={destination}
          onChange={(event) => setDestination(event.target.value)}
          className={inputClass}
        />

        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-3">
            <label className="text-body-sm font-medium" htmlFor="trip-starts">
              First day
            </label>
            <input
              id="trip-starts"
              type="date"
              required
              value={startsOn}
              onChange={(event) => {
                setStartsOn(event.target.value)
                // Keep the range ordered instead of erroring later.
                if (endsOn !== '' && endsOn < event.target.value)
                  setEndsOn(event.target.value)
              }}
              className={inputClass}
            />
          </div>
          <div className="flex flex-col gap-3">
            <label className="text-body-sm font-medium" htmlFor="trip-ends">
              Last day
            </label>
            <input
              id="trip-ends"
              type="date"
              required
              min={startsOn || undefined}
              value={endsOn}
              onChange={(event) => setEndsOn(event.target.value)}
              className={inputClass}
            />
          </div>
        </div>

        <label className="text-body-sm font-medium" htmlFor="trip-lodging">
          Staying at <span className="font-normal text-muted">(optional)</span>
        </label>
        <input
          id="trip-lodging"
          maxLength={120}
          placeholder="Not booked yet"
          value={lodging}
          onChange={(event) => setLodging(event.target.value)}
          className={inputClass}
        />

        <label className="text-body-sm font-medium" htmlFor="trip-purpose">
          Purpose <span className="font-normal text-muted">(optional)</span>
        </label>
        <input
          id="trip-purpose"
          maxLength={80}
          placeholder="Conference"
          value={purpose}
          onChange={(event) => setPurpose(event.target.value)}
          className={inputClass}
        />

        <p className="text-caption text-muted">
          I'll watch your calendar for anything that lands in these dates.
        </p>
        <Button type="submit" disabled={!ready || create.isPending}>
          {create.isPending ? 'Creating…' : 'Create trip'}
        </Button>
        {create.isError && (
          <p role="alert" className="text-body-sm text-state-failed">
            Could not create the trip. Check your connection and retry.
          </p>
        )}
      </form>
    </Sheet>
  )
}
