/** The design's switch: a 50 x 30 track with the knob sliding to the on side.
 *  Disabled when there is nothing for it to compare against, and the row it
 *  sits in says why, so the switch never looks broken. */
export function Toggle({
  on,
  label,
  onChange,
  disabled = false,
}: {
  on: boolean
  label: string
  onChange: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={onChange}
      className={`flex h-[30px] w-[50px] flex-none rounded-full p-[3px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-45 ${
        on ? 'justify-end bg-primary' : 'justify-start bg-track-off'
      }`}
    >
      <span className="block size-6 rounded-full bg-card shadow-[0_1px_3px_rgba(4,44,83,0.35)]" />
    </button>
  )
}
