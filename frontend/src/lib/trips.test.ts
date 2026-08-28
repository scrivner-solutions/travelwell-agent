import { describe, expect, it } from 'vitest'
import { calendarSpan } from './trips'

describe('calendarSpan', () => {
  it('pads a mid-week range out to Sunday-to-Saturday', () => {
    // 2026-09-09 is a Wednesday, 2026-09-12 already a Saturday.
    const span = calendarSpan('2026-09-09', '2026-09-12')
    expect(span[0]).toBe('2026-09-06')
    expect(span[span.length - 1]).toBe('2026-09-12')
    expect(span).toHaveLength(7)
  })

  it('crosses month boundaries without skipping days', () => {
    // 2026-08-30 is a Sunday; the closing Saturday lands in September.
    const span = calendarSpan('2026-08-30', '2026-09-02')
    expect(span[0]).toBe('2026-08-30')
    expect(span[span.length - 1]).toBe('2026-09-05')
    expect(span).toContain('2026-08-31')
    expect(span).toContain('2026-09-01')
    expect(span).toHaveLength(7)
  })

  it('keeps a single day inside one full week', () => {
    const span = calendarSpan('2026-08-25', '2026-08-25')
    expect(span[0]).toBe('2026-08-23')
    expect(span[span.length - 1]).toBe('2026-08-29')
    expect(span).toHaveLength(7)
  })
})
