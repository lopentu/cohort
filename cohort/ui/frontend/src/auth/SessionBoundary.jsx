import { createContext, useContext, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { request, setCsrfToken } from '../request'
import { Button, Field, Notice } from '../components/ui'
import LanguageSelector from './LanguageSelector'

const SessionContext = createContext(null)
export const useSession = () => useContext(SessionContext)

export default function SessionBoundary({ children }) {
  const { t } = useTranslation()
  const [session, setSession] = useState(null)
  const [error, setError] = useState(null)
  const [expired, setExpired] = useState(false)
  const update = data => { setCsrfToken(data.csrf_token); setSession(data); setError(null) }
  const refresh = () => request('/api/auth/session').then(update).catch(error => setError(error.message))
  useEffect(() => {
    let active = true
    request('/api/auth/session').then(data => { if (active) update(data) }).catch(error => { if (active) setError(error.message) })
    const expire = () => { setCsrfToken(null); setExpired(true); setSession({ enabled: true, authenticated: false }) }
    window.addEventListener('cohort:session-expired', expire)
    return () => { active = false; window.removeEventListener('cohort:session-expired', expire) }
  }, [])
  const login = async (username, password) => {
    const data = await request('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }),
    })
    update(data); setExpired(false)
  }
  const logout = async () => {
    try { update(await request('/api/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })) }
    catch (error) {
      // Expiry invalidates CSRF too. Check server state before calling this a
      // failed sign-out, so a quiet tab cannot retain an expired session.
      if (error.code === 'csrf_failed') {
        try {
          const current = await request('/api/auth/session')
          if (!current.authenticated) { update(current); setExpired(true); return }
        } catch { /* Keep the failure visible if session state cannot be read. */ }
      }
      setError(error.message)
    }
  }
  if (!session) return <main className="auth-screen"><h1>COHORT</h1>
    {error ? <><Notice>{t('Could not reach the server. Check the connection and try again.')}</Notice><Button onClick={refresh}>{t('Try again')}</Button></> : <p role="status">{t('Checking session…')}</p>}
  </main>
  if (!session.authenticated) return <LoginForm onLogin={login} expired={expired} />
  return <SessionContext.Provider value={{ ...session, logout }}>
    {error && <Notice className="session-notice error">{t('Could not sign out. Please try again.')}</Notice>}
    {children}
  </SessionContext.Provider>
}

function LoginForm({ onLogin, expired }) {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const submit = async event => {
    event.preventDefault(); setBusy(true); setError(null)
    try { await onLogin(username, password) }
    catch (error) {
      setPassword('')
      setError(error.status === 429 ? 'Too many sign-in attempts. Wait a few minutes and try again.'
        : error.status === 401 ? 'Username or password is incorrect.'
        : 'Could not sign in. Check the connection and try again.')
    } finally { setBusy(false) }
  }
  return <main className="auth-screen">
    <div className="auth-language"><LanguageSelector /></div>
    <section className="auth-content" aria-labelledby="login-title">
      <h1>COHORT</h1><h2 id="login-title">{t('Sign in')}</h2>
      <p className="hint">{t('Sign in to open your research records and corpus tools.')}</p>
      {expired && <Notice kind="hint">{t('Your session expired. Sign in again to continue. Saved research is unchanged.')}</Notice>}
      <form onSubmit={submit} className="auth-form">
        <Field label={t('Username')} name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={event => setUsername(event.target.value)} required maxLength={128} autoFocus />
        <Field label={t('Password')} name="password" type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required maxLength={1024} />
        {error && <Notice>{t(error)}</Notice>}
        <Button type="submit" disabled={busy} aria-busy={busy}>{t(busy ? 'Signing in…' : 'Sign in')}</Button>
      </form>
      <p className="hint small">{t('Account setup and password changes are handled locally by the server owner.')}</p>
    </section>
  </main>
}
