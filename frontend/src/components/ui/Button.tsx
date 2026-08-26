import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost'

const variantClasses: Record<Variant, string> = {
  primary:
    'bg-primary text-white hover:bg-primary-deep disabled:bg-muted-soft',
  secondary:
    'bg-card text-primary border border-border hover:border-primary disabled:text-muted-soft',
  ghost: 'bg-transparent text-primary hover:bg-border-soft disabled:text-muted-soft',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

export function Button({ variant = 'primary', className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`h-[var(--control-height)] rounded-control px-5 font-body text-body font-semibold transition-colors duration-[var(--motion-quick)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed ${variantClasses[variant]} ${className}`}
      {...props}
    />
  )
}
