// Layout and visual encoding.
//
// docs/design.md §10 is explicit that a naive rendering of this graph "flattens
// exactly the epistemics that justify the system", so three things below are
// requirements rather than styling choices:
//
//   * node status is a visual channel, not a tooltip;
//   * `descends_from`/`parallel_of` are visually distinct from `attests`,
//     because they *discount* support rather than adding it;
//   * contradiction edges are as visible as agreement edges.
//
// The layout is a deterministic evidence chain — witness → passage →
// claim/conjecture — rather than a force simulation. A force blob would place
// the same graph differently on every load, which is a poor property for
// something a researcher is meant to read, cite and return to.

export const COLUMNS = [
  { key: 'witness', label: 'Witnesses', types: ['witness'] },
  { key: 'passage', label: 'Passages', types: ['passage'] },
  { key: 'assertion', label: 'Claims & conjectures', types: ['claim', 'conjecture'] },
  { key: 'audit', label: 'Queries & audit', types: ['query', 'verification', 'decision'] },
  // Rightmost, because the last column reads as where the chain arrives, and
  // what it arrives at is the thing the work was for. Audit sits before it:
  // a query and a verification are how an assertion was reached, not where it
  // was heading, so ending the chain on them would make bookkeeping the
  // conclusion. The cost is that `addresses` now spans the audit column, and
  // that is the cheaper cost — two edges bowing over a column of queries,
  // against a layout that puts the research question behind the paperwork.
  { key: 'question', label: 'Research questions', types: ['question'] },
]

// Audit bookkeeping, not evidence (docs/design.md §5 principle 6). Hidden by
// default so the evidence chain stays legible; never removed, because hiding
// verification permanently would overstate how checked the graph is.
export const AUDIT_TYPES = new Set(['verification', 'decision'])

export const STATUS_ORDER = ['proposed', 'attested', 'accepted', 'rejected']

export const EDGE_STYLE = {
  attests:      { klass: 'e-attests',      label: 'attests' },
  part_of:      { klass: 'e-structural',   label: 'part of' },
  verifies:     { klass: 'e-structural',   label: 'verifies' },
  searched_for: { klass: 'e-structural',   label: 'searched for' },
  tests:        { klass: 'e-tests',        label: 'tests' },
  // Its own channel, not `e-structural`. `part_of` and `verifies` are
  // bookkeeping that says where a record sits; `addresses` says what the work
  // was *for*, and a graph that drew it as bookkeeping would be hiding the one
  // relation a reader scans for first.
  addresses:    { klass: 'e-addresses',    label: 'addresses' },
  supersedes:   { klass: 'e-structural',   label: 'supersedes' },
  quotes:       { klass: 'e-structural',   label: 'quotes' },
  contradicts:  { klass: 'e-contradicts',  label: 'contradicts' },
  parallel_of:  { klass: 'e-discount',     label: 'parallel of' },
  descends_from:{ klass: 'e-discount',     label: 'descends from' },
}

// What the legend offers to explain, in reading order: the three edge kinds
// that carry the argument first, then the two that say what an assertion was
// for and what would refute it, then bookkeeping last.
//
// `strong` is the word rendered bold. That agreement between related
// witnesses *discounts* support is the system's central claim, so the legend
// says it in words; a reader left to infer it from a dash pattern is being
// handed a code, not a key.
export const LEGEND_EDGES = [
  { key: 'attests', types: ['attests'], klass: 'e-attests', text: 'attests — adds support' },
  {
    key: 'discount',
    types: ['parallel_of', 'descends_from'],
    klass: 'e-discount',
    text: 'parallel of / descends from — discounts support',
    strong: 'discounts',
  },
  { key: 'contradicts', types: ['contradicts'], klass: 'e-contradicts', text: 'contradicts' },
  {
    key: 'tests',
    types: ['tests'],
    klass: 'e-tests',
    text: 'tests — the query that would refute this, predicted before the evidence was in',
  },
  { key: 'addresses', types: ['addresses'], klass: 'e-addresses', text: 'addresses — what an assertion answers' },
  {
    key: 'structural',
    types: ['part_of', 'verifies', 'searched_for', 'supersedes', 'quotes'],
    klass: 'e-structural',
    text: 'structural — where a record sits',
  },
]

