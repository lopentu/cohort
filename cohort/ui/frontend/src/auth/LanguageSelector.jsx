import { useTranslation } from 'react-i18next'
import { setLanguage } from '../i18n'

export default function LanguageSelector() {
  const { t, i18n } = useTranslation()
  return <label className="language-selector">
    <span className="sr-only">{t('Interface language')}</span>
    <select value={i18n.resolvedLanguage || i18n.language} onChange={event => setLanguage(event.target.value)} aria-label={t('Interface language')}>
      <option value="en" lang="en">English</option>
      <option value="zh-TW" lang="zh-TW">繁體中文</option>
    </select>
  </label>
}
