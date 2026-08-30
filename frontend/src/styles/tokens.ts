/**
 * Typed mirror of tokens.css for the few places that need token values in
 * JS (Maps styling, canvas drawing). Rendering code should use CSS custom
 * properties / Tailwind utilities instead.
 */
export const colors = {
  ink: '#042C53',
  primary: '#185FA5',
  primaryDeep: '#0F4C8A',
  agent: '#5B52B8',
  agentBright: '#7F77DD',
  surface: '#F4F7FB',
  card: '#FFFFFF',
  border: '#E1E7F0',
  borderSoft: '#EDF1F7',
  muted: '#5A6B80',
  mutedSoft: '#8A97A8',
} as const

export const radius = {
  card: 22,
  panel: 16,
  control: 14,
} as const

export const motion = {
  quickMs: 140,
  standardMs: 240,
} as const
