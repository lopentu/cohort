import assert from 'node:assert/strict'
import test from 'node:test'
import { existsSync } from 'node:fs'

test('localization module is available', () => {
  assert.ok(existsSync(new URL('./i18n.js', import.meta.url)))
})
test('language preference, fallback and live translation preserve identifiers', async () => {
  const { default: i18n, resolveLanguage, setLanguage, loadLanguage } = await import('./i18n.js')
  assert.equal(resolveLanguage('fr'), 'en')
  assert.equal(resolveLanguage('zh-TW'), 'zh-TW')
  assert.equal(loadLanguage({ getItem: () => 'zh-TW' }), 'zh-TW')
  assert.equal(loadLanguage({ getItem: () => 'fr' }), 'en')
  assert.equal(loadLanguage({ getItem: () => { throw Error('blocked') } }), 'en')
  await setLanguage('zh-TW')
  assert.equal(i18n.t('Corpus'), '語料')
  assert.equal(i18n.t('T0603'), 'T0603')
  await setLanguage('en')
  assert.equal(i18n.t('Corpus'), 'Corpus')
})
test('every checked-in English message has a nonempty Taiwan translation', async () => {
  const { resources } = await import('./locales.js')
  assert.deepEqual(Object.keys(resources.en.translation).sort(), Object.keys(resources['zh-TW'].translation).sort())
  for (const [key, value] of Object.entries(resources['zh-TW'].translation)) {
    assert.ok(value.trim(), key)
  }
})

test('saved language updates document language and survives switching', async () => {
  const { setLanguage, loadLanguage, LANGUAGE_KEY } = await import('./i18n.js')
  const data = new Map()
  const storage = { getItem: key => data.get(key), setItem: (key, value) => data.set(key, value) }
  const originalDocument = globalThis.document
  globalThis.document = { documentElement: { lang: 'en' } }
  try {
    await setLanguage('zh-TW', storage)
    assert.equal(data.get(LANGUAGE_KEY), 'zh-TW')
    assert.equal(loadLanguage(storage), 'zh-TW')
    assert.equal(document.documentElement.lang, 'zh-TW')
    await setLanguage('unsupported', storage)
    assert.equal(document.documentElement.lang, 'en')
    assert.equal(loadLanguage(storage), 'en')
  } finally { globalThis.document = originalDocument }
})

test('application source messages have translations in both languages', async () => {
  const { readFileSync, readdirSync } = await import('node:fs')
  const { parse } = await import('@babel/parser')
  const { resources } = await import('./locales.js')
  const root = new URL('./', import.meta.url)
  function inspect(node, file) {
    if (!node || typeof node !== 'object') return
    if (node.type === 'CallExpression' && ['t', 'tr'].includes(node.callee?.name) && node.arguments[0]?.type === 'StringLiteral') {
      const key = node.arguments[0].value
      for (const language of ['en', 'zh-TW']) assert.ok(Object.hasOwn(resources[language].translation, key), `${file}: ${language}: ${key}`)
    }
    for (const value of Object.values(node)) {
      if (Array.isArray(value)) value.forEach(child => inspect(child, file))
      else if (value && typeof value === 'object') inspect(value, file)
    }
  }
  const files = readdirSync(root, { recursive: true }).filter(file => /\.(jsx|js)$/.test(file) && file !== 'locales.js')
  for (const file of files) inspect(parse(readFileSync(new URL(file, root), 'utf8'), { sourceType: 'module', plugins: ['jsx'] }), file)
})
