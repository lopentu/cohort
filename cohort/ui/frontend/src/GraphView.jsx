import { useEffect, useRef } from 'react'
import { DataSet, Network } from 'vis-network/standalone'
import { EDGE_STYLE, isVisible, nodeTitle } from './graph-model'

// A draggable force-directed rendering of the evidence graph. It replaces the
// fixed witness→passage→claim column layout with a physics graph whose nodes can
// be dragged, while preserving the epistemics docs/design.md §10 requires and
// tests/test_ui_theme.py guards (in the stylesheet, still, for the legend + a
// fallback): node status is a visual channel (the border — dashed/heavier/red),
// and parallel_of / descends_from are drawn distinct from attests (heavier,
// dashed) because they *discount* support. Node clicks open the same DetailPanel
// inspector; edges carry a hover tooltip.

// vis renders to <canvas>, so the CSS classes cannot style it — the palette is
// read from the same CSS custom properties the sheet uses, so a theme switch is
// picked up on the next rebuild.
function palette() {
  const cs = getComputedStyle(document.documentElement)
  const v = (name, fallback) => cs.getPropertyValue(name).trim() || fallback
  return {
    surface: v('--bg-raised', '#1f1f22'),
    selected: v('--node-fill-selected', '#22303f'),
    text: v('--text', '#f5f5f7'),
    textDim: v('--text-dim', '#a1a1a8'),
    supports: v('--supports', '#0a84ff'),
    discounts: v('--discounts', '#ff9f0a'),
    contradicts: v('--contradicts', '#ff453a'),
    structural: v('--structural', '#48484e'),
    tests: v('--tests', '#bf5af2'),
    addresses: v('--addresses', '#5ac8f5'),
    proposed: v('--proposed', '#8e8e96'),
    attested: v('--attested', '#0a84ff'),
    accepted: v('--accepted', '#30d158'),
    rejected: v('--rejected', '#ff453a'),
  }
}

const TYPE_SHAPE = {
  witness: 'ellipse', passage: 'box', claim: 'box', conjecture: 'diamond',
  query: 'dot', question: 'star', verification: 'square', decision: 'square',
}

// Node colour carries MEANING, not just status, so the types stop reading alike:
//   * a claim/conjecture is GREEN only when >=2 independent witnesses corroborate
//     it, YELLOW when nothing attests it / it is single-sourced / its witnesses
//     collapse to one via shared descent, RED when it is contradicted or
//     rejected — computed here from the edges;
//   * a source text (CBETA witness) is BLACK, an agent query BLUE;
//   * passages, research questions and audit nodes get their own steady colours.
// Type shape stays a second channel; status rides the border (dashed = proposed
// / unchecked, heavier = accepted).
const NODE_BORDER = '#8a8a8f'
const INK_LIGHT = '#f7f7fa'
const INK_DARK = '#0b0b0c'
const NODE_COLORS = {
  witness:      { fill: '#141416', text: INK_LIGHT },
  passage:      { fill: '#0a84ff', text: INK_LIGHT },   // located evidence, blue like the query
  query:        { fill: '#0a84ff', text: INK_LIGHT },
  question:     { fill: '#5e5ce6', text: INK_LIGHT },
  audit:        { fill: '#8e8e93', text: INK_LIGHT },   // verification / decision
  supported:    { fill: '#34c759', text: INK_DARK },
  insufficient: { fill: '#ffd60a', text: INK_DARK },
  against:      { fill: '#ff453a', text: INK_LIGHT },
}

// The node-colour key, for the legend.
export const NODE_LEGEND = [
  { key: 'claim — supported', color: NODE_COLORS.supported.fill },
  { key: 'claim — insufficient evidence', color: NODE_COLORS.insufficient.fill },
  { key: 'claim — contradicted', color: NODE_COLORS.against.fill },
  { key: 'source text', color: NODE_COLORS.witness.fill },
  { key: 'passage', color: NODE_COLORS.passage.fill },
  { key: 'query', color: NODE_COLORS.query.fill },
  { key: 'question', color: NODE_COLORS.question.fill },
]

