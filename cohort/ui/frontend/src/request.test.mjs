import test from 'node:test'
import assert from 'node:assert/strict'
import { request, setCsrfToken } from './request.js'

test('state-changing requests send the active session CSRF token', async () => {
  setCsrfToken('session-token')
  let received
  await request('/api/accept', { method: 'POST', body: '{}' }, async (_url, options) => {
    received = options
    return { ok: true, json: async () => ({ ok: true }) }
  })
  assert.equal(received.headers['X-CSRF-Token'], 'session-token')
  assert.equal(received.credentials, 'same-origin')
})

test('expired sessions signal login and preserve the failure status', async () => {
  const events = []
  const original = globalThis.window
  globalThis.window = { dispatchEvent: event => events.push(event.type) }
  try {
    await assert.rejects(request('/api/graph', {}, async () => ({
      ok: false, status: 401, json: async () => ({ detail: { code: 'authentication_required', message: 'Sign in again.' } }),
    })), error => error.status === 401 && error.code === 'authentication_required')
    assert.deepEqual(events, ['cohort:session-expired'])
  } finally { globalThis.window = original }
})

test('readonly requests do not send CSRF and graph refusal codes survive', async () => {
  setCsrfToken('token')
  let received
  await assert.rejects(request('/api/graph', {}, async (_url, options) => {
    received = options
    return { ok: false, status: 403, json: async () => ({ detail: { rule: 'source_required', message: 'Missing source.' } }) }
  }), error => error.rule === 'source_required' && error.message === 'source_required: Missing source.')
  assert.equal(received.headers['X-CSRF-Token'], undefined)
})
