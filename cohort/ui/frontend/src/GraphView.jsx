import { useEffect, useRef } from 'react'
import { DataSet, Network } from 'vis-network/standalone'
import { EDGE_STYLE, isVisible, nodeTitle, nodeStatusLabel } from './graph-model'

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
    addresses: v('--addresses', '#f29ac8'),
    proposed: v('--proposed', '#8e8e96'),
    attested: v('--attested', '#0a84ff'),
    accepted: v('--accepted', '#30d158'),
    rejected: v('--rejected', '#ff453a'),
  }
}

// `claim` and `conjecture` are one shape now: the UI has always called the
// pair "hypothesis" (see the legend comment below) and drawing them
// differently — a box for one, a diamond for the other — read as two kinds of
// thing where the vocabulary says there is one.
export const TYPE_SHAPE = {
  witness: 'ellipse', passage: 'box', claim: 'diamond', conjecture: 'diamond',
  query: 'dot', question: 'star', verification: 'square', decision: 'square',
}

// A hypothesis's fill is its STATUS, not a computed verdict: grey while
// PROPOSED (nothing has checked it), blue once ATTESTED, green once ACCEPTED
// — the one citable state — red once REJECTED, and yellow whenever a live
// `contradicts` edge touches it (CONTRADICTED), independent of status, because
// a contradiction discovered after acceptance is exactly the case a reader
// must not have hidden from them.
//   * a source text (CBETA witness) is BLACK, an agent query BLUE;
//   * passages, research questions and audit nodes get their own steady colours.
// Type shape stays a second channel; status also rides the border (dashed =
// proposed / unchecked, heavier = accepted) so it survives greyscale too.
const NODE_BORDER = '#8a8a8f'
const INK_LIGHT = '#f7f7fa'
const INK_DARK = '#0b0b0c'
const NODE_COLORS = {
  witness:      { fill: '#141416', text: INK_LIGHT },
  passage:      { fill: '#0a84ff', text: INK_LIGHT },   // located evidence, blue like the query
  query:        { fill: '#0a84ff', text: INK_LIGHT },
  question:     { fill: '#5e5ce6', text: INK_LIGHT },
  audit:        { fill: '#8e8e93', text: INK_LIGHT },   // verification / decision
  proposed:     { fill: '#8e8e96', text: INK_LIGHT },
  attested:     { fill: '#0a84ff', text: INK_LIGHT },
  contradicted: { fill: '#ffd60a', text: INK_DARK },
  accepted:     { fill: '#30d158', text: INK_DARK },
  rejected:     { fill: '#ff453a', text: INK_LIGHT },
}

// What a conjecture turned out to be, when the server says so — see
// `views.assessments`. This channel exists because status is blind to an
// ascription study: those conjectures are settled by measurement and carry no
// attesting passages, so all twenty-two of them would render identically
// under plain status whether their control had been survived, failed, or
// never run.
//
// `unplaced` is deliberately the same yellow as `contradicted`: in both cases
// the method could not see the thing, which is not a finding against it — a
// separate literal, not an alias, because the two are not the same concept.
// `alternate` gets violet — the `tests` hue — because it points somewhere
// else rather than confirming or denying anything here.
const ASSESSMENT_COLORS = {
  survived:   NODE_COLORS.accepted,
  discarded:  NODE_COLORS.rejected,
  untested:   { fill: '#8e8e96', text: INK_LIGHT },
  associates: NODE_COLORS.accepted,
  weak:       { fill: '#ff9f0a', text: INK_DARK },
  alternate:  { fill: '#bf5af2', text: INK_LIGHT },
  unplaced:   { fill: '#ffd60a', text: INK_DARK },
}

