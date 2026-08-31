import { describe, expect, it } from 'vitest'
import { SOURCE_ACTION_LABEL, SOURCE_STATE, sourceAction } from './sources'

/**
 * What this pins: a row only offers what the backend will accept. /me/sources
 * returns rows for kinds this build cannot handshake (the demo seeds a gmail
 * one), and connect, callback and disconnect all 404 for those, so the button
 * has to be absent rather than merely disappointing.
 */
describe('sourceAction', () => {
  it('offers nothing for a kind this build cannot connect', () => {
    expect(sourceAction(null, false)).toBeNull()
    // Including one that claims to be connected: the DELETE 404s just the same.
    expect(sourceAction('connected', false)).toBeNull()
    expect(sourceAction('revoked', false)).toBeNull()
  })

  it('offers connect for a connectable kind with no grant', () => {
    expect(sourceAction(null, true)).toBe('connect')
  })

  it('offers disconnect only while a grant is live', () => {
    expect(sourceAction('connected', true)).toBe('disconnect')
  })

  it('offers reconnect for both ways a grant can stop working', () => {
    expect(sourceAction('revoked', true)).toBe('reconnect')
    expect(sourceAction('error', true)).toBe('reconnect')
  })
})

describe('SOURCE_STATE', () => {
  it('names states, not the actions that fix them', () => {
    // `revoked` used to read 'Reconnect', which is now the button beside it.
    const actions = Object.values(SOURCE_ACTION_LABEL)
    for (const state of Object.values(SOURCE_STATE)) {
      expect(actions).not.toContain(state.text)
    }
  })
})
