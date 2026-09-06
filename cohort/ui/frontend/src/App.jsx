import { useCallback, useEffect, useState } from 'react'
import { getGraph, getHealth, getRefusals } from './api'
import DetailPanel from './DetailPanel'
import GraphView, { NODE_LEGEND } from './GraphView'
import CorpusPanel from './CorpusPanel'
import EvidencePanel from './EvidencePanel'
import FindingsPanel from './FindingsPanel'
import RefusalsPanel from './RefusalsPanel'
import RunPanel from './RunPanel'
import Settings, { applyTheme, loadTheme } from './Settings'
import StatsBar from './StatsBar'
import TabIntro from './TabIntro'
import { EDGE_STYLE, legendFor } from './graph-model'
import { usePresence, useSlidingIndicator } from './motion'

export default function App() {
  const [data, setData] = useState(null)
  const [health, setHealth] = useState(null)
  const [refusals, setRefusals] = useState(null)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [showAudit, setShowAudit] = useState(false)
  const [showRefusals, setShowRefusals] = useState(false)
  const [tab, setTab] = useState('graph')
  // Which way the last tab change travelled, so the incoming panel slides in
  // from the side the reader came from rather than always from the same edge.
  const [tabDir, setTabDir] = useState('none')
  const [theme, setTheme] = useState(loadTheme)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [statsOpen, setStatsOpen] = useState(false)
  const [agentSeed, setAgentSeed] = useState(null)

  const reload = useCallback(() => {
    Promise.all([getGraph(), getHealth()])
      .then(([g, h]) => { setData(g); setHealth(h) })
      .catch((e) => setError(e.message))
    // A missing log is a legitimate state, not an error, so a failure here
    // must not blank the whole view.
    getRefusals().then(setRefusals).catch(() => setRefusals(null))
  }, [])

  useEffect(() => { applyTheme(theme) }, [theme])

  // The stats popover hangs off a control that only the Graph tab shows, so
  // leaving it open while switching away would strand it.
  useEffect(() => { if (tab !== 'graph') setStatsOpen(false) }, [tab])

  useEffect(reload, [reload])

  // The refused-writes panel is toggled, so it needs an exit as much as an
  // entrance; without one it disappears on a frame while everything else on
  // the tab moves.
  const refusalsShown = usePresence(showRefusals && tab === 'graph', 200)

  // The tab list, and the thumb that tracks it. Both live above the early
  // returns below: hooks must run on every render, and the list has to be a
  // value rather than inline JSX so a click can tell which way it is moving.
  const tabs = [
    ['graph', 'Graph'],
    ['findings', 'Findings'],
    health?.corpus_enabled && ['corpus', 'Corpus'],
    health?.evidence_enabled && ['evidence', 'Evidence'],
    health?.runs_enabled && ['run', 'Inquiry'],
  ].filter(Boolean)

  const { trackRef: tabTrackRef, thumbProps: tabThumbProps } =
    useSlidingIndicator(tab, tabs.length, !!data)

  const goTab = (key) => {
    if (key === tab) return
    const from = tabs.findIndex(([k]) => k === tab)
    const to = tabs.findIndex(([k]) => k === key)
    setTabDir(to > from ? 'next' : 'prev')
    setTab(key)
  }

  // Escape dismisses the floating inspector — the ordinary gesture for a panel
  // that overlays content rather than sitting beside it.
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setSelectedId(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (error) {
    return (
      <div className="boot error">
        <h1>COHORT</h1>
        <p>{error}</p>
        <p className="hint">
          Seed a graph with <code>scripts/seed_demo_graph.py</code>, then serve it
          with <code>scripts/serve_ui.py</code>.
        </p>
      </div>
    )
  }
  if (!data) return <div className="boot"><h1>COHORT</h1><p className="hint">Loading…</p></div>

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>COHORT</h1>
          <span className="tag">beta</span>
        </div>
        <div className={`graph-controls ${tab === 'graph' ? '' : 'off'}`}>
          {/* Refusals are an output of this system, not a debug view
              (docs/design.md §15), so the count is always on screen while the
              graph is — a zero is itself a fact worth showing. */}
          <button
            className={`refusal-tab ${showRefusals ? 'on' : ''}`}
            onClick={() => setShowRefusals((v) => !v)}
            disabled={!refusals?.available}
            title={
              refusals?.available
                ? 'Writes this graph refused, and which rule refused them'
                : 'No event log beside this projection, so refusals cannot be read'
            }
          >
            refused writes
            <span className="refusal-count">
              {refusals?.available ? refusals.total : '—'}
            </span>
          </button>
          <StatsBar
            health={health}
            open={statsOpen}
            onToggle={(v) => { setStatsOpen(v); if (v) setSettingsOpen(false) }}
          />
        </div>
        <nav className="tabs" ref={tabTrackRef}>
          {/* One raised surface that slides between segments, rather than a
              background switching off here and on there: the tab bar is a
              macOS segmented control (styles.css), and that control moves. */}
          <span {...tabThumbProps} />
          {tabs.map(([key, label]) => (
            <button
              key={key}
              className={`tab ${tab === key ? 'on' : ''}`}
              data-seg-on={tab === key}
              onClick={() => goTab(key)}
            >{label}</button>
          ))}
        </nav>

        <div className="topbar-controls">
          <Settings
            open={settingsOpen}
            onToggle={(v) => { setSettingsOpen(v); if (v) setStatsOpen(false) }}
            theme={theme}
            onTheme={setTheme}
            showAudit={showAudit}
            onShowAudit={setShowAudit}
          />
        </div>
      </header>

      {data.truncated && (
        <div className="banner">
          This view is truncated — some nodes are not shown, so the support
          visible here is not the whole graph.
        </div>
      )}

      <div className="body">
        <main>
          {/* One keyed panel per tab. The key is what restarts the entrance
              animation on every change, and `data-dir` sends the panel in from
              the side the reader came from, so the movement agrees with the
              thumb sliding in the tab bar above. The panel — not `main` — is
              the scroller, so the graph and the refusals list share one
              scrollable column exactly as they did when `main` held them. */}
          <div className="tab-panel" key={tab} data-dir={tabDir}>
            {tab === 'graph' && (
              <>
                <TabIntro tab="graph" />
                <Legend data={data} showAudit={showAudit} />
                <GraphView
                  data={data}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  showAudit={showAudit}
                />
                {refusalsShown.mounted && (
                  <RefusalsPanel refusals={refusals} closing={refusalsShown.closing} />
                )}
              </>
            )}
            {tab === 'findings' && <TabIntro tab="findings" />}
            {tab === 'findings' && (
              <FindingsPanel
                onSelect={(id) => { setSelectedId(id); goTab('graph') }}
              />
            )}
            {tab === 'corpus' && <TabIntro tab="corpus" />}
            {tab === 'corpus' && (
              <CorpusPanel
                onCite={(phrase) => { setAgentSeed(phrase); goTab('run') }}
              />
            )}
            {tab === 'evidence' && <TabIntro tab="evidence" />}
            {tab === 'evidence' && <EvidencePanel />}
            {tab === 'run' && <TabIntro tab="run" />}
            {tab === 'run' && (
              <RunPanel instructionSeed={agentSeed} onGraphChanged={reload} />
            )}
          </div>
        </main>
        {/* Floating inspector, and only over the graph: it is the graph's
            detail view, so overlaying the corpus or run panels with it would
            cover unrelated content. */}
        {tab === 'graph' && (
          <DetailPanel
            nodeId={selectedId}
            onSelect={setSelectedId}
            onClose={() => setSelectedId(null)}
            canWrite={!!health?.writes_enabled}
            onChanged={reload}
          />
        )}
      </div>
    </div>
  )
}

function Legend({ data, showAudit }) {
  // Edge key describes *this* graph (`legendFor` keeps only drawn edges); the
  // node key explains the fill colours, which now carry meaning rather than
  // status: a claim reads green/yellow/red for supported / insufficient /
  // contradicted, a source text is black, a passage and a query blue. A dashed
  // outline still marks a proposed (unchecked) node on the canvas.
  const { edges } = legendFor(data.nodes, data.edges, { showAudit })

  return (
    <div className="legend">
      {edges.map((e) => (
        <span className="li" key={e.key}>
          <i className={`swatch ${e.klass}`} /> {emphasise(e.text, e.strong)}
        </span>
      ))}
      {!!edges.length && <span className="sep" />}
      {NODE_LEGEND.map((n) => (
        <span className="li" key={n.key}>
          <i className="dot" style={{ background: n.color }} /> {n.key}
        </span>
      ))}
    </div>
  )
}

//: bolds one word inside a legend line without putting markup in the data.
function emphasise(text, word) {
  if (!word) return text
  const at = text.indexOf(word)
  if (at < 0) return text
  return (
    <>
      {text.slice(0, at)}<b>{word}</b>{text.slice(at + word.length)}
    </>
  )
}
