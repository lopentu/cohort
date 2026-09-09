// Node and agent ids are opaque and routinely contain `#` (a passage's ref is
// `{witness}#{excerpt}`), so they travel as encoded query parameters, never as
// path segments — see cohort/ui/api.py's `/api/node` docstring.
const json = async (url, options) => {
  const res = await fetch(url, options)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = body.detail
    // A refused write answers with {rule, message}: the rule is the whole
    // point (it names the commitment that declined), so it must survive into
    // the message the researcher reads rather than being flattened to a code.
    const err = new Error(
      typeof detail === 'object' && detail !== null
        ? `${detail.rule}: ${detail.message}`
        : detail || `${res.status} ${res.statusText}`,
    )
    err.status = res.status
    err.rule = typeof detail === 'object' && detail !== null ? detail.rule : null
    throw err
  }
  return res.json()
}

export const getHealth = () => json('/api/health')
export const getGraph = (limit = 5000) => json(`/api/graph?limit=${limit}`)
export const getNode = (id) => json(`/api/node?id=${encodeURIComponent(id)}`)
export const getAgent = (id) => json(`/api/agent?id=${encodeURIComponent(id)}`)
export const getRefusals = (limit = 100) => json(`/api/refusals?limit=${limit}`)
export const getCitable = () => json('/api/citable')
export const getRejected = () => json('/api/rejected')
export const getIntegrity = () => json('/api/integrity')
export const getRebuild = () => json('/api/rebuild')

const post = (path, id, body) =>
  json(`${path}?id=${encodeURIComponent(id)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  })

export const attestNode = (id) => post('/api/attest', id)
export const acceptNode = (id) => post('/api/accept', id)
export const rejectNode = (id, reason) => post('/api/reject', id, { reason })
export const reopenNode = (id, reason) => post('/api/reopen', id, { reason })
export const retractEdge = (id, reason) => post('/api/edge/retract', id, { reason })
export const restoreEdge = (id, reason) => post('/api/edge/restore', id, { reason })

// --- corpus (read-only; the same source.search()/fetch() Python calls) ------
export const searchCorpus = (q, limit = 20) =>
  json(`/api/corpus/search?q=${encodeURIComponent(q)}&limit=${limit}`)
// `strip_markup` is display-only and the response says so; the panel makes it
// a visible toggle rather than a silent default, because stripped text no
// longer shares offsets with the witness.
export const fetchCorpus = (ref, { maxChars = 4000, stripMarkup = true } = {}) =>
  json(
    `/api/corpus/fetch?ref=${encodeURIComponent(ref)}` +
    `&max_chars=${maxChars}&strip_markup=${stripMarkup}`,
  )
// A passage in context — chars of source text on each side of its recorded
// excerpt, re-fetched live rather than trusted from the stored (often tiny)
// excerpt. 404s for a passage with no source_ref/excerpt to re-fetch from;
// the caller treats that as "no context available", not an error.
export const getPassageContext = (id, window = 10) =>
  json(`/api/passage/context?id=${encodeURIComponent(id)}&window=${window}`)

// --- agent runs (the only calls that spend money) ---------------------------
export const getRunConfig = () => json('/api/run/config')
export const getRuns = () => json('/api/run')
export const startRun = (body) =>
  json('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
export const stopRun = () => json('/api/run/stop', { method: 'POST' })

export const getFindings = (limit) =>
  json(`/api/findings${limit ? `?limit=${limit}` : ''}`)
export const getDossier = (id) => json(`/api/findings?id=${encodeURIComponent(id)}`)

export const getQuestions = (id) =>
  json(`/api/questions${id ? `?id=${encodeURIComponent(id)}` : ''}`)
export const askQuestion = (body) =>
  json('/api/questions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

// --- attribution evidence (read-only; the same AttributionIndex the CLI uses) -
export const getEvidenceUnits = () => json('/api/evidence/units')
export const getEvidence = (uid, features = 'radich', { withhold = '', offset = 0, pair = '' } = {}) =>
  json(
    `/api/evidence?uid=${encodeURIComponent(uid)}&features=${encodeURIComponent(features)}` +
    `&withhold=${encodeURIComponent(withhold)}&offset=${offset}&pair=${encodeURIComponent(pair)}`,
  )

export const getRelated = (uid, start = 0) => json(uid
  ? `/api/corpus/related?uid=${encodeURIComponent(uid)}&start=${start}`
  : '/api/corpus/related')
