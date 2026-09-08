import { useEffect, useRef } from 'react'
import { usePresence } from './motion'

// The node/edge counts, collapsed behind a disclosure.
//
// Expanded, this was seven or eight separate figures competing with the tab bar
// for the same row, and it wrapped to a second line as soon as the window
// narrowed. Collapsed it shows the two totals a reader actually tracks — how
// big is this graph, and did that run add anything — with the per-type
// breakdown one click away.
//
// The order is the evidence chain (witness → passage → claim → conjecture),
// not alphabetical and not by count: the columns of the graph read in that
// order, and a panel that sorted by size would put whichever type happens to
// be numerous first and break the correspondence.

const TYPE_ORDER = [
  'witness', 'passage', 'claim', 'conjecture', 'query', 'verification', 'decision',
]

export default function StatsBar({ health, open, onToggle }) {
  const wrapRef = useRef(null)
  // Kept mounted through its exit animation — see Settings for the pattern.
  const pop = usePresence(open, 150)

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

  if (!health) return null

  const counts = health.nodes || {}
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const ordered = [
    ...TYPE_ORDER.filter((t) => counts[t]).map((t) => [t, counts[t]]),
    // anything the vocabulary gains later still shows up rather than vanishing
    ...Object.entries(counts).filter(([t]) => !TYPE_ORDER.includes(t)),
  ]

  return (
    <div className="stats-wrap" ref={wrapRef}>
      <button
        className={`stats-btn ${open ? 'on' : ''}`}
        onClick={() => onToggle(!open)}
        aria-expanded={open}
        title="Node and edge counts"
      >
        <span><strong>{total}</strong> nodes</span>
        <span className="stats-sep" />
        <span><strong>{health.edges}</strong> edges</span>
        <Chevron open={open} />
      </button>

      {pop.mounted && (
        <div
          className={`stats-pop ${pop.closing ? 'closing' : ''}`}
          role="dialog"
          aria-label="Graph contents"
        >
          <h3>Graph contents</h3>
          <ul className="stats-list">
            {ordered.map(([type, n]) => (
              <li key={type}>
                <i className={`stats-dot t-${type}`} />
                <span className="stats-type">{type}</span>
                <span className="stats-n">{n}</span>
              </li>
            ))}
          </ul>
          <div className="stats-foot">
            <span>edges</span><span className="stats-n">{health.edges}</span>
          </div>
          <p className="hint small">
            Counts include audit records. Repeated passage checks are grouped in the inspector.
          </p>
        </div>
      )}
    </div>
  )
}

function Chevron({ open }) {
  return (
    <svg
      className={`chevron ${open ? 'on' : ''}`}
      width="9" height="9" viewBox="0 0 10 10" fill="none" aria-hidden="true"
    >
      <path
        d="M2 3.6 L5 6.6 L8 3.6"
        stroke="currentColor" strokeWidth="1.4"
        strokeLinecap="round" strokeLinejoin="round"
      />
    </svg>
  )
}