//: Shown instead of the plain `tests` entry once any prediction has been run.
//: Keyed by outcome rather than by edge type, because after a test is run the
//: outcome is the thing a reader is looking for.
export const LEGEND_OUTCOMES = [
  { key: 'held', klass: 'e-test-held', text: 'prediction held', strong: 'held' },
  { key: 'broke', klass: 'e-test-broke', text: 'prediction broke', strong: 'broke' },
  { key: 'undecided', klass: 'e-test-undecided', text: 'test did not decide' },
]

//: One rule for what the reader can see, used by both `layout` and
//: `legendFor`. Two copies of this test is how `question` nodes came to be
//: absent from the graph while present in every other view: a node type
//: missing from `COLUMNS` is invisible, and nothing said so.
const COLUMN_TYPES = new Set(COLUMNS.flatMap((c) => c.types))

export function isVisible(node, showAudit) {
  return COLUMN_TYPES.has(node.type) && (showAudit || !AUDIT_TYPES.has(node.type))
}

// A legend listing every edge type the vocabulary has explains, on most
// graphs, mostly things that are not on the screen — and a key with six
// entries for a picture using two teaches the reader to stop reading it. So
// it describes this graph: the entries whose edges are actually drawn, in the
// fixed order above, plus the statuses actually present.
//
// Safe to shrink *because* it is derived from the drawn edges: an entry can
// only vanish when there is nothing left for it to mislabel. It shrinks for
// the audit toggle too, which is the point — turning bookkeeping off should
// take its key with it.
export function legendFor(nodes, edges, { showAudit }) {
  const visible = new Set(nodes.filter((n) => isVisible(n, showAudit)).map((n) => n.id))
  const drawn = new Set(
    edges.filter((e) => visible.has(e.src) && visible.has(e.dst)).map((e) => e.type),
  )
  const statuses = new Set(
    nodes.filter((n) => visible.has(n.id)).map((n) => n.status),
  )
  const outcomes = new Set(
    edges
      .filter((e) => visible.has(e.src) && visible.has(e.dst))
      .filter((e) => e.type === 'tests' && e.outcome && e.outcome !== 'unrun')
      .map((e) => e.outcome),
  )
  // A `tests` entry is dropped once every tests edge on screen has been run:
  // it would be explaining a dotted line the reader cannot see.
  const anyUnrun = edges.some(
    (e) => visible.has(e.src) && visible.has(e.dst)
      && e.type === 'tests' && (!e.outcome || e.outcome === 'unrun'),
  )
  return {
    edges: LEGEND_EDGES.filter(
      (entry) => entry.types.some((t) => drawn.has(t))
        && !(entry.key === 'tests' && !anyUnrun),
    ),
    outcomes: LEGEND_OUTCOMES.filter((o) => outcomes.has(o.key)),
    statuses: STATUS_ORDER.filter((s) => statuses.has(s)),
  }
}

// A `tests` edge is the only edge whose meaning changes after it is drawn.
// Every other relation states something that is either true or retracted; this
// one states a prediction, and a prediction that has been run either held or
// broke. Rendering all of them alike turns twenty-two tested predictions into
// twenty-two identical lines — which is precisely the flattening §10 forbids,
// on the axis a prediction-driven study actually turns on.
//
// Dotted stays the *unrun* case, which is what dotted was always saying: still
// open, not yet asked.
export const TEST_OUTCOME = {
  held:      { klass: 'e-test-held',      label: 'prediction held' },
  broke:     { klass: 'e-test-broke',     label: 'prediction broke' },
  undecided: { klass: 'e-test-undecided', label: 'test did not decide' },
  unrun:     { klass: 'e-tests',          label: 'tests — not yet run' },
}

export function edgeClass(edge) {
  if (edge.type === 'tests' && edge.outcome) {
    return (TEST_OUTCOME[edge.outcome] || TEST_OUTCOME.unrun).klass
  }
  return (EDGE_STYLE[edge.type] || EDGE_STYLE.part_of).klass
}

export const NODE_W = 190
export const NODE_H = 54
//: wide enough for a same-column edge to bow out into the gap without
//: reaching the next column (see `edgePath`), which is what the two most
//: important edge types actually need — `parallel_of` links witnesses to
//: witnesses and `contradicts` links a claim to a conjecture, and both
//: endpoints therefore sit in one column.
const COL_GAP = 310
const ROW_GAP = 86
const PAD_X = 40
const PAD_Y = 56
//: horizontal room inside a node for its title: the 14px left inset plus a
//: 12px right gutter.
export const TITLE_MAX_PX = NODE_W - 14 - 12

