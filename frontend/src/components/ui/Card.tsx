import type { ButtonHTMLAttributes, HTMLAttributes } from 'react'

const cardClass =
  'rounded-card border border-border-soft bg-card p-4 shadow-[var(--shadow-card)]'

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
