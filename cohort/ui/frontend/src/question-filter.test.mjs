import test from 'node:test'
import assert from 'node:assert/strict'
import { hiddenIdsForQuestions } from './graph-model.js'
test('hiding a question also hides its passage and verification cycle', () => {
  const nodes = [['q','question'],['h','claim'],['p','passage'],['w','witness'],['v','verification']].map(([id,type])=>({id,type}))
  const edges = [['addresses','h','q'],['attests','p','h'],['part_of','p','w'],['verifies','v','p']].map(([type,src,dst])=>({type,src,dst}))
  assert.deepEqual([...hiddenIdsForQuestions(nodes,edges,new Set(['q']))].sort(),['h','p','q','v','w'])
})
test('shared evidence stays visible for a displayed question', () => {
  const nodes = [['q','question'],['other','question'],['h','claim'],['p','passage']].map(([id,type])=>({id,type}))
  const edges = [['addresses','h','q'],['addresses','h','other'],['attests','p','h']].map(([type,src,dst])=>({type,src,dst}))
  assert.deepEqual([...hiddenIdsForQuestions(nodes,edges,new Set(['q']))],['q'])
})
