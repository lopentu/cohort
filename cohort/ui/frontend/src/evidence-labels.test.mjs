import test from 'node:test'
import assert from 'node:assert/strict'
import { profileName, textName } from './evidence-labels.js'

test('corpus grouping is explained as material, not a translator', () => {
  assert.equal(profileName('pre-Dhr-other'), 'Other material before Dharmarakṣa (pre-Dhr-other)')
  assert.equal(profileName('ASg'), 'An Shigao 安世高 (ASg)')
  assert.equal(profileName('Dhr'), 'Dharmarakṣa 竺法護 (Dhr)')
  assert.equal(profileName('Dhkṣ'), 'Dharmakṣema 曇無讖 (Dhkṣ)')
})
test('unknown identifiers are preserved without inventing an ascription or title', () => {
  assert.equal(profileName('fixture-class'), 'fixture-class')
  assert.equal(textName('T9999'), 'T9999')
  assert.equal(textName('T0603'), 'Yin chi ru jing 陰持入經 · T0603')
})

test('readable prose preserves source identifiers and expands a mixed group as one label', async () => {
  const { explainProfileCodes } = await import('./evidence-labels.js')
  assert.equal(explainProfileCodes('T1694 X-ASg source:Dhr pre-Dhr-other'),
    'T1694 X-ASg source:Dhr Other material before Dharmarakṣa (pre-Dhr-other)')
})
