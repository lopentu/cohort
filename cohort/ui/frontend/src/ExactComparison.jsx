import { useEffect, useState } from 'react'
import { fetchCorpus } from './api'
import { explainProfileCodes } from './evidence-labels'
import CbetaLink from './CbetaLink'

export default function ExactComparison({ selections, onRemove, onClear }) {
  if (!selections.length) return null
  return <section className="exact-comparison" aria-label="Compare exact-search results">
    <div className="exact-comparison-heading">
      <h3>Compare passages · {selections.length}/2</h3>
      <button className="btn tiny" onClick={onClear}>Clear comparison</button>
    </div>
    <div className="exact-comparison-columns">
      {selections.map(hit => <ComparisonPassage key={hit.ref} hit={hit} onRemove={onRemove} />)}
      {selections.length === 1 && <p className="exact-comparison-empty">Choose Compare on another result.</p>}
    </div>
  </section>
}

function ComparisonPassage({ hit, onRemove }) {
  const [record, setRecord] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    let live = true
    fetchCorpus(hit.ref, { stripMarkup: true }).then(data => {
      if (live) setRecord(data)
    }).catch(err => { if (live) setError(err.message) })
    return () => { live = false }
  }, [hit.ref])
  return <article className="exact-comparison-passage">
    <header>
      <h4>{explainProfileCodes(hit.title || hit.ref)}</h4>
      <button className="btn tiny" onClick={() => onRemove(hit.ref)} aria-label={`Remove ${hit.title || hit.ref} from comparison`}>Remove</button>
    </header>
    <CbetaLink url={hit.cbeta_url} />
    <div className="exact-comparison-scroll" tabIndex="0" aria-label={`Passage from ${hit.title || hit.ref}`}>
      {hit.snippet && <>
        <p className="hint small">Search excerpt · {hit.phrase}</p>
        <p className="exact-search-excerpt" lang="zh"><PhraseText text={hit.snippet} phrase={hit.phrase} /></p>
      </>}
      {error ? <p className="error" role="alert">{error}</p> : !record ? <p className="hint">Loading source…</p> : <>
        <p className="hint small">{record.truncated ? `Source opening: first ${Array.from(record.text).length.toLocaleString()} of ${record.total_chars.toLocaleString()} characters.` : 'Source text.'} Markup hidden; display positions differ from the source.</p>
        {record.locator && <p className="hint small">{record.locator}</p>}
        <pre className="record-text" lang="zh"><PhraseText text={record.text} phrase={hit.phrase} /></pre>
        {record.source_terms && <p className="terms">{record.source_terms}</p>}
      </>}
    </div>
  </article>
}

function PhraseText({ text, phrase }) {
  if (!phrase) return text
  const parts = text.split(phrase)
  return parts.map((part, i) => <span key={i}>{i > 0 && <mark className="related-shared-mark">{phrase}</mark>}{part}</span>)
}