// A claim/conjecture's verdict from the graph edges: contradicted or rejected ->
// 'against'; nothing attests it (or only shared-descent witnesses do) ->
// 'insufficient'; independently attested -> 'supported'.
function claimVerdicts(nodes, edges) {
  const attesters = new Map()
  const witnessOf = new Map()
  const discountPairs = []
  const contradicted = new Set()
  for (const e of edges) {
    if (e.type === 'attests') {
      const a = attesters.get(e.dst) || []
      a.push(e.src)
      attesters.set(e.dst, a)
    } else if (e.type === 'part_of') {
      witnessOf.set(e.src, e.dst)
    } else if (e.type === 'parallel_of' || e.type === 'descends_from') {
      discountPairs.push([e.src, e.dst])
    } else if (e.type === 'contradicts') {
      contradicted.add(e.src)
      contradicted.add(e.dst)
    }
  }
  const verdict = new Map()
  for (const n of nodes) {
    if (n.type !== 'claim' && n.type !== 'conjecture') continue
    if (n.status === 'rejected' || contradicted.has(n.id)) {
      verdict.set(n.id, 'against')
      continue
    }
    const passages = attesters.get(n.id) || []
    const witnesses = new Set(passages.map((p) => witnessOf.get(p)).filter(Boolean))
    // Green needs corroboration: at least two DISTINCT witnesses not themselves
    // linked by a discounting edge. Nothing attesting, a single source, or
    // witnesses that collapse to one via shared descent all read insufficient.
    if (witnesses.size < 2) {
      verdict.set(n.id, 'insufficient')
      continue
    }
    const pset = new Set(passages)
    const nonIndependent = discountPairs.some(
      ([a, b]) => (witnesses.has(a) && witnesses.has(b)) || (pset.has(a) && pset.has(b)),
    )
    verdict.set(n.id, nonIndependent ? 'insufficient' : 'supported')
  }
  return verdict
}

function nodeColorKey(node, verdicts) {
  switch (node.type) {
    case 'witness': return 'witness'
    case 'passage': return 'passage'
    case 'query': return 'query'
    case 'question': return 'question'
    case 'verification':
    case 'decision': return 'audit'
    case 'claim':
    case 'conjecture': return verdicts.get(node.id) || 'insufficient'
    default: return 'audit'
  }
}

// edge type -> colour / weight / dash, mirroring EDGE_STYLE + styles.css.
function edgeStyle(type, p) {
  switch (type) {
    case 'attests': return { color: p.supports, width: 1.8 }
    case 'tests': return { color: p.tests, width: 1.6, dashes: [2, 3] }
    case 'addresses': return { color: p.addresses, width: 1.8 }
    case 'contradicts': return { color: p.contradicts, width: 2.8 }
    case 'parallel_of':
    case 'descends_from': return { color: p.discounts, width: 2.8, dashes: [7, 4] }
    default: return { color: p.structural, width: 1 } // part_of / verifies / searched_for / quotes / supersedes
  }
}

const SYMMETRIC = new Set(['parallel_of', 'contradicts'])

function truncate(s, n) {
  const chars = [...String(s ?? '')]
  return chars.length > n ? chars.slice(0, n).join('') + '…' : chars.join('')
}

function buildNodes(nodes, showAudit, p, verdicts) {
  return nodes.filter((n) => isVisible(n, showAudit)).map((n) => {
    const c = NODE_COLORS[nodeColorKey(n, verdicts)]
    const dashes = n.status === 'proposed' ? [4, 3] : false   // unchecked cue
    const width = n.status === 'accepted' ? 3.5 : 1.5          // citable weight
    return {
      id: n.id,
      label: truncate(nodeTitle(n), 16),
      shape: TYPE_SHAPE[n.type] || 'box',
      color: {
        background: c.fill,
        border: NODE_BORDER,
        highlight: { background: c.fill, border: p.text },
        hover: { background: c.fill, border: p.text },
      },
      borderWidth: width,
      borderWidthSelected: width + 2.5,
      shapeProperties: { borderDashes: dashes },
      font: { color: c.text, size: 14, face: 'system-ui' },
      margin: 7,
      widthConstraint: { maximum: 150 },
      // hover tooltip; the click opens the full DetailPanel inspector
      title: `${n.type} · ${n.status}${n.assurance ? ' · ' + n.assurance : ''}`,
    }
  })
}

