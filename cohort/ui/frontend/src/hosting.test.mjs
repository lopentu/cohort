import test from 'node:test'
import assert from 'node:assert/strict'
import { applicationPath, request } from './request.js'

test('API and help URLs stay beneath the application prefix', () => {
  assert.equal(applicationPath('/api/graph?limit=5', 'https://example.org/cohort/#view=graph'), '/cohort/api/graph?limit=5')
  assert.equal(applicationPath('/assets/ui-guide.html#corpus', 'https://example.org/cohort/'), '/cohort/assets/ui-guide.html#corpus')
  assert.equal(applicationPath('/api/auth/login', 'http://localhost:8000/'), '/api/auth/login')
})

test('real request forwarding uses the deployed prefix', async () => {
  const original = globalThis.document
  globalThis.document = { baseURI: 'https://example.org/cohort/' }
  try {
    let received
    await request('/api/auth/session', {}, async url => {
      received = url
      return { ok: true, json: async () => ({ authenticated: false }) }
    })
    assert.equal(received, '/cohort/api/auth/session')
  } finally { globalThis.document = original }
})

test('the shared helper refuses external or parent-path requests', () => {
  for (const path of ['https://evil.example/', '//evil.example/', '/api/../../elsewhere', '/../elsewhere']) {
    assert.throws(() => applicationPath(path, 'https://example.org/cohort/'))
  }
})
