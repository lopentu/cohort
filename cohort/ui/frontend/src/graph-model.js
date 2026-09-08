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
  // The edge is still stored passage -> witness (schemas.py EDGE_DOMAINS,
  // unchanged) — but "passage part of witness" read subordinate-first, the
  // passage as the primary thing and the witness as a location note.
  // "contains" reads the other way, from the container's side, and
  // GraphView.jsx's `ARROW_AT_FROM` draws the arrowhead to match: it points at
  // the passage, so the picture reads "witness contains passage" the same
  // direction as the word, rather than a label contradicting the arrow it
  // sits on.
  part_of:      { klass: 'e-structural',   label: 'contains' },
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
  { key: 'attests', types: ['attests'], klass: 'e-attests', text: 'attests — passage supports proposal' },
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
    text: 'tests — query tests a conjecture',
  },
  { key: 'addresses', types: ['addresses'], klass: 'e-addresses', text: 'addresses — proposal responds to question' },
  {
    key: 'structural',
    types: ['part_of', 'verifies', 'searched_for', 'supersedes', 'quotes'],
    klass: 'e-structural',
    text: 'source links and audit records',
  },
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
  return {
    edges: LEGEND_EDGES.filter((entry) => entry.types.some((t) => drawn.has(t))),
    statuses: STATUS_ORDER.filter((s) => statuses.has(s)),
  }
}

// Hiding a question is a browser-only preference (App.jsx holds the set,
// RunPanel.jsx persists it) — never a graph write. docs/design.md principle 1
// makes the event log the one place a question could be un-asked, and there
// is no such event, so "remove it and its relevant nodes/edges" can only mean
// *stop drawing* them, recomputed fresh from the current graph on every
// render rather than a flag stored on any node.
//
// A hypothesis is pulled in with a hidden question only if it has nothing
// else to be shown for: every `addresses` edge it has names a hidden
// question. One that also addresses a question that stays visible is left
// alone — it is still live evidence for that question.
//
// A witness/passage/query/verification/decision is pulled in only once every
// edge it has left points into the already-hidden set — an attesting passage
// that also supports a still-visible hypothesis stays, because it is real
// evidence for that hypothesis regardless of what else it once supported.
// Iterated to a fixed point because hiding one node can orphan another (a
// witness whose one passage was just hidden).
const PRUNABLE_SUPPORT_TYPES = new Set(['witness', 'passage', 'query', 'verification', 'decision'])

export function hiddenIdsForQuestions(nodes, edges, hiddenQuestionIds) {
  const hidden = new Set(hiddenQuestionIds)
  if (!hidden.size) return hidden

  const addressesOf = new Map()   // hypothesis id -> Set(question id)
  for (const e of edges) {
    if (e.type !== 'addresses') continue
    const qs = addressesOf.get(e.src) || new Set()
    qs.add(e.dst)
    addressesOf.set(e.src, qs)
  }
  for (const [hypId, qs] of addressesOf) {
    if ([...qs].every((q) => hidden.has(q))) hidden.add(hypId)
  }

  // Sweep support nodes to a fixed point: each pass can hide a node the
  // previous pass could not yet justify hiding.
  let changed = true
  while (changed) {
    changed = false
    for (const n of nodes) {
      if (hidden.has(n.id) || !PRUNABLE_SUPPORT_TYPES.has(n.type)) continue
      let touching = edges.filter((e) => e.src === n.id || e.dst === n.id)
      // A passage's `part_of` (now labelled "contains") edge to its witness
      // says where it sits, not why it matters — every passage has exactly
      // one, so counting it here would make a passage un-hideable, and worse,
      // deadlocks against its witness: the passage stays visible because its
      // witness isn't hidden yet, and the witness stays visible because this
      // passage isn't hidden yet, and neither pass ever breaks the tie. Only
      // a passage's *evidentiary* edges (attests, verifies, tests) decide
      // whether hiding the question left it with nothing to be shown for; a
      // witness's own visibility is still decided by its `part_of` edges
      // below, once its passages have already been resolved.
      if (n.type === 'passage') touching = touching.filter((e) => e.type !== 'part_of')
      if (!touching.length) continue   // nothing links it either way — leave it
      const stillLinked = touching.some((e) => !hidden.has(e.src === n.id ? e.dst : e.src))
      if (!stillLinked) {
        hidden.add(n.id)
        changed = true
      }
    }
  }
  return hidden
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