function buildEdges(edges, visibleIds, p) {
  // parallel_of / contradicts are stored both directions; draw each once so the
  // edges the design most wants read at true weight aren't doubled.
  const seen = new Set()
  return edges
    .filter((e) => visibleIds.has(e.src) && visibleIds.has(e.dst))
    .filter((e) => {
      const key = [e.type, ...[e.src, e.dst].sort()].join('\x00')
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .map((e) => {
      const s = edgeStyle(e.type, p)
      const label = (EDGE_STYLE[e.type] || EDGE_STYLE.part_of).label
      return {
        id: e.id,
        from: e.src,
        to: e.dst,
        color: { color: s.color, highlight: s.color, hover: s.color, opacity: 0.9 },
        width: s.width,
        dashes: s.dashes || false,
        arrows: SYMMETRIC.has(e.type) ? undefined : { to: { enabled: true, scaleFactor: 0.55 } },
        smooth: { enabled: true, type: 'dynamic' },
        title: label + (e.discounts ? ' — discounts support' : ''),
      }
    })
}

export default function GraphView({ data, selectedId, onSelect, showAudit }) {
  const containerRef = useRef(null)
  const networkRef = useRef(null)
  const nodesRef = useRef(null)
  const edgesRef = useRef(null)
  const idsRef = useRef(new Set())
  // latest onSelect / selectedId, so the click handler (bound once) never goes stale
  const onSelectRef = useRef(onSelect)
  const selectedRef = useRef(selectedId)
  onSelectRef.current = onSelect
  selectedRef.current = selectedId

  // create the network once
  useEffect(() => {
    const nodes = new DataSet([])
    const edges = new DataSet([])
    nodesRef.current = nodes
    edgesRef.current = edges
    const network = new Network(
      containerRef.current,
      { nodes, edges },
      {
        physics: {
          stabilization: { iterations: 180 },
          barnesHut: {
            gravitationalConstant: -12000, springLength: 135,
            springConstant: 0.045, avoidOverlap: 0.35, damping: 0.28,
          },
        },
        interaction: { hover: true, tooltipDelay: 120, dragNodes: true, dragView: true, zoomView: true },
        nodes: { shadow: false, scaling: { min: 10, max: 30 } },
        edges: { smooth: { enabled: true, type: 'dynamic' } },
      },
    )
    networkRef.current = network
    // node click -> open (or, on the already-open node, close) the inspector,
    // matching the toggle-select gesture the rest of the UI uses.
    network.on('click', (params) => {
      if (params.nodes && params.nodes.length) {
        const id = params.nodes[0]
        onSelectRef.current(id === selectedRef.current ? null : id)
      }
    })
    // Fit the whole graph into view once physics settles, and again whenever the
    // container resizes (the canvas height tracks the viewport), so the graph is
    // never left zoomed into a corner.
    network.on('stabilizationIterationsDone', () => network.fit({ animation: false }))
    const ro = new ResizeObserver(() => networkRef.current && networkRef.current.fit({ animation: false }))
    ro.observe(containerRef.current)
    return () => { ro.disconnect(); network.destroy(); networkRef.current = null }
  }, [])

  // (re)load the data whenever it or the audit toggle changes
  useEffect(() => {
    if (!nodesRef.current) return
    const p = palette()
    const verdicts = claimVerdicts(data.nodes, data.edges)
    const visNodes = buildNodes(data.nodes, showAudit, p, verdicts)
    idsRef.current = new Set(visNodes.map((n) => n.id))
    const visEdges = buildEdges(data.edges, idsRef.current, p)
    nodesRef.current.clear()
    edgesRef.current.clear()
    nodesRef.current.add(visNodes)
    edgesRef.current.add(visEdges)
    if (selectedRef.current && idsRef.current.has(selectedRef.current)) {
      networkRef.current.selectNodes([selectedRef.current])
    }
  }, [data, showAudit])

  // reflect a selection made elsewhere (e.g. the Findings tab) onto the canvas
  useEffect(() => {
    const net = networkRef.current
    if (!net) return
    if (selectedId && idsRef.current.has(selectedId)) {
      net.selectNodes([selectedId])
      net.focus(selectedId, { scale: 1.0, animation: { duration: 300 } })
    } else {
      net.unselectAll()
    }
  }, [selectedId])

  return (
    <div className="graph-scroll">
      <div
        ref={containerRef}
        className="graph-canvas"
        role="img"
        aria-label="Evidence graph (draggable)"
        style={{ width: '100%', height: 'calc(100vh - 150px)', minHeight: '420px' }}
      />
    </div>
  )
}
