import { Button, Popover } from './components/ui'
import { useTranslation } from 'react-i18next'
import { tr } from './i18n'

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
  useTranslation()



  if (!health) return null

  const counts = health.nodes || {}
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const ordered = [
    ...TYPE_ORDER.filter((t) => counts[t]).map((t) => [t, counts[t]]),
    // anything the vocabulary gains later still shows up rather than vanishing
    ...Object.entries(counts).filter(([t]) => !TYPE_ORDER.includes(t)),
  ]

  return (
    <Popover open={open} onOpenChange={onToggle} label={tr("Graph contents")} className="stats-pop" trigger={
      <Button
        className={`stats-btn ${open ? 'on' : ''}`}
        aria-expanded={open}
        title={tr("Node and edge counts")}
      >
        <span><strong>{total}</strong> {tr("nodes")}</span>
        <span className="stats-sep" />
        <span><strong>{health.edges}</strong> {tr("edges")}</span>
        <Chevron open={open} />
      </Button>
    }>
          <h3>{tr("Graph contents")}</h3>
          <ul className="stats-list">
            {ordered.map(([type, n]) => (
              <li key={type}>
                <i className={`stats-dot t-${type}`} />
                <span className="stats-type">{tr(type)}</span>
                <span className="stats-n">{n}</span>
              </li>
            ))}
          </ul>
          <div className="stats-foot">
            <span>{tr("edges")}</span><span className="stats-n">{health.edges}</span>
          </div>
          <p className="hint small">{tr("Counts include audit records. Repeated passage checks are grouped in the inspector.")}</p>

    </Popover>
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
