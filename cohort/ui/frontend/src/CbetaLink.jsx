import { useTranslation } from 'react-i18next'
import { tr } from './i18n'
export default function CbetaLink({ url }) {
  useTranslation()
  if (!url) return null
  return <a className="cbeta-link" href={url} target="_blank" rel="noreferrer noopener"
    title={tr("Open the online text; local character positions do not map to this page")}>{tr("CBETA ↗")}</a>
}
