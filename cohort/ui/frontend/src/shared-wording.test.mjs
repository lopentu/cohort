import test from 'node:test'
import assert from 'node:assert/strict'
import { sharedWordingSegments } from './shared-wording.js'
test('uses source code-point offsets on both sides and preserves punctuation', () => {
  const runs = [{ a_start: 101, a_end: 106, b_start: 900, b_end: 905 }]
  const a = sharedWordingSegments('前𠀀甲，乙丙後', 100, runs, 'a')
  assert.deepEqual(a, [{ text: '前', shared: false }, { text: '𠀀甲，乙丙', shared: true }, { text: '後', shared: false }])
  assert.equal(sharedWordingSegments('𠀀甲，乙丙後', 900, runs, 'b')[0].text, '𠀀甲，乙丙')
})
test('merges overlapping runs, clips to excerpt, and leaves unmatched text intact', () => {
  const runs = [{ a_start: 8, a_end: 12 }, { a_start: 11, a_end: 13 }, { a_start: 20, a_end: 24 }]
  assert.deepEqual(sharedWordingSegments('甲乙丙丁', 10, runs, 'a'), [{ text: '甲乙丙', shared: true }, { text: '丁', shared: false }])
  assert.deepEqual(sharedWordingSegments('甲乙', 0, [], 'a'), [{ text: '甲乙', shared: false }])
})
