import CbetaLink from './CbetaLink'
import { useEffect, useRef, useState } from 'react'
import { getRelated } from './api'
import { textName } from './evidence-labels'

export default function RelatedPanel() {
  const [config, setConfig] = useState(null)
  const [uid, setUid] = useState('T0263-rest')
  const [start, setStart] = useState(0)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const request = useRef(0)
  useEffect(() => {
    let live = true
    getRelated().then(x => { if (live) setConfig(x) }).catch(e => { if (live) setError(e.message) })
    return () => { live = false; request.current++ }
  }, [])
  const search = async (target = uid, position = start) => {
    const id = ++request.current
    setUid(target); setStart(position); setBusy(true); setError(null); setResult(null)
    try {
      const data = await getRelated(target, position)
      if (id === request.current) setResult(data)
    } catch (e) { if (id === request.current) setError(e.message) }
    finally { if (id === request.current) setBusy(false) }
  }
  const change = (value) => {
    request.current++; setUid(value); setStart(0); setResult(null); setBusy(false)
  }
  return <div className="related-panel">
    <p>Find passages with similar content in other works. Start from an indexed text, not a typed research question.</p>
    {error && <p className="error" role="alert">{error}</p>}
    {!config ? <p className="hint">Loading index…</p> : !config.enabled ? <p className="hint">{config.reason}</p> : <>
      <p className="hint small"><b>Embedding model (from filename):</b> {config.model_from_filename}<br />
        {config.units.length.toLocaleString()} indexed texts/chapters · {config.windows.toLocaleString()} passages · {config.window_chars}-character windows</p>
      <details><summary>Model and search method</summary>
        <p>{config.method}. Higher values mean closer vectors, not a probability of a textual relationship.</p>
        <p>{config.provenance_note} This index covers selected local material, not all of CBETA. No new embeddings or paid model calls are made here.</p>
        <p>The search excludes all units of the target’s Taishō work. Different units of another work may still appear together.</p>
      </details>
      <form className="related-form" onSubmit={e => { e.preventDefault(); search() }}>
        <label>Indexed text<select aria-label="Indexed text" value={config.units.includes(uid) ? uid : ''} onChange={e => change(e.target.value)}>
          <option value="" disabled>Select a text</option>
          {config.units.map(u => <option key={u} value={u}>{textName(u)}</option>)}
        </select></label>
        <label>Source position<input type="number" min="0" step={config.window_chars} value={start}
          onChange={e => { request.current++; setStart(Number(e.target.value)); setResult(null); setBusy(false) }} /></label>
        <button className="btn" disabled={busy || !config.units.includes(uid)}>{busy ? 'Searching…' : 'Find related passages'}</button>
      </form>
      <div className="suggested-inputs">
        {[
          ['T0263-rest', 'Lotus Sūtra · Dharmarakṣa', 4000],
          ['T0603', 'Body, mind and senses · T0603'],
          ['T0453', 'Maitreya · T0453'],
        ].filter(([u]) => config.units.includes(u)).map(([u, label, position = 0]) =>
          <button className="btn tiny" key={u} onClick={() => search(u, position)}>{label}</button>)}
      </div>
    </>}
    {result && <>
      <div className="related-comparison">
      <section className="related-selected" aria-label="Selected passage" tabIndex="0">
      <h3>Selected passage · {textName(result.query.uid)}</h3>
      <p className="hint small">Source characters {result.query.start}–{result.query.end} (zero-based, end excluded)</p>
      <CbetaLink url={result.query.cbeta_url} />
      <p className="related-text" lang="zh">{result.query.text}</p>
      <div className="related-navigation">
        <button className="btn tiny" disabled={result.positions.indexOf(start) <= 0}
          onClick={() => search(uid, result.positions[result.positions.indexOf(start) - 1])}>Previous passage</button>
        <button className="btn tiny" disabled={result.positions.indexOf(start) >= result.positions.length - 1}
          onClick={() => search(uid, result.positions[result.positions.indexOf(start) + 1])}>Next passage</button>
      </div>
      </section>
      <section className="related-results" aria-label="Related passage results" tabIndex="0">
      <h3>Related passages</h3>
      <p className="hint small">Showing {result.matches.length} of {result.candidate_windows.toLocaleString()} candidate passages, ranked by cosine similarity.</p>
      {!result.matches.length && <p>No passages from other works are indexed.</p>}
      {result.matches.map((m, i) => <article className="related-match" key={`${m.uid}:${m.start}`}>
        <h4>{i + 1}. {textName(m.uid)} <span className="hint small">Cosine {m.cosine.toFixed(3)}</span></h4>
        <p className="hint small">{m.uid} · Source characters {m.start}–{m.end}</p>
        <CbetaLink url={m.cbeta_url} />
        <p className="related-text" lang="zh">{m.text}</p>
        <details><summary>Check shared wording</summary>
          <p>Longest shared sequence: {m.longest_shared_run} Chinese characters. Punctuation is ignored; only these two displayed passages are compared.</p>
          {m.shared_runs.length ? <ul>{m.shared_runs.map((r, j) => <li key={j}>
            <span lang="zh">{r.text}</span> · {r.chars} characters<br />
            Selected text: {r.a_start}–{r.a_end} · Related text: {r.b_start}–{r.b_end}
          </li>)}</ul> : <p>No shared sequence of four or more Chinese characters.</p>}
        </details>
      </article>)}
      </section>
      </div>
      <details><summary>Source checks and limits</summary>
        <p>{result.limitations}</p>
        <p>Positions refer to the local base texts, not CBETA page and line numbers. End positions are excluded. Source hashes below describe the files read for this result.</p>
        {[result.query, ...result.matches].map((p, i) => <p className="related-hash" key={i}>{p.uid}: {p.source_sha256}</p>)}
      </details>
    </>}
  </div>
}
