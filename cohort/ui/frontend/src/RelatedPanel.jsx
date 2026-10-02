import { Button } from './components/ui'
import { useTranslation } from 'react-i18next'
import { tr, formatNumber } from './i18n'
import CbetaLink from './CbetaLink'
import { useEffect, useRef, useState } from 'react'
import { getRelated } from './api'
import { textName } from './evidence-labels'
import { sharedWordingSegments } from './shared-wording'

export default function RelatedPanel({ onInvestigate }) {
  useTranslation()
  const [config, setConfig] = useState(null)
  const [uid, setUid] = useState('T0263-rest')
  const [start, setStart] = useState(0)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [wordingIndex, setWordingIndex] = useState(null)
  const request = useRef(0)
  useEffect(() => {
    let live = true
    getRelated().then(x => { if (live) setConfig(x) }).catch(e => { if (live) setError(e.message) })
    return () => { live = false; request.current++ }
  }, [])
  const search = async (target = uid, position = start) => {
    const id = ++request.current
    setUid(target); setStart(position); setBusy(true); setError(null); setResult(null); setWordingIndex(null)
    try {
      const data = await getRelated(target, position)
      if (id === request.current) setResult(data)
    } catch (e) { if (id === request.current) setError(e.message) }
    finally { if (id === request.current) setBusy(false) }
  }
  const change = (value) => {
    request.current++; setUid(value); setStart(0); setResult(null); setBusy(false)
  }
  const activeMatch = result?.matches[wordingIndex] ?? null
  return <div className="related-panel">
    <p>{tr("Find passages with similar content in other works. Start from an indexed text, not a typed research question.")}</p>
    {error && <p className="error" role="alert">{error}</p>}
    {!config ? <p className="hint">{tr("Loading index…")}</p> : !config.enabled ? <p className="hint">{config.reason}</p> : <>
      <p className="hint small"><b>{tr("Embedding model (from filename):")}</b> {config.model_from_filename}<br />
        {formatNumber(config.units.length)} {tr("indexed texts/chapters ·")} {formatNumber(config.windows)} {tr("passages ·")} {config.window_chars}{tr("-character windows")}</p>
      <details><summary>{tr("Model and search method")}</summary>
        <p>{config.method}{tr(". Higher values mean closer vectors, not a probability of a textual relationship.")}</p>
        <p>{config.provenance_note} {tr("This index covers selected local material, not all of CBETA. No new embeddings or paid model calls are made here.")}</p>
        <p>{tr("The search excludes all units of the target’s Taishō work. Different units of another work may still appear together.")}</p>
      </details>
      <form className="related-form" onSubmit={e => { e.preventDefault(); search() }}>
        <label>{tr("Indexed text")}<select aria-label={tr("Indexed text")} value={config.units.includes(uid) ? uid : ''} onChange={e => change(e.target.value)}>
          <option value="" disabled>{tr("Select a text")}</option>
          {config.units.map(u => <option key={u} value={u}>{textName(u)}</option>)}
        </select></label>
        <label>{tr("Source position")}<input type="number" min="0" step={config.window_chars} value={start}
          onChange={e => { request.current++; setStart(Number(e.target.value)); setResult(null); setBusy(false) }} /></label>
        <Button type="submit" className="btn" disabled={busy || !config.units.includes(uid)}>{busy ? tr("Searching…") : tr("Find related passages")}</Button>
      </form>
      <div className="suggested-inputs">
        {[
          ['T0263-rest', tr("Lotus Sūtra · Dharmarakṣa"), 4000],
          ['T0603', tr("Body, mind and senses · T0603")],
          ['T0453', tr("Maitreya · T0453")],
        ].filter(([u]) => config.units.includes(u)).map(([u, label, position = 0]) =>
          <Button className="btn tiny" key={u} onClick={() => search(u, position)}>{label}</Button>)}
      </div>
    </>}
    {result && <>
      <div className="related-comparison">
      <section className="related-selected" aria-label={tr("Selected passage")} tabIndex="0">
      <h3>{tr("Selected passage ·")} {textName(result.query.uid)}</h3>
      <p className="hint small">{tr("Source characters")} {result.query.start}–{result.query.end} {tr("(zero-based, end excluded)")}</p>
      <CbetaLink url={result.query.cbeta_url} />
      {activeMatch && <p className="hint small" role="status">{tr("Shared wording with result")} {wordingIndex + 1} · {textName(activeMatch.uid)}</p>}
      <p className="related-text" lang="zh" id="related-selected-text"><SharedText passage={result.query} runs={activeMatch?.shared_runs || []} side="a" /></p>
      <div className="related-navigation">
        <Button className="btn tiny" disabled={result.positions.indexOf(start) <= 0}
          onClick={() => search(uid, result.positions[result.positions.indexOf(start) - 1])}>{tr("Previous passage")}</Button>
        <Button className="btn tiny" disabled={result.positions.indexOf(start) >= result.positions.length - 1}
          onClick={() => search(uid, result.positions[result.positions.indexOf(start) + 1])}>{tr("Next passage")}</Button>
      </div>
      </section>
      <section className="related-results" aria-label={tr("Related passage results")} tabIndex="0">
      <h3>{tr("Related passages")}</h3>
      <p className="hint small">{tr("Showing")} {result.matches.length} {tr("of")} {formatNumber(result.candidate_windows)} {tr("candidate passages, ranked by cosine similarity.")}</p>
      {!result.matches.length && <p>{tr("No passages from other works are indexed.")}</p>}
      {result.matches.map((m, i) => <article className="related-match" key={`${m.uid}:${m.start}`}>
        <h4>{i + 1}. {textName(m.uid)} <span className="hint small">{tr("Cosine")} {m.cosine.toFixed(3)}</span></h4>
        <p className="hint small">{m.uid} {tr("· Source characters")} {m.start}–{m.end}</p>
        <CbetaLink url={m.cbeta_url} />
        <div className="related-match-actions">
        <Button className="btn related-wording" type="button"
          aria-pressed={wordingIndex === i} aria-controls={`related-selected-text related-result-text-${i}`}
          onClick={() => setWordingIndex(current => current === i ? null : i)}>
          <span aria-hidden="true">{wordingIndex === i ? '✓' : '▧'}</span>{tr("Shared wording")}<span className="related-wording-count" title={tr("Longest shared sequence of Chinese characters")}>{m.longest_shared_run} {tr("chars")}</span>
        </Button>
        {onInvestigate && <Button className="btn related-investigate" type="button"
          title={tr("Open an editable Inquiry question with both passages")}
          onClick={() => onInvestigate({ kind: 'passage-pair', selected: result.query, match: m })}>{tr("Investigate this pair")}<span aria-hidden="true">→</span>
        </Button>}
        </div>
        {wordingIndex === i && <p className="hint small" role="status">
          {m.shared_runs.length ? tr("Matching sequences of 4+ Chinese characters are highlighted in both excerpts. Punctuation is ignored.") : tr("No shared sequence of 4+ Chinese characters to highlight in these excerpts.")}
        </p>}
        <p className="related-text" lang="zh" id={`related-result-text-${i}`}><SharedText passage={m} runs={wordingIndex === i ? m.shared_runs : []} side="b" /></p>
      </article>)}
      </section>
      </div>
      <details><summary>{tr("Source checks and limits")}</summary>
        <p>{result.limitations}</p>
        <p>{tr("Positions refer to the local base texts, not CBETA page and line numbers. End positions are excluded. Source hashes below describe the files read for this result.")}</p>
        {[result.query, ...result.matches].map((p, i) => <p className="related-hash" key={i}>{p.uid}: {p.source_sha256}</p>)}
      </details>
    </>}
  </div>
}

function SharedText({ passage, runs, side }) {
  return sharedWordingSegments(passage.text, passage.start, runs, side).map((part, i) =>
    part.shared ? <mark className="related-shared-mark" key={i}>{part.text}</mark> : part.text)
}
