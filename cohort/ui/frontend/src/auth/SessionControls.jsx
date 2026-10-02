import { useTranslation } from 'react-i18next'
import { useSession } from './SessionBoundary'
import LanguageSelector from './LanguageSelector'
import { Button } from '../components/ui'

export default function SessionControls() {
  const { t } = useTranslation()
  const session = useSession()
  return <div className="session-controls">
    <LanguageSelector />
    {session?.enabled && <Button className="btn tiny" onClick={session.logout} title={session.username}>{t('Sign out')}</Button>}
  </div>
}