//: The whole node-colour vocabulary. `types` is what has to be on screen for
//: an entry to be worth showing, and `states` likewise — see `nodeLegendFor`.
//:
//: **`hypothesis`, not `claim`.** These three entries colour a `claim` *or* a
//: `conjecture`, and calling the pair "claim" was wrong twice over: it is the
//: name of one of the two, and Findings has always called them hypotheses.
//: `claim` and `conjecture` stay the node types in the graph and in the
//: vocabulary — they carry different rules, and a refusal still names which —
//: but where the UI means "either of them" it now says hypothesis.
//:
//: `feature` and `work` name what a hypothesis is *about* rather than
//: repeating `hypothesis` ten times down a horizontal key. They are
//: hypotheses too; the subject is the informative half.
const NODE_LEGEND_ALL = [
  { key: 'hypothesis — proposed', color: NODE_COLORS.proposed.fill, types: ['claim', 'conjecture'] },
  { key: 'hypothesis — attested', color: NODE_COLORS.attested.fill, types: ['claim', 'conjecture'] },
  { key: 'hypothesis — contradicted', color: NODE_COLORS.contradicted.fill, types: ['claim', 'conjecture'] },
  { key: 'hypothesis — accepted', color: NODE_COLORS.accepted.fill, types: ['claim', 'conjecture'] },
  { key: 'hypothesis — rejected', color: NODE_COLORS.rejected.fill, types: ['claim', 'conjecture'] },
  { key: 'feature — survived its control', color: ASSESSMENT_COLORS.survived.fill, states: ['survived'] },
  { key: 'feature — discarded by its control', color: ASSESSMENT_COLORS.discarded.fill, states: ['discarded'] },
  { key: 'feature — control not run', color: ASSESSMENT_COLORS.untested.fill, states: ['untested'] },
  { key: 'work — associates with the benchmark', color: ASSESSMENT_COLORS.associates.fill, states: ['associates'] },
  { key: 'work — weak association', color: ASSESSMENT_COLORS.weak.fill, states: ['weak'] },
  { key: 'work — alternate reference point', color: ASSESSMENT_COLORS.alternate.fill, states: ['alternate'] },
  { key: 'work — not placed', color: ASSESSMENT_COLORS.unplaced.fill, states: ['unplaced'] },
  { key: 'source text', color: NODE_COLORS.witness.fill, types: ['witness'] },
  { key: 'passage', color: NODE_COLORS.passage.fill, types: ['passage'] },
  { key: 'search query', color: NODE_COLORS.query.fill, types: ['query'] },
  { key: 'research question', color: NODE_COLORS.question.fill, types: ['question'] },
]

// The key for *this* graph, not the vocabulary — the same discipline
// `legendFor` applies to edges. Ten node colours listed against a graph that
// draws four is a legend a reader has to filter by hand, and one that offers
// "survived its control" where no control was ever run is describing a
// different study.
export function nodeLegendFor(nodes, showAudit) {
  const shown = nodes.filter((n) => isVisible(n, showAudit))
  const types = new Set(shown.map((n) => n.type))
  const states = new Set(shown.map((n) => n.assessment?.state).filter(Boolean))
  return NODE_LEGEND_ALL.filter((entry) => {
    // A conjecture the server has assessed is drawn by its assessment, so the
    // three edge-derived entries must not claim it.
    if (entry.types) {
      const assessed = entry.types.some((t) => t === 'claim' || t === 'conjecture')
      if (assessed && !shown.some((n) => entry.types.includes(n.type) && !n.assessment)) {
        return false
      }
      return entry.types.some((t) => types.has(t))
    }
    return entry.states.some((st) => states.has(st))
  })
}

// Node ids touched by a live `contradicts` edge — symmetric, so either end
// counts. Used to paint CONTRADICTED over whatever status the node itself
// carries: the fact that something now contradicts it is the thing a reader
// needs to see, whether the node was proposed, attested, or already accepted.
function contradictedIds(edges) {
  const ids = new Set()
  for (const e of edges) {
    if (e.type === 'contradicts') {
      ids.add(e.src)
      ids.add(e.dst)
    }
  }
  return ids
}

