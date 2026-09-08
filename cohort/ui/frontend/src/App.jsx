import { passageCheckIds } from './span-verification'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { getGraph, getHealth, getRefusals } from './api'
import DetailPanel from './DetailPanel'
import GraphView, { nodeLegendFor, TYPE_SHAPE } from './GraphView'
import CorpusPanel from './CorpusPanel'
import EvidencePanel from './EvidencePanel'
import FindingsPanel from './FindingsPanel'
import RefusalsPanel from './RefusalsPanel'
import RunPanel, { loadHiddenQuestions, saveHiddenQuestions } from './RunPanel'
import Settings, { applyTheme, loadTheme } from './Settings'
import StatsBar from './StatsBar'
import TabIntro from './TabIntro'
import { EDGE_STYLE, hiddenIdsForQuestions, legendFor } from './graph-model'
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
  // The third top-bar popover. All three are mutually exclusive: two panels
  // hanging off adjacent controls would overlap each other.
  const [introOpen, setIntroOpen] = useState(false)
  const [agentSeed, setAgentSeed] = useState(null)
  const consumeAgentSeed = useCallback(() => setAgentSeed(null), [])
  // Which questions are hidden from the Graph tab. A view preference, not a
  // graph write — see RunPanel.jsx's `loadHiddenQuestions` for why.
  const [hiddenQuestions, setHiddenQuestions] = useState(loadHiddenQuestions)

  const reload = useCallback(() => {
    Promise.all([getGraph(), getHealth()])
      .then(([g, h]) => {
        // Preserve the data reference when polling finds no new records:
        // GraphView otherwise rebuilds the network and loses its layout.
        setData((previous) => JSON.stringify(previous) === JSON.stringify(g) ? previous : g)
        setHealth(h)
      })
      .catch((e) => setError(e.message))
    // A missing log is a legitimate state, not an error, so a failure here
    // must not blank the whole view.
    getRefusals().then(setRefusals).catch(() => setRefusals(null))
  }, [])

  useEffect(() => { applyTheme(theme) }, [theme])
  useEffect(() => { saveHiddenQuestions(hiddenQuestions) }, [hiddenQuestions])

  const toggleHiddenQuestion = useCallback((id) => {
    setHiddenQuestions((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  // The stats popover hangs off a control that only the Graph tab shows, so
  // leaving it open while switching away would strand it.
  useEffect(() => { if (tab !== 'graph') setStatsOpen(false) }, [tab])

  // The help panel describes the tab you are on, so a tab change makes its
  // open contents wrong. Closed rather than swapped: silently replacing the
  // text under a reader's eyes is worse than making them ask again.
  useEffect(() => { setIntroOpen(false) }, [tab])

  useEffect(() => {
    // Inquiry unmounts on tab changes, but its server-side run keeps writing.
    // Refresh here rather than depending on Inquiry to announce completion.
    reload()
    if (tab !== 'graph') return undefined
    const timer = setInterval(reload, 4000)
    return () => clearInterval(timer)
  }, [tab, reload])

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

  // What the Graph tab and its legend actually draw: `data` minus whatever a
  // hidden question pulled down with it. Memoized on [data, hiddenQuestions]
  // specifically, not recomputed on every render — GraphView reloads its
  // vis-network DataSet (clearing and re-adding every node, which resets
  // physics and scatters every node back to its unstabilized starting
  // position) whenever this object's *reference* changes, and a plain
  // computation in the render body produces a new object on every render,
  // including one triggered by clicking a node (which only changes
  // `selectedId` and has nothing to do with what the graph should show).
  const graphData = useMemo(() => {
    if (!data) return data
    const hiddenIds = hiddenIdsForQuestions(data.nodes, data.edges, hiddenQuestions)
    for (const id of passageCheckIds(data.nodes, data.edges)) hiddenIds.add(id)
    if (!hiddenIds.size) return data
    return {
      ...data,
      nodes: data.nodes.filter((n) => !hiddenIds.has(n.id)),
      edges: data.edges.filter((e) => !hiddenIds.has(e.src) && !hiddenIds.has(e.dst)),
    }
  }, [data, hiddenQuestions])

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
            onToggle={(v) => {
              setStatsOpen(v)
              if (v) { setSettingsOpen(false); setIntroOpen(false) }
            }}
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
          <TabIntro
            tab={tab}
            open={introOpen}
            onToggle={(v) => {
              setIntroOpen(v)
              if (v) { setSettingsOpen(false); setStatsOpen(false) }
            }}
          />
          <Settings
            open={settingsOpen}
            onToggle={(v) => {
              setSettingsOpen(v)
              if (v) { setStatsOpen(false); setIntroOpen(false) }
            }}
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
                <Legend data={graphData} showAudit={showAudit} />
                <GraphView
                  data={graphData}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  showAudit={showAudit}
                />
                {refusalsShown.mounted && (
                  <RefusalsPanel refusals={refusals} closing={refusalsShown.closing} />
                )}
              </>
            )}
            {tab === 'findings' && (
              <FindingsPanel
                onSelect={(id) => { setSelectedId(id); goTab('graph') }}
              />
            )}
            {tab === 'corpus' && (
              <CorpusPanel
                onCite={(source) => { setAgentSeed(source); goTab('run') }}
              />
            )}
            {tab === 'evidence' && <EvidencePanel />}
            {tab === 'run' && (
              <RunPanel
                instructionSeed={agentSeed}
                onSeedConsumed={consumeAgentSeed}
                onGraphChanged={reload}
                hiddenQuestions={hiddenQuestions}
                onToggleHiddenQuestion={toggleHiddenQuestion}
              />
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
  // node key explains the fill colours. A hypothesis (claim or conjecture,
  // drawn as a diamond either way) reads grey/blue/yellow/green/red for
  // proposed / attested / contradicted / accepted / rejected; a source text is
  // black, a passage and a query blue. Contradicted overrides whatever status
  // the node itself carries — see GraphView.jsx `nodeColorKey`.
  const { edges } = legendFor(data.nodes, data.edges, { showAudit })
  // The node key for *this* graph, not the whole vocabulary — ten colours
  // listed against a graph that draws four is a legend the reader has to
  // filter by hand, and one offering "survived its control" where no control
  // was run describes a different study.
  const nodeKey = nodeLegendFor(data.nodes, showAudit)

  return (
    <div className="legend" aria-label="Graph key">
      <strong className="legend-title">Graph key</strong>
      {edges.map((e) => (
        <span className="li" key={e.key}>
          <i className={`swatch ${e.klass}`} /> {emphasise(e.text, e.strong)}
        </span>
      ))}
      {!!edges.length && !!nodeKey.length && <span className="sep" />}
      {nodeKey.map((n) => (
        <span className="li" key={n.key}>
          <NodeKeyShape shape={n.types ? TYPE_SHAPE[n.types[0]] : 'diamond'} color={n.color} /> {n.key}
        </span>
      ))}
      <details className="legend-explainer">
        <summary>What do these links mean?</summary>
        <dl>
          <dt><i className="swatch e-attests" /> Attests</dt>
          <dd>A passage supports a claim or conjecture. For example, a quoted passage is evidence for a claim about its wording. The link records support; it does not prove the claim.</dd>
          <dt><i className="swatch e-addresses" /> Addresses</dt>
          <dd>A claim or conjecture responds to a research question. It tells you which question the proposal concerns, not whether the proposal answers it successfully.</dd>
          <dt>Claim / conjecture</dt>
          <dd>Both appear under “Hypotheses.” A claim states what the sources support; a conjecture proposes an explanation to test. A hypothesis is not a collection of claims.</dd>
          <dt>Other links</dt>
          <dd>Tests connects a query to a conjecture. Parallel and descent links mark related sources whose support may not be independent.</dd>
        </dl>
        <a href="/assets/graph-guide.html" target="_blank" rel="noopener noreferrer">Open the illustrated graph guide</a>
      </details>
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

function NodeKeyShape({ shape, color }) {
  const common = { fill: color, stroke: 'currentColor', strokeWidth: 0.7 }
  return (
    <svg className="node-key-shape" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" data-shape={shape}>
      {shape === 'star' ? <polygon points="10,1 12.8,6.5 19,7.5 14.5,12 15.5,18.5 10,15.5 4.5,18.5 5.5,12 1,7.5 7.2,6.5" {...common} />
        : shape === 'diamond' ? <polygon points="10,1 19,10 10,19 1,10" {...common} />
          : shape === 'ellipse' ? <ellipse cx="10" cy="10" rx="9" ry="5.5" {...common} />
            : shape === 'box' ? <rect x="1" y="4" width="18" height="12" rx="2" {...common} />
              : shape === 'square' ? <rect x="3" y="3" width="14" height="14" {...common} />
                : <circle cx="10" cy="10" r="6" {...common} />}
    </svg>
  )
}
