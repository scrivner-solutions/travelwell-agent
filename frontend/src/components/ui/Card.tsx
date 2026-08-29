import type { ButtonHTMLAttributes, HTMLAttributes } from 'react'

/* No shadow: depth comes from border and surface. A surface that genuinely
 * floats above the page opts in with shadow-[var(--shadow-card)]. */
const cardClass = 'rounded-card border border-border-soft bg-card p-4'

export function Card({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`${cardClass} ${className}`} {...props} />
}

/** A whole-card tap target; a real button so it stays keyboard-reachable. */
export function CardButton({
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`${cardClass} block w-full text-left hover:bg-surface ${className}`}
      {...props}
    />
  )
}
