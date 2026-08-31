import { describe, expect, it } from 'vitest'
import { SOURCE_ACTION_LABEL, SOURCE_STATE, canGoBackInApp, sourceAction } from './sources'

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

/**
 * What this pins: the reported bug. Pressing Done after connecting a calendar
 * returned the user to Google's consent screen, because the only guard was
 * history.length > 1, which is true after the redirect chain and says nothing
 * about whether the previous entry is ours.
 */
describe('canGoBackInApp', () => {
  it('refuses back after the OAuth callback, however deep the history', () => {
    expect(canGoBackInApp(true, 2)).toBe(false)
    expect(canGoBackInApp(true, 50)).toBe(false)
  })

  it('allows back for an ordinary in-app visit', () => {
    expect(canGoBackInApp(false, 2)).toBe(true)
  })

  it('refuses back when this is the only entry, as before', () => {
    expect(canGoBackInApp(false, 1)).toBe(false)
  })
})
