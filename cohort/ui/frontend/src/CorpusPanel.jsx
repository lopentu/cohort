import { explainProfileCodes } from './evidence-labels'
import { useEffect, useRef, useState } from 'react'
import { fetchCorpus, searchCorpus } from './api'
import Reveal from './Reveal'

// Browsing and searching the corpus, so the web UI can do what a script can.
//
// Two things this panel must not do, both of them tempting:
//
//   * It must not present results as ranked. `CbetaFtsIndex.search()` returns
//     corpus order and applies no relevance model on purpose (a BM25 ranking
//     would favour short commentaries over the scriptures they quote — a
//     scholarly judgement smuggled into infrastructure). A numbered list reads
//     as a ranking whether or not it is one, so the ordering is stated in
//     words and the count of what was *not* shown is stated too.
//
//   * It must not present an excerpt as a whole text. `fetch` truncates, and
//     the response says how many characters exist; a reader who cannot see
//     that would form conclusions about a witness from a fragment.
//
// Search runs as you type, debounced. Full-corpus search answers in ~65ms, so
// waiting for a submit adds latency the index does not have. Every response is
// tagged with the query that asked for it and a stale one is dropped, because
// debouncing alone does not stop an earlier request from landing last and
// showing results for a phrase the user has already moved on from.

export default function CorpusPanel({ onCite }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [openRef, setOpenRef] = useState(null)
  const [record, setRecord] = useState(null)
  const [stripMarkup, setStripMarkup] = useState(true)
  const latest = useRef('')

  const run = async (raw) => {
    const q = (raw ?? query).trim()
    if (!q) { setResults(null); setError(null); return }
    latest.current = q
    setBusy(true)
    setError(null)
    setRecord(null)
    setOpenRef(null)
    try {
      const data = await searchCorpus(q, 20)
      if (latest.current !== q) return   // a newer query is already in flight
      setResults(data)
    } catch (err) {
      if (latest.current !== q) return
      setError(err.message)
      setResults(null)
    } finally {
      if (latest.current === q) setBusy(false)
    }
  }

  // Debounce: 220ms is long enough that a fast typist sends one request per
  // word rather than per keystroke, short enough to feel like no wait at all.
  useEffect(() => {
    const q = query.trim()
    if (!q) { setResults(null); latest.current = ''; return undefined }
    const t = setTimeout(() => run(q), 220)
    return () => clearTimeout(t)
  }, [query])

  const open = async (ref, strip = stripMarkup) => {
    if (openRef === ref && strip === stripMarkup) {
      setOpenRef(null); setRecord(null); return
    }
    setOpenRef(ref)
    setRecord(null)
    try {
      setRecord(await fetchCorpus(ref, { stripMarkup: strip }))
    } catch (err) {
      setError(err.message)
    }
  }

  const toggleMarkup = async () => {
    const next = !stripMarkup
    setStripMarkup(next)
    if (openRef) {
      setRecord(null)
      try {
        setRecord(await fetchCorpus(openRef, { stripMarkup: next }))
      } catch (err) {
        setError(err.message)
      }
    }
  }

  return (
    <section className="corpus">
      <h2>Corpus</h2>
      <form className="corpus-form" onSubmit={(e) => { e.preventDefault(); run() }}>
        <input
          className="corpus-input"
          placeholder="exact phrase, e.g. 色即是空"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn" type="submit" disabled={!query.trim()}>
          {busy ? 'Searching…' : 'Search'}
        </button>
      </form>
      <p className="hint small">
        Exact substring match over every citable span. No wildcards, no
        stemming — what you type is what is found.
      </p>

      {error && <p className="error">{error}</p>}

      {results && (
        <>
          <div className="corpus-meta">
            <span><strong>{results.count}</strong> witnesses</span>
            <span className="ordering">{results.ordering}</span>
          </div>
          {results.truncated && (
            <p className="warn small">
              At least {results.count} matches — the list is cut at that point,
              so these are an arbitrary slice of the matching witnesses, not the
              most relevant ones. Narrow the phrase to see a meaningful set.
            </p>
          )}
          {results.count === 0 && (
            <p className="hint">
              No witness contains this phrase. That is a finding, not an
              error — it belongs in a conjecture, since only a retrieval can
              settle an absence.
            </p>
          )}
          <ul className="corpus-list">
            {results.hits.map((h) => (
              <li key={h.ref} className={openRef === h.ref ? 'open' : ''}>
                <div className="corpus-row">
                  <button className="corpus-ref" onClick={() => open(h.ref)}>
                    {h.title ? explainProfileCodes(h.title) : h.ref}
                  </button>
                  {h.cbeta_url && (
                    <a
                      className="btn tiny cbeta-link"
                      href={h.cbeta_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      title="Read this text in CBETA Online"
                    >
                      CBETA ↗
                    </a>
                  )}
                  {onCite && (
                    <button
                      className="btn tiny"
                      title="Use this phrase as an agent's task"
                      onClick={() => onCite(query.trim())}
                    >
                      send to agent
                    </button>
                  )}
                </div>
                {h.snippet && <p className="corpus-snippet">{h.snippet}</p>}
                <Reveal open={openRef === h.ref}>
                  <div className="corpus-record">
                    {!record ? (
                      <p className="hint">Loading…</p>
                    ) : (
                      <>
                        <div className="record-meta">
                          <code>{record.witness_ref}</code>
                          {record.locator && <span>{record.locator}</span>}
                          <span>
                            {record.truncated
                              ? `showing ${record.text.length} of ${record.total_chars} chars`
                              : `${record.total_chars} chars`}
                          </span>
                          <button className="btn tiny" onClick={toggleMarkup}>
                            {record.markup_stripped ? 'show TEI markup' : 'hide TEI markup'}
                          </button>
                        </div>
                        {record.markup_stripped && (
                          <p className="hint small">
                            Markup stripped for reading. Character offsets no
                            longer match the witness, so this view is for
                            reading only — never for locating a span.
                          </p>
                        )}
                        {/* The corpus is licensed; its terms travel with every
                            derived artifact, including this view. */}
                        {record.source_terms && (
                          <p className="terms">{record.source_terms}</p>
                        )}
                        <pre className="record-text">{record.text}</pre>
                        {record.truncated && (
                          <p className="warn small">
                            Truncated — this is a fragment of the witness, not
                            the whole text.
                          </p>
                        )}
                      </>
                    )}
                  </div>
                </Reveal>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