export function layout(nodes, { showAudit }) {
  const visible = nodes.filter((n) => isVisible(n, showAudit))
  const columns = COLUMNS.map((col) => ({
    ...col,
    nodes: visible
      .filter((n) => col.types.includes(n.type))
      .sort((a, b) => a.created_seq - b.created_seq),
  })).filter((col) => col.nodes.length > 0)

  const positions = new Map()
  columns.forEach((col, ci) => {
    col.nodes.forEach((node, ri) => {
      positions.set(node.id, {
        x: PAD_X + ci * COL_GAP,
        y: PAD_Y + ri * ROW_GAP,
        w: NODE_W,
        h: NODE_H,
        node,
      })
    })
  })

  const width = PAD_X * 2 + Math.max(1, columns.length) * COL_GAP
  const rows = Math.max(1, ...columns.map((c) => c.nodes.length))
  const height = PAD_Y * 2 + rows * ROW_GAP
  return { columns, positions, width, height }
}

// A curve rather than a straight line: with columns, many edges share
// endpoints, and straight segments overlap into an unreadable bundle.
export function edgePath(from, to) {
  const y1 = from.y + from.h / 2
  const y2 = to.y + to.h / 2

  // Same column. This case used to fall through to the backward branch, which
  // drew a horizontal line from the source's left edge to the target's right
  // edge — straight through both node boxes, and through every node between
  // them. It was not a cosmetic problem: `parallel_of`, `descends_from` and
  // `contradicts` all connect nodes within one column, so the three edge types
  // carrying the design's actual argument were the ones being drawn as lines
  // through solid rectangles. They now bow out into the column gap, further
  // for a longer vertical span so several of them stay separable.
  if (from.x === to.x) {
    const x = from.x + from.w
    const bulge = Math.min(96, 34 + Math.abs(y2 - y1) * 0.30)
    return `M ${x} ${y1} C ${x + bulge} ${y1}, ${x + bulge} ${y2}, ${x} ${y2}`
  }

  const x1 = from.x + from.w
  const x2 = to.x
  if (x2 < x1) {
    // a backward edge (e.g. passage -> witness): leave from the left side
    const bx1 = from.x
    const bx2 = to.x + to.w
    const mid = (bx1 + bx2) / 2
    return `M ${bx1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${bx2} ${y2}`
  }
  const mid = (x1 + x2) / 2
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`
}

//: CJK and other full-width characters occupy roughly a full em, Latin about
//: half. Truncating by character count therefore overflowed badly on this
//: corpus: 24 Chinese characters at 13px is ~312px in a 164px slot.
const FULLWIDTH_RE = /[\u1100-\u115f\u2e80-\u9fff\ua960-\ua97f\uac00-\ud7a3\uf900-\ufaff\ufe30-\ufe4f\uff00-\uff60\uffe0-\uffe6]/

//: Fit `text` to `maxPx` at `fontPx`, appending an ellipsis when it is cut.
//: An estimate, not a measurement — measuring would need a canvas or a DOM
//: round-trip per node — but it is a *conservative* estimate, and the node's
//: clip path in `GraphView` is the hard guarantee behind it.
export function fitText(text, maxPx = TITLE_MAX_PX, fontPx = 13) {
  const s = String(text ?? '')
  const charW = (ch) => (FULLWIDTH_RE.test(ch) ? fontPx : fontPx * 0.53)
  let total = 0
  for (const ch of s) total += charW(ch)
  if (total <= maxPx) return s

  const budget = maxPx - fontPx * 0.53   // room for the ellipsis
  let acc = 0
  let out = ''
  for (const ch of s) {
    const w = charW(ch)
    if (acc + w > budget) break
    out += ch
    acc += w
  }
  return `${out.trimEnd()}…`
}

export function nodeTitle(node) {
  const p = node.payload || {}
  if (node.type === 'witness') return p.label || p.canonical_ref || node.id
  if (node.type === 'passage') return p.excerpt || p.canonical_ref || node.id
  if (node.type === 'verification') return `${p.method || 'verification'} · ${p.result || ''}`
  if (node.type === 'decision') return p.action || 'decision'
  return p.text || node.id
}
