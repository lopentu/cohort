import test from 'node:test'
import assert from 'node:assert/strict'
import { spanVerification, passageCheckIds } from './span-verification.js'
const check = (id, result, extra = {}) => ({ id, payload: { method: 'exact_span', result, span_start: 2, span_end: 8, ...extra } })
test('repeated matching spans produce one verified state', () => {
  assert.equal(spanVerification([check('a', 'pass'), check('b', 'pass')]).verified, true)
})
test('a later failed or incomplete check cannot leave a verified label', () => {
  assert.equal(spanVerification([check('a', 'pass'), check('b', 'fail')]).verified, false)
  assert.equal(spanVerification([check('a', 'pass', { span_start: null })]).verified, false)
  assert.equal(spanVerification([]).verified, false)
})
test('only exact-span audit nodes attached to passages are removed from the drawing', () => {
  const nodes = [{ id: 'p', type: 'passage' }, { id: 'c', type: 'claim' }, check('a', 'pass'), check('b', 'pass')]
  const edges = [{ type: 'verifies', src: 'a', dst: 'p' }, { type: 'verifies', src: 'b', dst: 'c' }]
  assert.deepEqual([...passageCheckIds(nodes, edges)], ['a'])
})
