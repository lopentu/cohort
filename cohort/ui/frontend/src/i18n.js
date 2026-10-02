import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'
import { resources } from './locales.js'

export const SUPPORTED_LANGUAGES = ['en', 'zh-TW']
export const LANGUAGE_KEY = 'cohort.language'
export function resolveLanguage(language) {
  return SUPPORTED_LANGUAGES.includes(language) ? language : 'en'
}
export function loadLanguage(storage) {
  try { return resolveLanguage((storage ?? (typeof window !== 'undefined' ? window.localStorage : undefined))?.getItem(LANGUAGE_KEY)) }
  catch { return 'en' }
}
const i18n = i18next.createInstance()
i18n.use(initReactI18next).init({
  resources, lng: loadLanguage(), fallbackLng: 'en', supportedLngs: SUPPORTED_LANGUAGES,
  keySeparator: false, nsSeparator: false, initImmediate: false,
  interpolation: { escapeValue: false },
})
i18n.on('languageChanged', language => {
  if (typeof document !== 'undefined') document.documentElement.lang = resolveLanguage(language)
})
if (typeof document !== 'undefined') document.documentElement.lang = resolveLanguage(i18n.language)
export function setLanguage(language, storage) {
  const resolved = resolveLanguage(language)
  try { (storage ?? (typeof window !== 'undefined' ? window.localStorage : undefined))?.setItem(LANGUAGE_KEY, resolved) } catch { /* blocked storage keeps this session usable */ }
  return i18n.changeLanguage(resolved)
}
export function tr(message, options) { return i18n.t(message, options) }
export function formatNumber(number, options) { return new Intl.NumberFormat(i18n.language, options).format(number) }
export function formatDate(value, options) { return new Intl.DateTimeFormat(i18n.language, options).format(new Date(value)) }
export default i18n

// Translate finite display labels; retain unrecognized diagnostics verbatim.
export function metadataLabel(message) {
  const floor = /^dropped: under the ([\d,]+)-character floor$/.exec(message)
  if (floor) return tr('Dropped: under the {{count}}-character floor', { count: floor[1] })
  const small = /^dropped: class too small to profile \((.*), (\d+) units\)$/.exec(message)
  if (small) return tr('Dropped: class too small to profile ({{group}}, {{count}} units)', { group: small[1], count: small[2] })
  return tr(message)
}

export function explorationLabel(message) {
  const candidate = /^Returned by the similarity search for (.*); not necessarily inspected\.$/.exec(message)
  if (candidate) return tr('Returned by the similarity search for {{text}}; not necessarily inspected.', { text: candidate[1] })
  const pair = /^Compare shared wording in (.*) and (.*)\.$/.exec(message)
  if (pair) return tr('Compare shared wording in {{first}} and {{second}}.', { first: pair[1], second: pair[2] })
  const match = /^Longest returned match: (\d+) characters \(minimum (\d+)\)\.$/.exec(message)
  if (match) return tr('Longest returned match: {{count}} characters (minimum {{minimum}}).', { count: match[1], minimum: match[2] })
  const excluded = /^Compare vocabulary profiles; exclude (.*)\.$/.exec(message)
  if (excluded) return tr('Compare vocabulary profiles; exclude {{texts}}.', { texts: excluded[1] })
  return tr(message)
}
