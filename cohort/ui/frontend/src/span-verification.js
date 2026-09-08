// The API orders checks oldest first. A later failure must supersede a pass;
// repeated passes are audit history, not independent evidence.
export function spanVerification(checks = []) {
  const latest = checks.filter((v) => v.payload?.method === 'exact_span').at(-1)
  const p = latest?.payload
  const verified = p?.result === 'pass'
    && Number.isInteger(p.span_start) && Number.isInteger(p.span_end)
    && p.span_start >= 0 && p.span_end > p.span_start
  return { verified: !!verified, latest }
}

export function passageCheckIds(nodes, edges) {
  const passages = new Set(nodes.filter((n) => n.type === 'passage').map((n) => n.id))
  const checks = new Set(nodes.filter((n) => n.payload?.method === 'exact_span').map((n) => n.id))
  return new Set(edges.filter((e) => e.type === 'verifies' && passages.has(e.dst) && checks.has(e.src)).map((e) => e.src))
}
