import test from 'node:test'
import assert from 'node:assert/strict'
import { corpusInquiryDraft } from './corpus-inquiry.js'
test('a corpus draft retains the selected reference and search phrase', () => {
  const draft = corpusInquiryDraft({ phrase: '明月', ref: 'source:edition-A#p12', title: 'Example text' })
  assert.match(draft.question, /明月/)
  assert.match(draft.instructions, /source:edition-A#p12/)
  assert.match(draft.instructions, /Example text/)
  assert.equal(draft.sourceRef, 'source:edition-A#p12')
})
test('different results for one phrase produce different starting sources', () => {
  const a = corpusInquiryDraft({ phrase: '明月', ref: 'source:a' })
  const b = corpusInquiryDraft({ phrase: '明月', ref: 'source:b' })
  assert.notEqual(a.instructions, b.instructions)
  assert.equal(corpusInquiryDraft(null), null)
})

test('a related-pair draft carries both exact windows, not just the search target', () => {
  const selected = { uid: 'T0001', start: 400, end: 800, text: '甲乙', source_sha256: 'hash-a' }
  const match = { uid: 'T0002', start: 1200, end: 1600, text: '丙丁', source_sha256: 'hash-b', cosine: 0.81234, longest_shared_run: 0 }
  const draft = corpusInquiryDraft({ kind: 'passage-pair', selected, match })
  for (const text of ['T0001', 'T0002', '400–800', '1200–1600', '甲乙', '丙丁', 'hash-a', 'hash-b', '0.81234']) {
    assert.ok(draft.instructions.includes(text), `missing ${text}`)
  }
  assert.match(draft.question, /same episode or teaching/)
  assert.match(draft.instructions, /resolve citations/)
  const other = corpusInquiryDraft({ kind: 'passage-pair', selected, match: { ...match, start: 2000, end: 2400, text: '戊己' } })
  assert.notEqual(other.instructions, draft.instructions)
  assert.ok(!other.instructions.includes('丙丁'))
})
