import { useEffect, useMemo, useState } from 'react'
import { getEvidence, getEvidenceUnits } from './api'

// Where one text leans between translator profiles, painted onto the text.
//
// The panel is a reading aid, not a classifier's verdict. Things it must keep
// visible, because each was once the difference between a defensible number
// and a wrong one (cohort/attribution.py):
//
//   * how many units of the target's own Taishō work were withheld from the
//     profiles before counting — the rule that turned 82% into 52% — and how
//     much of each class is left afterwards, since a leaning toward a class
//     with two units left rests on almost nothing;
//   * which feature vocabulary produced the picture, since Radich's curated
//     list sees Dharmarakṣa well and the earliest translators barely at all;
//   * the ledger of what was discarded, beside the picker;
//   * raw counts beside every rate, because "988 per 100,000" can be ten
//     occurrences in a profile of a thousand tokens.
//
// Colour compares a *pinned pair* of translators, A (teal) against B (rust),
// not the leader against the runner-up: by default A is the text's own
// catalogue label. That is what lets the same text painted under two
// vocabularies mean the same thing in both — under one it may be rust, under
// the other teal, and that change is the finding. Painting "whoever is
// winning" in teal would make every text teal.

const FEATURE_LABEL = {
  radich: "Radich's curated strings",
  generic: 'commonest strings, no labels read',
  both: 'both together',
}
const ALPHA_CAP = 0.55   // above this the ink fails 4.5:1 contrast on both grounds

// The URL hash carries the selection so a view can be linked and reproduced.
function readHash() {
  const h = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  return { uid: h.get('uid') || null, features: h.get('features') || 'radich',
    withhold: h.get('withhold') || '', offset: Number(h.get('offset') || 0),
    pair: h.get('pair') || '' }
}
function writeHash(state) {
  const h = new URLSearchParams()
  if (state.uid) h.set('uid', state.uid)
  if (state.features !== 'radich') h.set('features', state.features)
  if (state.withhold) h.set('withhold', state.withhold)
  if (state.offset) h.set('offset', String(state.offset))
  if (state.pair) h.set('pair', state.pair)
  const next = '#' + h.toString()
  if (window.location.hash !== next) window.history.replaceState(null, '', next)
}

