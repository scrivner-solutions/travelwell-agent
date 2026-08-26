import type { HTMLAttributes } from 'react'

export function Card({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-card border border-border-soft bg-card p-4 shadow-[var(--shadow-card)] ${className}`}
      {...props}
    />
  )
}
