import { Link } from '@tanstack/react-router'

/**
 * The circular profile entry in every screen header (design prototype: 40px
 * circle, person icon traced from the prototype's exact SVG paths).
 */
export function ProfileButton() {
  return (
    <Link
      to="/profile"
      aria-label="Profile"
      className="grid size-10 flex-none place-items-center rounded-full border border-border bg-card text-muted hover:bg-state-neutral-soft focus-visible:outline-2 focus-visible:outline-primary"
    >
      <svg
        width="19"
        height="19"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <circle cx="12" cy="8" r="3.6" />
        <path d="M5 20v-1a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v1" />
      </svg>
    </Link>
  )
}