export default function EvidencePanel() {
  const initial = useMemo(readHash, [])
  const [units, setUnits] = useState(null)
  const [query, setQuery] = useState(initial.uid || '')
  const [uid, setUid] = useState(initial.uid)
  const [features, setFeatures] = useState(initial.features)
  const [withhold, setWithhold] = useState(initial.withhold)
  const [offset, setOffset] = useState(initial.offset)
  // 'A,B' pins which two classes the colours compare, so a link can paint a grey
  // text as tradition (A) against the leader (B) instead of leader vs runner-up.
  const [pair, setPair] = useState(initial.pair)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [showHow, setShowHow] = useState(!initial.uid)
  const [showLedger, setShowLedger] = useState(false)

  useEffect(() => {
    let live = true
    getEvidenceUnits()
      .then((u) => live && setUnits(u))
      .catch((e) => live && setError(e.message))
    return () => { live = false }
  }, [])

  useEffect(() => {
    writeHash({ uid, features, withhold, offset, pair })
    if (!uid) return undefined
    let live = true
    setBusy(true); setError(null)
    getEvidence(uid, features, { withhold, offset, pair })
      .then((d) => { if (live) { setData(d); setBusy(false) } })
      .catch((e) => { if (live) { setError(e.message); setData(null); setBusy(false) } })
    return () => { live = false }
  }, [uid, features, withhold, offset, pair])

  const choose = (u) => { setUid(u); setOffset(0) }

  // The picker: grey first, because grey is the question; then labelled units
  // for checking the method against texts whose translator is secure.
  const matches = useMemo(() => {
    if (!units) return []
    const q = query.trim().toLowerCase()
    const rows = units.units.filter((r) =>
      !q || r.uid.toLowerCase().includes(q) || r.label.toLowerCase().includes(q))
    rows.sort((a, b) => (a.label === 'grey') === (b.label === 'grey')
      ? a.uid.localeCompare(b.uid)
      : a.label === 'grey' ? -1 : 1)
    return rows.slice(0, 60)
  }, [units, query])

  return (
    <section className="evidence">
      <h2>Evidence</h2>
      <p className="hint">
        For one text: which short strings (2-4 characters) occur more often in one
        translator's securely ascribed work than another's, and where in the text
        they fall. A leaning with its reasons on show, not an attribution.
      </p>

      <button className="btn tiny" onClick={() => setShowHow((v) => !v)} aria-expanded={showHow}>
        {showHow ? 'hide' : 'show'} how to read this
      </button>
      {showHow && <HowToRead />}

      <div className="ev-controls">
        <label className="ev-filter">
          <span className="visually-hidden">filter units</span>
          <input
            className="corpus-input"
            placeholder="filter by unit id or label, e.g. T0603, grey, ASg"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="ev-features" role="radiogroup" aria-label="feature vocabulary">
          {Object.entries(FEATURE_LABEL).map(([k, label]) => (
            <button
              key={k}
              role="radio"
              aria-checked={features === k}
              className={`btn tiny ${features === k ? 'on' : ''}`}
              onClick={() => setFeatures(k)}
            >{label}</button>
          ))}
        </div>
      </div>

      {units && (
        <div className="ev-picker">
          <ul className="ev-units">
            {matches.map((r) => (
              <li key={r.uid}>
                <button
                  className={`ev-unit ${uid === r.uid ? 'on' : ''}`}
                  onClick={() => choose(r.uid)}
                  title={`${r.uid} — ${r.profiled ? 'in the profiles; its whole work is withheld when judged' : 'not in the profiles'}`}
                >
                  <span className="ev-uid">{r.uid}</span>
                  <span className={`ev-label ${r.label === 'grey' ? 'grey' : ''}`}>{r.label}</span>
                  <span className="ev-chars">{r.han_chars.toLocaleString()}</span>
                </button>
              </li>
            ))}
            {matches.length === 60 && <li className="hint small">first 60 shown; narrow the filter</li>}
          </ul>
          <div className="ev-ledger">
            <button className="btn tiny" onClick={() => setShowLedger((v) => !v)} aria-expanded={showLedger}>
              {showLedger ? 'hide' : 'show'} what was discarded
            </button>
            {showLedger && (
              <table className="ev-table">
                <tbody>
                  {Object.entries(units.ledger).map(([k, v]) => (
                    <tr key={k}><td>{k}</td><td className="num">{v.toLocaleString()}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
            {showLedger && units.notes.map((n) => <p key={n} className="hint small">{n}</p>)}
          </div>
        </div>
      )}

      <div aria-live="polite">
        {error && <p className="error">{error}</p>}
        {busy && <p className="hint">Counting…</p>}
      </div>
      {data && !busy && (
        <Reading
          data={data}
          sequence={units?.sequence || []}
          withhold={withhold}
          onWithhold={setWithhold}
          pair={pair}
          onPair={setPair}
          onOffset={setOffset}
        />
      )}
    </section>
  )
}

function HowToRead() {
  return (
    <div className="ev-how">
      <p>
        <b>What is counted.</b> Every 2-, 3- and 4-character string in the text that
        is in the chosen vocabulary. Each carries a weight: the log of how many times
        more likely that string is in translator A's securely ascribed work than in
        B's. A weight of +3 means about 20 times more likely; +7 about 1,000 times.
        A string at 33 per 100,000 in one profile and 0 in the other carries a
        large weight; one at 12 and 11 carries almost none.
      </p>
      <p>
        <b>What the colours mean.</b> <span className="ev-swatch a" /> spans pull toward
        translator A, <span className="ev-swatch b" /> spans toward translator B.
        A is the text's own catalogue label when it has one, otherwise the leading
        candidate; B is the strongest rival. The pair stays fixed when you switch
        vocabularies, so a change of colour is a change of evidence. Saturation is
        the weight of evidence on that character.
      </p>
      <p>
        <b>The strip</b> is the whole text, one cell per few hundred characters. Click a
        cell to read that part of the text. A text that changes colour part-way changes
        <em> something</em>: most often subject or genre, sometimes the hand.
      </p>
      <p>
        <b>What is withheld.</b> If the text is a chapter of a labelled work, every
        chapter of that work is removed from the profiles first. Otherwise the method
        recognises the book, not the translator; that mistake once read as 82%
        accuracy where the honest figure was 52%. You can withhold further units by
        id (a commentary you suspect of quoting the text, say) and watch what survives.
      </p>
      <p>
        <b>Why two vocabularies.</b> Radich's list was harvested for a Dharmarakṣa
        dictionary; it barely sees An Shigao. The label-free strings are the commonest
        in the grey texts, chosen without reading a label. Switch and compare.
      </p>
      <p>
        <b>What it is not.</b> "No evidence" means not one string of the vocabulary occurs
        in the text; nothing is ranked. A margin near zero is "nothing either way", not a
        weak attribution. A text composed in Chinese has no translator to find. The
        researcher reads; the panel only points.
      </p>
    </div>
  )
}

function rgba(which, a) {
  return `rgba(var(--ev-${which}-rgb), ${Math.max(0, Math.min(a, ALPHA_CAP)).toFixed(2)})`
}

function Reading({ data, sequence, withhold, onWithhold, pair: pinnedPair, onPair, onOffset }) {
  const [withholdDraft, setWithholdDraft] = useState(withhold)
  useEffect(() => { setWithholdDraft(withhold) }, [withhold])
  const [pairDraft, setPairDraft] = useState(pinnedPair)
  useEffect(() => { setPairDraft(pinnedPair) }, [pinnedPair])

  const pair = data.pair
  const a = pair?.a, b = pair?.b
  const scale = data.scale || 1
  const stripScale = data.strip_scale || 1

  // One span per run of equal colour bucket, so a 2,400-character excerpt is a
  // few hundred spans rather than 2,400. Array.from iterates code points, which
  // is what keeps the paint aligned with the server's per-code-point evidence
  // when the text contains supplementary-plane characters.
  const spans = useMemo(() => {
    const out = []
    let run = ''; let cur = null
    const bucket = (e) => (e ? `${e > 0 ? 'a' : 'b'}${Math.min(6, Math.round(Math.abs(e) / scale * 6))}` : null)
    const chars = Array.from(data.excerpt.text)
    chars.forEach((ch, i) => {
      // Line breaks in the source file would collapse to visible gaps between
      // CJK characters; drop them from the display but keep the index aligned.
      if (ch === '\n' || ch === '\r') return
      const bk = bucket(data.excerpt.evidence[i] ?? 0)
      if (bk !== cur && run) { out.push([cur, run]); run = '' }
      cur = bk; run += ch
    })
    if (run) out.push([cur, run])
    return out
  }, [data, scale])

  const bucketColour = (bk) => (bk ? rgba(bk[0], (parseInt(bk.slice(1), 10) / 6) * ALPHA_CAP) : 'transparent')
  const seq = (lab) => { const i = sequence.indexOf(lab); return i >= 0 ? `#${i + 1} of ${sequence.length} in Radich's order` : '' }
  const excerptEnd = data.excerpt.end ?? (data.excerpt.start + Array.from(data.excerpt.text).length)

  return (
    <div className="ev-reading">
      <div className="ev-head">
        <h3>{data.uid} <span className="hint small">catalogue label <b>{data.label}</b></span></h3>
        <p className="hint small">
          {data.han_chars.toLocaleString()} Han characters ({data.code_points.toLocaleString()} code points)
          · {data.hits.toLocaleString()} feature hits · {data.distinct.toLocaleString()} distinct
          · vocabulary: {FEATURE_LABEL[data.features]} ({data.n_features.toLocaleString()} strings)
          {data.withheld_units > 0 && (
            <> · <b>{data.withheld_units} unit{data.withheld_units > 1 ? 's' : ''} withheld</b> from the profiles
              {data.withheld_extra.length > 0 && <> (incl. {data.withheld_extra.join(', ')})</>}</>
          )}
        </p>
      </div>

      <form
        className="ev-withhold"
        onSubmit={(e) => { e.preventDefault(); onWithhold(withholdDraft.trim()) }}
      >
        <label>
          <span className="hint small">also withhold (unit ids, comma-separated), the sensitivity test:</span>
          <input
            className="corpus-input"
            value={withholdDraft}
            placeholder="e.g. T1694"
            onChange={(e) => setWithholdDraft(e.target.value)}
          />
        </label>
        <button className="btn tiny" type="submit">recompute</button>
        {withhold && <button className="btn tiny" type="button" onClick={() => onWithhold('')}>clear</button>}
      </form>

      <form
        className="ev-withhold"
        onSubmit={(e) => { e.preventDefault(); onPair(pairDraft.replace(/\s+/g, '')) }}
      >
        <label>
          <span className="hint small">paint A against B (two class labels, A,B); empty = label or leader vs strongest rival:</span>
          <input
            className="corpus-input"
            value={pairDraft}
            placeholder="e.g. Dhr,ZFn"
            onChange={(e) => setPairDraft(e.target.value)}
          />
        </label>
        <button className="btn tiny" type="submit">repaint</button>
        {pinnedPair && <button className="btn tiny" type="button" onClick={() => onPair('')}>clear</button>}
      </form>

      {data.verdict === 'no evidence' ? (
        <div className="ev-verdict">
          <div><b className="warn">no evidence</b>
            <span className="hint small"> not one string of this vocabulary occurs in the text; nothing is ranked</span></div>
        </div>
      ) : (
        <div className="ev-verdict">
          <div><span className="hint small">leans</span><b>{data.first}</b><span className="hint small">{seq(data.first)}</span></div>
          <div><span className="hint small">over</span><b>{data.second}</b><span className="hint small">{seq(data.second)}</span></div>
          <div>
            <span className="hint small">margin</span>
            <b>{data.margin > 0 ? '+' : ''}{data.margin.toFixed(2)}</b>
            <span className="hint small">log-odds per distinct string; not comparable across texts</span>
          </div>
          {data.verdict === 'low evidence' && (
            <div><b className="warn">low evidence</b><span className="hint small">fewer than 10 distinct strings</span></div>
          )}
        </div>
      )}

      {data.verdict !== 'no evidence' && (
        <details className="ev-ranking">
          <summary className="hint small">all {data.ranking.length} candidates, and what is left of each profile</summary>
          <table className="ev-table">
            <thead><tr><th className="g">class</th><th>Δ log-likelihood</th><th>units left</th><th>feature tokens</th><th>order</th></tr></thead>
            <tbody>
              {data.ranking.map((r) => {
                const p = data.profiles[r.label] || {}
                return (
                  <tr key={r.label} className={p.thin ? 'thin' : ''}>
                    <td className="g">{r.label}{p.thin && <span className="warn small"> thin</span>}</td>
                    <td className="num">{r.delta.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                    <td className="num">{p.units} of {p.units_before_withholding}</td>
                    <td className="num">{(p.feature_tokens ?? 0).toLocaleString()}</td>
                    <td className="num">{p.sequence != null ? p.sequence + 1 : ''}</td>
                  </tr>
                )
              })}
              {data.no_profile.map((n) => (
                <tr key={n.label}><td className="g">{n.label}</td><td colSpan="4" className="hint small">not judged: {n.reason}</td></tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {pair && (
        <p className="hint small">
          Painted pair: <b className="ev-a">{a}</b> (A) vs <b className="ev-b">{b}</b> (B)
          {pair.pinned ? ', pinned' : a === data.label ? ', the catalogue label vs its strongest rival' : ', the leader vs its strongest rival'}.
          Profiles hold {data.profiles[a].feature_tokens.toLocaleString()} and {data.profiles[b].feature_tokens.toLocaleString()} feature tokens.
        </p>
      )}

      <p className="hint small">
        Whole text, one cell per {data.strip_cell.toLocaleString()} characters. Click a cell to read that part.
      </p>
      <div className="ev-strip" role="group" aria-label="evidence across the whole text">
        {data.strip.map((c) => (
          <button
            key={c.start}
            type="button"
            className={`ev-cell ${c.start <= data.excerpt.start && data.excerpt.start < c.end ? 'here' : ''}`}
            title={`characters ${c.start.toLocaleString()}–${c.end.toLocaleString()}: ${c.mean > 0 ? 'toward ' + a : c.mean < 0 ? 'toward ' + b : 'nothing'} (${c.mean > 0 ? '+' : ''}${c.mean.toFixed(3)})`}
            aria-label={`characters ${c.start} to ${c.end}`}
            style={{ background: c.mean ? rgba(c.mean > 0 ? 'a' : 'b', Math.abs(c.mean) / stripScale * ALPHA_CAP) : 'transparent' }}
            onClick={() => onOffset(c.start)}
          />
        ))}
      </div>

      <p className="hint small">
        Characters {data.excerpt.start.toLocaleString()}–{excerptEnd.toLocaleString()}.
        Saturation is capped at the 95th percentile of evidence weight.
        {data.excerpt.start > 0 && <> <button className="btn tiny" type="button" onClick={() => onOffset(0)}>back to the start</button></>}
      </p>
      <div className="ev-text" lang="zh-Hant">
        {spans.map(([bk, s], i) => bk
          ? <mark key={i} className={bk[0] === 'a' ? 'a' : 'b'} style={{ background: bucketColour(bk) }}>{s}</mark>
          : <span key={i}>{s}</span>)}
      </div>

      {pair && (
        <div className="ev-cols">
          <EvidenceTable title={`for ${a}`} rows={data.for} a={a} b={b} />
          <EvidenceTable title={`for ${b}`} rows={data.against} a={a} b={b} />
        </div>
      )}
      <p className="hint small">
        Weight = hits × log-odds of the string in A's profile versus B's, add-half
        smoothing. "n" is the raw count in that profile; the rate is per 100,000
        <em> feature tokens</em> in that profile (hits of any vocabulary string), not
        per 100,000 characters. Overlapping 2-, 3- and 4-character strings are
        counted separately and are not independent, so weights overstate certainty;
        read them as a ranking. Strings absent from both profiles are not shown.
      </p>
    </div>
  )
}

function EvidenceTable({ title, rows, a, b }) {
  return (
    <div>
      <table className="ev-table">
        <thead>
          <tr>
            <th className="g">{title}</th><th>hits</th>
            <th title="raw count, and per 100,000 feature tokens in that profile">{a} n · /100k</th>
            <th title="raw count, and per 100,000 feature tokens in that profile">{b} n · /100k</th>
            <th>weight</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.gram}>
              <td className="g" lang="zh-Hant">{r.gram}</td>
              <td className="num">{r.hits}</td>
              <td className="num">{r.count_a} · {r.rate_a.toFixed(1)}</td>
              <td className="num">{r.count_b} · {r.rate_b.toFixed(1)}</td>
              <td className="num">{r.weight > 0 ? '+' : ''}{r.weight.toFixed(1)}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan="5" className="hint small">nothing pulls this way</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
