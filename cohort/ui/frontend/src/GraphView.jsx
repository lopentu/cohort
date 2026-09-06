import {
  COLUMNS,
  EDGE_STYLE,
  TEST_OUTCOME,
  edgeClass,
  NODE_H,
  NODE_W,
  edgePath,
  fitText,
  layout,
  nodeTitle,
} from './graph-model'

export default function GraphView({ data, selectedId, onSelect, showAudit }) {
  const { columns, positions, width, height } = layout(data.nodes, { showAudit })

  const edges = data.edges.filter(
    (e) => positions.has(e.src) && positions.has(e.dst),
  )
  // `parallel_of` and `contradicts` are stored in both directions; drawing
  // both would double the visual weight of exactly the edges the design wants
  // read at their true strength.
  const seen = new Set()
  const drawn = edges.filter((e) => {
    const key = [e.type, ...[e.src, e.dst].sort()].join('\x00')
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })

  const neighbours = new Set()
  if (selectedId) {
    drawn.forEach((e) => {
      if (e.src === selectedId) neighbours.add(e.dst)
      if (e.dst === selectedId) neighbours.add(e.src)
    })
  }

  return (
    <div className="graph-scroll">
      <svg width={width} height={height} className="graph" role="img" aria-label="Evidence graph">
        <defs>
          {['attests', 'discount', 'contradicts', 'structural', 'tests', 'addresses',
            'test-held', 'test-broke', 'test-undecided'].map((k) => (
            <marker
              key={k} id={`arrow-${k}`} viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="6" markerHeight="6" orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" className={`arrow a-${k}`} />
            </marker>
          ))}
          {/* The hard guarantee behind `fitText`'s estimate: label text can
              never paint outside its node box, whatever the font or script
              actually measures. Defined once at the node's own origin, which
              is where every node group's coordinates start. */}
          <clipPath id="node-clip">
            <rect width={NODE_W} height={NODE_H} rx="7" />
          </clipPath>
        </defs>

        {columns.map((col, ci) => {
          const first = col.nodes[0] && positions.get(col.nodes[0].id)
          return first ? (
            <text key={col.key} className="col-label" x={first.x} y={26}>
              {COLUMNS.find((c) => c.key === col.key)?.label}
            </text>
          ) : null
        })}

        <g className="edges">
          {drawn.map((e) => {
            const style = EDGE_STYLE[e.type] || EDGE_STYLE.part_of
            // A run `tests` edge draws as its outcome, not as its type.
            const klass = edgeClass(e)
            const label =
              e.type === 'tests' && e.outcome
                ? (TEST_OUTCOME[e.outcome] || TEST_OUTCOME.unrun).label
                : style.label
            const dim = selectedId && e.src !== selectedId && e.dst !== selectedId
            const marker = klass.replace('e-', '')
            return (
              <path
                key={e.id}
                d={edgePath(positions.get(e.src), positions.get(e.dst))}
                className={`edge ${klass} ${dim ? 'dim' : ''}`}
                markerEnd={`url(#arrow-${marker})`}
              >
                <title>{label}{e.discounts ? ' — discounts support' : ''}</title>
              </path>
            )
          })}
        </g>

        <g className="nodes">
          {[...positions.values()].map(({ x, y, w, h, node }) => {
            const isSel = node.id === selectedId
            const dim = selectedId && !isSel && !neighbours.has(node.id)
            // A second click on the selected node closes the inspector.
            // Selecting is a toggle everywhere else in this UI — the refusals
            // pill, the gear, the stats disclosure — and without it undoing a
            // click means reaching for the close button or Escape.
            const pick = () => onSelect(isSel ? null : node.id)
            return (
              <g
                key={node.id}
                transform={`translate(${x},${y})`}
                className={`node n-${node.type} s-${node.status} ${isSel ? 'selected' : ''} ${dim ? 'dim' : ''}`}
                onClick={pick}
                tabIndex={0}
                role="button"
                aria-pressed={isSel}
                onKeyDown={(ev) => (ev.key === 'Enter' || ev.key === ' ') && pick()}
              >
                {/* Selection gets its own ring outside the box rather than
                    restyling the box's stroke. The stroke now carries status
                    (docs/design.md §10), and a selected node whose status
                    colour had been overwritten by the selection colour would
                    hide the one channel §10 requires — exactly when the
                    reader is looking hardest at it. */}
                <rect
                  x="-3" y="-3" width={w + 6} height={h + 6} rx="10"
                  className="node-ring"
                />
                <rect width={w} height={h} rx="7" className="node-box" />
                <g clipPath="url(#node-clip)">
                  <text className="node-type" x="14" y="19">{node.type}</text>
                  <text className="node-status" x={w - 12} y="19" textAnchor="end">
                    {node.status}
                  </text>
                  <text className="node-title" x="14" y="39">
                    {fitText(nodeTitle(node))}
                  </text>
                </g>
                <title>{`${node.type} · ${node.status} · ${node.assurance}\n${nodeTitle(node)}`}</title>
              </g>
            )
          })}
        </g>
      </svg>
    </div>
  )
}
