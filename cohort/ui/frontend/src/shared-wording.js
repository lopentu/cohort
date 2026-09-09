// Source offsets count Unicode code points; JS string offsets count UTF-16
// units. Array.from keeps supplementary Chinese characters correctly aligned.
export function sharedWordingSegments(text, start, runs, side) {
  const chars = Array.from(text)
  const ranges = runs.map(run => [Math.max(0, run[`${side}_start`] - start), Math.min(chars.length, run[`${side}_end`] - start)])
    .filter(([a, b]) => a < b).sort((a, b) => a[0] - b[0])
  const merged = []
  for (const [a, b] of ranges) {
    const last = merged.at(-1)
    if (last && a <= last[1]) last[1] = Math.max(last[1], b)
    else merged.push([a, b])
  }
  const parts = []
  let cursor = 0
  for (const [a, b] of merged) {
    if (cursor < a) parts.push({ text: chars.slice(cursor, a).join(''), shared: false })
    parts.push({ text: chars.slice(a, b).join(''), shared: true })
    cursor = b
  }
  if (cursor < chars.length) parts.push({ text: chars.slice(cursor).join(''), shared: false })
  return parts
}
