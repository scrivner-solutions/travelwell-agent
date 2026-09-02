import { ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Sheet } from '@/components/ui/Sheet'
import { Toggle } from '@/components/ui/Toggle'
import {
  DEFAULT_FILTERS,
  TIME_WINDOWS,
  WALK_OPTIONS,
  WINDOW_LABELS,
  type FilterPrefs,
  type Filters,
} from './filters'

export interface FilterSheetProps {
  open: boolean
  onClose: () => void
  filters: Filters
  onChange: (filters: Filters) => void
  /** Undefined while the profile is loading: the two toggles wait. */
  prefs: FilterPrefs | undefined
  /** How many places the current filters leave, for the apply button. */
  count: number
  onStandingPreferences: () => void
}

function capLabel(cents: number): string {
  return cents % 100 === 0 ? `$${cents / 100}` : `$${(cents / 100).toFixed(2)}`
}

const eyebrow = 'text-eyebrow-wide font-semibold uppercase text-muted-soft'

function Segment<T>({
  label,
  options,
  value,
  onPick,
}: {
  label: string
  options: { label: string; value: T }[]
  value: T
  onPick: (value: T) => void
}) {
  return (
    <fieldset className="mt-5 min-w-0">
      <legend className={eyebrow}>{label}</legend>
      <div className="mt-2.5 flex gap-[7px]">
        {options.map((option) => {
          const on = option.value === value
          return (
            <button
              key={option.label}
              type="button"
              aria-pressed={on}
              onClick={() => onPick(option.value)}
              className={`h-11 flex-1 rounded-[12px] border text-caption font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
                on
                  ? 'border-primary bg-state-confirmed-soft text-primary-deep'
                  : 'border-border bg-card text-muted'
              }`}
            >
              {option.label}
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}

function ToggleRow({
  label,
  sub,
  on,
  disabled,
  onChange,
}: {
  label: string
  sub: string
  on: boolean
  disabled: boolean
  onChange: () => void
}) {
  return (
    <div className="flex items-center gap-3 border-b border-surface px-[15px] py-3.5 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className={`text-body-sm font-semibold ${disabled ? 'text-muted' : ''}`}>{label}</p>
        <p className="mt-0.5 text-label text-muted-soft">{sub}</p>
      </div>
      <Toggle on={on} label={label} disabled={disabled} onChange={onChange} />
    </div>
  )
}

/** The prototype's filter sheet, less the two controls no place carries data
 *  for (session length, membership coverage). Every change applies at once;
 *  the button at the bottom only says what it left and closes. */
export function FilterSheet({
  open,
  onClose,
  filters,
  onChange,
  prefs,
  count,
  onStandingPreferences,
}: FilterSheetProps) {
  const cap = prefs?.dayPassBudgetCents ?? null
  const wanted = prefs?.amenities ?? []

  return (
    <Sheet open={open} onClose={onClose} title="Filters">
      <Segment
        label="Time I have"
        options={TIME_WINDOWS.map((window) => ({ label: WINDOW_LABELS[window], value: window }))}
        value={filters.window}
        onPick={(window) => onChange({ ...filters, window })}
      />
      <Segment
        label="Walk at most"
        options={WALK_OPTIONS}
        value={filters.walk}
        onPick={(walk) => onChange({ ...filters, walk })}
      />

      <div className="mt-5 overflow-hidden rounded-panel border border-border bg-card">
        <ToggleRow
          label={cap === null ? 'Stay under my pass cap' : `Stay under my ${capLabel(cap)} pass cap`}
          sub={cap === null ? 'Set a pass cap in your profile' : 'Hides day passes above the cap'}
          on={filters.underCap}
          disabled={cap === null}
          onChange={() => onChange({ ...filters, underCap: !filters.underCap })}
        />
        <ToggleRow
          label="Must have my amenities"
          sub={wanted.length > 0 ? wanted.join(' · ') : 'None set yet'}
          on={filters.amenities}
          disabled={wanted.length === 0}
          onChange={() => onChange({ ...filters, amenities: !filters.amenities })}
        />
      </div>

      <button
        type="button"
        onClick={onStandingPreferences}
        className="mt-3.5 flex h-[52px] w-full items-center justify-between rounded-control border border-border px-[15px] text-left text-body-sm font-semibold hover:bg-surface focus-visible:outline-2 focus-visible:outline-primary"
      >
        Standing preferences
        <ChevronRight className="size-4 text-muted-soft" aria-hidden />
      </button>

      <div className="mt-[18px] flex gap-[9px]">
        <Button variant="secondary" onClick={() => onChange(DEFAULT_FILTERS)}>
          Reset
        </Button>
        <Button className="flex-1" onClick={onClose}>
          Show {count === 1 ? '1 place' : `${count} places`}
        </Button>
      </div>
    </Sheet>
  )
}
