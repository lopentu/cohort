// Display names only: preserve the catalogue codes in API requests and URLs.
// These demo text titles are catalogue metadata, not inferred ascriptions.
const PROFILES = {
  ASg: 'An Shigao 安世高',
  Dhr: 'Dharmarakṣa 竺法護',
  'Dhkṣ': 'Dharmakṣema 曇無讖',
  ZFn: 'Zhu Fonian 竺佛念',
  ZQ: 'Zhi Qian 支謙',
  'pre-Dhr-other': 'Other material before Dharmarakṣa',
  grey: 'Translator uncertain in this catalogue',
}
const TEXTS = {
  T0603: 'Yin chi ru jing 陰持入經',
  T1694: 'Commentary on the Yin chi ru jing 陰持入經註',
  T0453: 'Maitreya’s descent 彌勒下生經',
  T0125: 'Ekottarikāgama 增壹阿含經',
}
export function profileName(code) {
  return PROFILES[code] ? `${PROFILES[code]} (${code})` : code
}
export function textName(uid) {
  return TEXTS[uid] ? `${TEXTS[uid]} · ${uid}` : uid
}

export function explainProfileCodes(text) {
  // Longest first prevents Dhr inside pre-Dhr-other being expanded separately.
  return text.replace(/(?<![\p{L}\p{N}_:/#-])(?:pre-Dhr-other|Dhkṣ|ASg|Dhr|ZFn|ZQ)(?![\p{L}\p{N}_:/#-])/gu, profileName)
}