// Which colour a node takes, and the precedence when two channels both have
// something to say.
//
// `rejected` wins outright — a researcher's rejection is final. `contradicted`
// wins over an assessment or a plain status, because a live contradiction is
// new information a reader must not have hidden from them just because the
// node was accepted, or because a control was run before the contradiction
// was recorded. Failing both, a server-side `assessment` wins over plain
// status: it is the result of a test that was actually run — a negative
// control, or a measurement against the canon — which outranks "nothing has
// checked this yet".
function nodeColorKey(node, contradicted) {
  switch (node.type) {
    case 'witness': return 'witness'
    case 'passage': return 'passage'
    case 'query': return 'query'
    case 'question': return 'question'
    case 'verification':
    case 'decision': return 'audit'
    case 'claim':
    case 'conjecture': {
      if (node.status === 'rejected') return 'rejected'
      if (contradicted.has(node.id)) return 'contradicted'
      if (node.assessment && ASSESSMENT_COLORS[node.assessment.state]) {
        return `assessment:${node.assessment.state}`
      }
      return node.status === 'accepted' ? 'accepted'
        : node.status === 'attested' ? 'attested'
        : 'proposed'
    }
    default: return 'audit'
  }
}

//: One lookup over both palettes, so `buildNodes` does not have to know which
//: channel produced the key.
function colorFor(key) {
  if (key.startsWith('assessment:')) {
    return ASSESSMENT_COLORS[key.slice('assessment:'.length)]
  }
  return NODE_COLORS[key]
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

// `part_of` is stored and drawn passage -> witness (`from: e.src, to: e.dst`
// below) like every other edge — nothing about the data moves. But its label
// reads "contains", from the witness's side, and an arrowhead sitting on the
// witness while the word describes the witness as the one doing the
// containing pointed the picture and the sentence in opposite directions.
// So this is the one type whose arrowhead is drawn at `from` instead of `to`
// — the line still runs between the same two nodes, only which end gets the
// arrowhead is flipped, purely at the canvas layer.
const ARROW_AT_FROM = new Set(['part_of'])

function truncate(s, n) {
  const chars = [...String(s ?? '')]
  return chars.length > n ? chars.slice(0, n).join('') + '…' : chars.join('')
}

// vis-network draws a box/ellipse's label INSIDE the shape, tinted for
// contrast against its fill — but a diamond or a star gets its label
// OUTSIDE, underneath, sitting on the canvas background rather than on
// `c.fill`. Using the fill-contrast colour there was picking white for
// several hypothesis statuses (proposed/attested/rejected) whenever the
// canvas itself reads light, which is illegible. These two shapes get a
// fixed dark label regardless of status colour.
const OUTSIDE_LABEL_SHAPES = new Set(['diamond', 'star'])

function buildNodes(nodes, showAudit, p, contradicted) {
  return nodes.filter((n) => isVisible(n, showAudit)).map((n) => {
    const c = colorFor(nodeColorKey(n, contradicted))
    const dashes = n.status === 'proposed' ? [4, 3] : false   // unchecked cue
    const width = n.status === 'accepted' ? 3.5 : 1.5          // citable weight
    const shape = TYPE_SHAPE[n.type] || 'box'
    return {
      id: n.id,
      label: truncate(nodeTitle(n), 16),
      shape,
      color: {
        background: c.fill,
        border: NODE_BORDER,
        highlight: { background: c.fill, border: p.text },
        hover: { background: c.fill, border: p.text },
      },
      borderWidth: width,
      borderWidthSelected: width + 2.5,
      shapeProperties: { borderDashes: dashes },
      font: { color: OUTSIDE_LABEL_SHAPES.has(shape) ? INK_DARK : c.text, size: 14, face: 'system-ui' },
      margin: 7,
      widthConstraint: { maximum: 150 },
      // hover tooltip; the click opens the full DetailPanel inspector.
      // The assessment's own sentence rather than its state
      // word, because "unplaced" and "discarded" are easy to read as the
      // same kind of negative and are not.
      title: `${n.type} · ${nodeStatusLabel(n)}${n.assurance ? ' · ' + n.assurance : ''}`
        + (n.assessment ? `\n${n.assessment.detail}` : ''),
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
        arrows: SYMMETRIC.has(e.type)
          ? undefined
          : ARROW_AT_FROM.has(e.type)
            ? { from: { enabled: true, scaleFactor: 0.55 } }
            : { to: { enabled: true, scaleFactor: 0.55 } },
        smooth: { enabled: true, type: 'dynamic' },
        title: label + (e.discounts ? ' — discounts support' : ''),
      }
    })
}

export default function GraphView({ data, selectedId, onSelect, showAudit, exploration }) {
  const containerRef = useRef(null)
  const networkRef = useRef(null)
  const nodesRef = useRef(null)
  const edgesRef = useRef(null)
  const idsRef = useRef(new Set())
  const layoutReady = useRef(false)
  const positionsRef = useRef({})
  const clickedSelection = useRef(false)
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
        clickedSelection.current = true
        onSelectRef.current(id === selectedRef.current ? null : id)
      }
    })
    // Arrange once, then stop the simulation. Reading, dragging and incoming
    // records must not restart physics or move the camera.
    const finishLayout = () => {
      if (layoutReady.current || !nodes.length) return
      layoutReady.current = true
      network.setOptions({ physics: { enabled: false } })
      network.fit({ animation: false })
    }
    network.on('stabilizationIterationsDone', finishLayout)
    network.on('stabilized', finishLayout)
    return () => { network.destroy(); networkRef.current = null; layoutReady.current = false }
  }, [])

  // (re)load the data whenever it or the audit toggle changes
  useEffect(() => {
    if (!nodesRef.current) return
    const p = palette()
    const contradicted = contradictedIds(data.edges)
    const visNodes = buildNodes(data.nodes, showAudit, p, contradicted)
    for (const item of exploration?.nodes || []) visNodes.push({
      id:item.id, label:item.label, shape:'box',
      color:{background:p.surface,border:p.textDim}, font:{color:p.text,size:13},
      shapeProperties:{borderDashes:[3,5]}, margin:9,
      title:'Exploration activity — click for actions and worker',
    })
    idsRef.current = new Set(visNodes.map((n) => n.id))
    const visEdges = buildEdges(data.edges, idsRef.current, p)
    for (const edge of exploration?.edges || []) {
      if (idsRef.current.has(edge.from) && idsRef.current.has(edge.to)) visEdges.push({
        ...edge, dashes:[3,5], arrows:'', color:{color:p.textDim}, width:1,
        title:'Exploration activity, not evidential support',
      })
    }
    const net = networkRef.current
    Object.assign(positionsRef.current, net.getPositions())
    const positions = positionsRef.current
    if (layoutReady.current) {
      visNodes.forEach((node, i) => {
        if (positions[node.id]) Object.assign(node, positions[node.id])
        else {
          const edge = visEdges.find((e) =>
            (e.from === node.id && positions[e.to]) || (e.to === node.id && positions[e.from]))
          const anchor = edge ? positions[edge.from === node.id ? edge.to : edge.from] : net.getViewPosition()
          const angle = i * 2.399963229728653
          Object.assign(node, { x: anchor.x + 150 * Math.cos(angle), y: anchor.y + 150 * Math.sin(angle) })
        }
      })
    }
    // Update existing records in place; clearing the datasets discards layout.
    const edgeIds = new Set(visEdges.map((e) => e.id))
    edgesRef.current.remove(edgesRef.current.getIds().filter((id) => !edgeIds.has(id)))
    nodesRef.current.remove(nodesRef.current.getIds().filter((id) => !idsRef.current.has(id)))
    nodesRef.current.update(visNodes)
    edgesRef.current.update(visEdges)
    if (!layoutReady.current && visNodes.length) net.stabilize(180)
    if (selectedRef.current && idsRef.current.has(selectedRef.current)) {
      networkRef.current.selectNodes([selectedRef.current])
    }
  }, [data, showAudit, exploration])

  // reflect a selection made elsewhere (e.g. the Findings tab) onto the canvas
  useEffect(() => {
    const net = networkRef.current
    if (!net) return
    const fromClick = clickedSelection.current
    clickedSelection.current = false
    if (selectedId && idsRef.current.has(selectedId)) {
      net.selectNodes([selectedId])
      if (!fromClick) net.focus(selectedId, { scale: 1.0, animation: false })
    } else {
      net.unselectAll()
    }
  }, [selectedId])

  return (
    <div className="graph-scroll">
      <button className="btn tiny" style={{ margin: '8px 18px' }}
        onClick={() => networkRef.current?.fit({ animation: false })}>Fit graph</button>
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
