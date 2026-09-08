import { useEffect, useRef } from 'react'
import { usePresence, useSlidingIndicator } from './motion'

// The settings popover: a gear in the top bar, a floating panel under it.
//
// Theme has three states rather than a two-way switch, because "follow the
// system" is a real answer and not the absence of one — a binary toggle forces
// a choice the reader may not want to make and then ignores their OS changing.
// `system` stamps no attribute and lets `prefers-color-scheme` decide;
// `light`/`dark` stamp `data-theme` on <html> and win over it. See styles.css.
//
// Preferences persist in localStorage, wrapped in try/catch throughout: a
// private window or a browser with site data blocked throws on access, and a
// theme toggle must never be the thing that white-screens the app.

export const THEMES = [
  ['system', 'System'],
  ['light', 'Light'],
  ['dark', 'Dark'],
]

const KEY = 'cohort.theme'

export function loadTheme() {
  try {
    const v = localStorage.getItem(KEY)
    return THEMES.some(([k]) => k === v) ? v : 'light'
  } catch {
    return 'light'
  }
}

export function applyTheme(theme) {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* storage unavailable: the theme still applies for this session */
  }
}

export default function Settings({
  open, onToggle, theme, onTheme, showAudit, onShowAudit,
}) {
  const wrapRef = useRef(null)
  // Held on screen while its exit animation plays, and marked `closing` while
  // it does; `pointer-events: none` in styles.css keeps the fading panel from
  // catching the click that dismissed it.
  const pop = usePresence(open, 150)
  const { trackRef, thumbProps } = useSlidingIndicator(theme, THEMES.length, pop.mounted)

  // Dismiss on outside click and on Escape — the two gestures a popover owes
  // its reader. Bound only while open, so the app is not listening to every
  // click on the page for no reason.
  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) onToggle(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); onToggle(false) }
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey, true)
    }
  }, [open, onToggle])

  return (
    <div className="settings-wrap" ref={wrapRef}>
      <button
        className={`icon-btn ${open ? 'on' : ''}`}
        onClick={() => onToggle(!open)}
        aria-label="Settings"
        aria-expanded={open}
        title="Settings"
      >
        <GearIcon />
      </button>

      {pop.mounted && (
        <div
          className={`settings-pop ${pop.closing ? 'closing' : ''}`}
          role="dialog"
          aria-label="Settings"
        >
          <h3>Appearance</h3>
          <div className="seg" role="radiogroup" aria-label="Theme" ref={trackRef}>
            {/* Same sliding thumb as the tab bar, because styles.css makes the
                two the same control — a segmented picker whose selection
                travels rather than teleports. */}
            <span {...thumbProps} />
            {THEMES.map(([key, label]) => (
              <button
                key={key}
                role="radio"
                aria-checked={theme === key}
                className={`seg-item ${theme === key ? 'on' : ''}`}
                data-seg-on={theme === key}
                onClick={() => onTheme(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="hint small">
            System follows your OS setting and keeps following it.
          </p>

          <h3>Graph</h3>
          <label className="setting-row">
            <input
              type="checkbox"
              checked={showAudit}
              onChange={(e) => onShowAudit(e.target.checked)}
            />
            <span>
              Show audit nodes
              {/* Not hidden because they are unimportant, but because the
                  evidence chain has to stay legible. Saying which nodes these
                  are matters: a reader who thinks the graph is complete would
                  overestimate how checked it is. */}
              <small>Verifications and decisions — bookkeeping, not evidence.</small>
            </span>
          </label>
        </div>
      )}
    </div>
  )
}

function GearIcon() {
  // Built from computed geometry rather than a hand-traced path: the previous
  // version carried a `transform="translate(...) scale(...)"` on the outer
  // shape only, which pushed the ring off the hub — visibly off-centre at
  // 15px. Everything here is concentric on (8,8): hub r=2.25, ring r=4.55,
  // and eight teeth stepping out to r=6.35 at 45° intervals.
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <g
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      >
        <circle cx="8" cy="8" r="2.25" />
        <circle cx="8" cy="8" r="4.55" />
        <path d="M12.55 8.00L14.35 8.00 M11.22 11.22L12.49 12.49 M8.00 12.55L8.00 14.35 M4.78 11.22L3.51 12.49 M3.45 8.00L1.65 8.00 M4.78 4.78L3.51 3.51 M8.00 3.45L8.00 1.65 M11.22 4.78L12.49 3.51" />
      </g>
    </svg>
  )
}
