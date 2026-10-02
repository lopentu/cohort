import React, { Suspense, lazy } from 'react'
import ReactDOM from 'react-dom/client'
import './i18n'
import SessionBoundary from './auth/SessionBoundary'
import { applyTheme, loadTheme } from './Settings'
import './styles.css'
import { tr } from './i18n'

const App = lazy(() => import('./App'))

// Before the first paint, not in an effect: applying a stored theme after
// React mounts would show one frame of the system scheme first, which is a
// visible flash for anyone whose choice differs from their OS.
applyTheme(loadTheme())

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <SessionBoundary>
      <Suspense fallback={<p className="boot" role="status">{tr('Loading…')}</p>}><App /></Suspense>
    </SessionBoundary>
  </React.StrictMode>,
)
