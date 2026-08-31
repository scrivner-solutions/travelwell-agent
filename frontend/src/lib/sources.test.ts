import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/client'
import {
  SOURCE_ACTION_LABEL,
  SOURCE_STATE,
  canGoBackInApp,
  sourceAction,
  syncFailureMessage,
  syncOutcomeMessage,
} from './sources'

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

/**
 * What this pins: a sync says what it did. The endpoint returns counts because
 * "nothing changed" and "nothing came back" are different answers, and a
 * button that renders both as a checkmark throws that distinction away.
 */
describe('syncOutcomeMessage', () => {
  const run = (created: number, updated: number, unchanged: number) => ({
    created,
    updated,
    unchanged,
    last_synced_at: '2026-08-31T10:00:00Z',
  })

  it('names both kinds of change', () => {
    expect(syncOutcomeMessage(run(2, 1, 7))).toBe('2 added and 1 updated')
  })

  it('names only the kind that happened', () => {
    expect(syncOutcomeMessage(run(3, 0, 0))).toBe('3 added')
    expect(syncOutcomeMessage(run(0, 4, 0))).toBe('4 updated')
  })

  it('says up to date rather than nothing when a run changed nothing', () => {
    expect(syncOutcomeMessage(run(0, 0, 12))).toBe('Already up to date')
    expect(syncOutcomeMessage(run(0, 0, 0))).toBe('Already up to date')
  })
})

/**
 * What this pins: a failure is visible and, where the server named the fix,
 * says it. The 409s here are the ones a user can act on.
 */
describe('syncFailureMessage', () => {
  const problem = (title: string, detail: string | null) => ({
    code: 'source_disconnected',
    detail,
    status: 409,
    title,
    type: 'about:blank',
  })

  it('joins the server title and its actionable detail', () => {
    const error = new ApiError(409, problem('That source is disconnected', 'Connect it again before syncing.'))
    expect(syncFailureMessage(error)).toBe(
      'That source is disconnected. Connect it again before syncing.',
    )
  })

  it('uses the title alone when there is no detail', () => {
    expect(syncFailureMessage(new ApiError(409, problem('That source is disconnected', null)))).toBe(
      'That source is disconnected',
    )
  })

  it('falls back for a failure that carried no problem body', () => {
    expect(syncFailureMessage(new ApiError(502))).toBe(
      'Sync failed. Check your connection and retry.',
    )
    expect(syncFailureMessage(new TypeError('Failed to fetch'))).toBe(
      'Sync failed. Check your connection and retry.',
    )
  })
})
