import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatTripTime, formatTripTimeRange, formatTripDay, deviceTimeZone } from './time'

// The DoD's timezone guarantee: a 5:30 PM Chicago workout reads 5:30 PM no
// matter what zone the test runner (or the user's phone) is in.
const chicago530pm = '2026-08-25T22:30:00Z' // 17:30 America/Chicago (CDT)

describe('trip timezone rendering', () => {
  it('renders instants in the trip timezone, not the device timezone', () => {
    expect(formatTripTime(chicago530pm, 'America/Chicago')).toBe('5:30 PM')
    expect(formatTripTime(chicago530pm, 'America/Los_Angeles')).toBe('3:30 PM')
  })

  it('formats ranges within the trip timezone', () => {
    expect(
      formatTripTimeRange(chicago530pm, '2026-08-25T23:15:00Z', 'America/Chicago'),
    ).toBe('5:30 PM - 6:15 PM')
  })

  it('formats trip-local days across the date line from the device zone', () => {
    // Midnight UTC is still the previous evening in Chicago.
    expect(formatTripDay('2026-08-26T00:30:00Z', 'America/Chicago')).toBe('Tue, Aug 25')
  })
})

function onDeviceIn(zone: string) {
  vi.spyOn(Intl, 'DateTimeFormat').mockReturnValue({
    resolvedOptions: () => ({ timeZone: zone }),
  } as unknown as Intl.DateTimeFormat)
}

describe('device timezone', () => {
  afterEach(() => vi.restoreAllMocks())

  it('reports the zone the device is set to', () => {
    onDeviceIn('Europe/Berlin')
    expect(deviceTimeZone()).toBe('Europe/Berlin')
  })

  it('reports undefined rather than an empty string when the engine has no zone', () => {
    onDeviceIn('')
    expect(deviceTimeZone()).toBeUndefined()
  })
})
