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
