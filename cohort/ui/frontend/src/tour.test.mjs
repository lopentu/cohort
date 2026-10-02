import test from 'node:test'
import assert from 'node:assert/strict'
import { tourSteps, rememberTour, hasSeenTour } from './onboarding/tour-state.js'

test('tour includes only enabled tabs in research workflow order', () => {
  assert.deepEqual(tourSteps(['graph', 'corpus', 'findings']).map(s => s.tab), ['corpus', 'graph', 'findings'])
  assert.deepEqual(tourSteps(['graph', 'findings', 'corpus', 'evidence', 'run']).map(s => s.tab), ['corpus', 'evidence', 'run', 'graph', 'findings'])
})

test('tour preference can survive storage being disabled', () => {
  const unavailable = { getItem() { throw new Error('blocked') }, setItem() { throw new Error('blocked') } }
  assert.equal(hasSeenTour(unavailable), false)
  assert.doesNotThrow(() => rememberTour(unavailable))
  const values = new Map()
  const storage = { getItem: k => values.get(k), setItem: (k,v) => values.set(k,v) }
  rememberTour(storage)
  assert.equal(hasSeenTour(storage), true)
})

test('tour survives a blocked localStorage getter', () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('blocked') } })
  try {
    assert.equal(hasSeenTour(), false)
    assert.doesNotThrow(() => rememberTour())
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'localStorage', descriptor)
    else delete globalThis.localStorage
  }
})
