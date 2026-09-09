import CbetaLink from './CbetaLink'
import { useEffect, useMemo, useState } from 'react'
import { getEvidence, getEvidenceUnits } from './api'
import { profileName, textName } from './evidence-labels'

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
// Colours compare two named groups, which may include a mixed corpus class.
// Only an explicit pair stays fixed across vocabulary changes. Keep the pair
// labels visible so automatic selection cannot masquerade as changed evidence.

const FEATURE_LABEL = {
  radich: "Radich's list for the Dharmarakṣa dictionary",
  generic: 'Frequent corpus strings',
  both: 'Combined lists',
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

export default function EvidencePanel({ onSelection }) {
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
  const [showHow, setShowHow] = useState(false)
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

  useEffect(() => {
    onSelection?.(data && !busy ? {view:'evidence',uid:data.uid,features:data.features,withhold:data.withheld_extra,pair:data.pair ? [data.pair.a,data.pair.b] : null} : null)
  }, [data,busy,onSelection])

  const choose = (u) => { setUid(u); setOffset(0) }

  // The picker: grey first, because grey is the question; then labelled units
  // for checking the method against texts whose translator is secure.
  const matches = useMemo(() => {
    if (!units) return []
    const q = query.trim().toLowerCase()
    const rows = units.units.filter((r) =>
      !q || textName(r.uid).toLowerCase().includes(q) || profileName(r.label).toLowerCase().includes(q))
    rows.sort((a, b) => (a.label === 'grey') === (b.label === 'grey')
      ? a.uid.localeCompare(b.uid)
      : a.label === 'grey' ? -1 : 1)
    return rows.slice(0, 60)
  }, [units, query])

  return (
    <section className="evidence">
      <h2>Compare a text's wording</h2>
      <p className="ev-introduction">
        Compare short-string counts across corpus groups.
      </p>

      <div className="suggested-inputs" aria-label="Suggested evidence texts">
        <span className="hint small">Try a text:</span>
        {[
          ['T0263-rest', 'Lotus Sūtra · Dharmarakṣa'],
          ['T0603', 'Yin chi ru jing 陰持入經 · T0603'],
          ['T0453', 'Maitreya’s descent 彌勒下生經 · T0453'],
        ].map(([id, label]) => <button type="button" className="btn tiny" key={id}
          onClick={() => { choose(id); setQuery(id); setFeatures('radich'); setWithhold(''); setPair('') }}>
          {label}
        </button>)}
      </div>
      <p className="hint small">Examples start with the curated strings and no additional exclusions.</p>

      <details className="ev-options ev-chooser" open={!uid}>
        <summary>{uid ? 'Change the selected text' : 'Choose a text to examine'}</summary>
      <div className="ev-controls">
        <label className="ev-filter">
          <span>Choose a text</span>
          <input
            className="corpus-input"
            placeholder="Search by title, catalogue ID or translator name"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>

      </div>

      {units && (
        <div className="ev-picker">
          <ul className="ev-units">
            {matches.map((r) => (
              <li key={r.uid}>
                <button
                  className={`ev-unit ${uid === r.uid ? 'on' : ''}`}
                  onClick={(e) => { choose(r.uid); e.currentTarget.closest('details').open = false }}
                  title={`${r.uid} — ${r.profiled ? 'in the profiles; its whole work is withheld when judged' : 'not in the profiles'}`}
                >
                  <span className="ev-uid">{textName(r.uid)}</span>
                  <span className={`ev-label ${r.label === 'grey' ? 'grey' : ''}`}>{profileName(r.label)}</span>
                  <span className="ev-chars">{r.han_chars.toLocaleString()}</span>
                </button>
              </li>
            ))}
            {matches.length === 60 && <li className="hint small">first 60 shown; narrow the filter</li>}
          </ul>
          <div className="ev-ledger">
            <button className="btn tiny" onClick={() => setShowLedger((v) => !v)} aria-expanded={showLedger}>
              {showLedger ? 'Hide' : 'Show'} corpus exclusions and counts
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

      </details>

      <div aria-live="polite">
        {error && <p className="error">{error}</p>}
        {busy && <p className="hint">Counting…</p>}
      </div>
      <details className="ev-options">
        <summary>Vocabulary and method</summary>
        <p>Here, “vocabulary” means a list of two-, three- and four-character sequences to count. They are not necessarily whole words.</p>
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
        <p className="hint small">{features === 'radich'
          ? 'Two-, three- and four-character strings selected for work on a Dharmarakṣa (竺法護) dictionary. They are not exclusive to his translations, and coverage differs across translators.'
          : features === 'generic'
          ? 'Frequent strings selected from texts whose translator is uncertain in this catalogue, without using translator labels. Common religious expressions can dominate.'
          : 'The union of both lists, with duplicate strings counted once in the list. Combining them does not remove their biases.'}</p>
        <p>The calculation stays the same when you switch lists; you change which strings it counts.</p>
        <button className="btn" onClick={() => setShowHow((v) => !v)} aria-expanded={showHow}>
          {showHow ? 'Hide method explanation' : 'Explain the calculation and its limits'}
        </button>
        {showHow && <HowToRead />}
      </details>
      {data && !busy && (
        <Reading
          data={data}
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
        <b>How the score is made.</b> Count the selected strings in your text. For each comparison group, use its relative string frequencies to score those matches. More frequent matches contribute more. The highest score determines the first-ranked group.
        </p>
      <p>
        <b>Score difference.</b> The highest score minus the next highest, divided by the number of distinct matched strings. Near zero means little separates those scores. It is not a probability, and there is no validated cutoff for assigning a translator.
      </p>
      <p>
        <b>Colours.</b> Teal and rust show which group a string favours. Stronger colour means greater weight. Fix the group pair before switching string sets.
      </p>
      <p>
        <b>Text overview.</b> Click a cell to read that section. Colour changes may reflect subject, genre or textual history.
      </p>
      <p>
        <b>Exclusions.</b> All profiled chapters of the target work are excluded automatically. You can exclude additional texts to test dependence on repeated material.
      </p>
      <p>
        <b>String sets.</b> The curated list was developed for a Dharmarakṣa dictionary and covers An Shigao poorly. The alternative uses frequent strings from uncertain texts without consulting translator labels.
      </p>
      <p>
        <b>Limits.</b> No matching strings means no ranking. Similar scores do not establish an attribution. Texts composed in Chinese may have no translator.
      </p>
    </div>
  )
}

function rgba(which, a) {
  return `rgba(var(--ev-${which}-rgb), ${Math.max(0, Math.min(a, ALPHA_CAP)).toFixed(2)})`
}

function Reading({ data, withhold, onWithhold, pair: pinnedPair, onPair, onOffset }) {
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
  const excerptEnd = data.excerpt.end ?? (data.excerpt.start + Array.from(data.excerpt.text).length)

  return (
    <div className="ev-reading">
      <div className="ev-head">
        <h3>{textName(data.uid)}</h3>
        <CbetaLink url={data.cbeta_url} />
        <p className="ev-catalogue">Catalogue classification: <b>{profileName(data.label)}</b></p>
        <p className="hint small">
          {data.han_chars.toLocaleString()} Han characters ({data.code_points.toLocaleString()} code points)
          · {data.hits.toLocaleString()} matched string occurrences · {data.distinct.toLocaleString()} different strings
          · vocabulary: {FEATURE_LABEL[data.features]} ({data.n_features.toLocaleString()} strings)
          {data.withheld_units > 0 && (
            <> · <b>{data.withheld_units} unit{data.withheld_units > 1 ? 's' : ''} withheld</b> from the profiles
              {data.withheld_extra.length > 0 && <> (incl. {data.withheld_extra.join(', ')})</>}</>
          )}
        </p>
      </div>

      {data.verdict === 'no evidence' ? (
        <div className="ev-verdict">
          <div><b className="warn">no evidence</b>
            <span className="hint small"> not one string of this vocabulary occurs in the text; nothing is ranked</span></div>
        </div>
      ) : (
        <div className="ev-verdict">
          <div><span className="hint small">Highest-ranked comparison group</span><b>{profileName(data.first)}</b></div>
          <div><span className="hint small">Next comparison group</span><b>{profileName(data.second)}</b></div>
          <div>
            <span className="hint small">Score difference</span>
            <b>{data.margin > 0 ? '+' : ''}{data.margin.toFixed(3)}</b>
            <span className="hint small">log-odds per distinct string; not comparable across texts</span>
          </div>
          {data.verdict === 'low evidence' && (
            <div><b className="warn">low evidence</b><span className="hint small">fewer than 10 distinct strings</span></div>
          )}
        </div>
      )}

      {data.verdict !== 'no evidence' && (
        <section className="ev-ranking" aria-label="Full group ranking">
          <h4>All {data.ranking.length} groups, ranked</h4>
          <p className="hint small">The leader is 0. Negative scores fall below it; more negative means further behind. These are total score differences, not the per-string margin above or probabilities.</p>
          <div className="ev-comparison-scroll">
          <table className="ev-table">
            <thead><tr><th>Rank</th><th className="g">Group</th><th>Score relative to leader</th><th>Texts/chapters used</th></tr></thead>
            <tbody>
              {data.ranking.map((r, index) => {
                const p = data.profiles[r.label] || {}
                return (
                  <tr key={r.label} className={p.thin ? 'thin' : ''}>
                    <td className="num">{index + 1}</td>
                    <td className="g">{profileName(r.label)}{p.thin && <span className="warn small"> thin</span>}</td>
                    <td className="num">{r.delta.toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                    <td className="num">{p.units} of {p.units_before_withholding}</td>
                  </tr>
                )
              })}
              {data.no_profile.map((n) => (
                <tr key={n.label}><td>—</td><td className="g">{profileName(n.label)}</td><td colSpan="2" className="hint small">not judged: {n.reason}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        </section>
      )}

      {(data.first === 'pre-Dhr-other' || data.second === 'pre-Dhr-other') && (
        <p className="hint small">“Other material before Dharmarakṣa 竺法護” is a mixed corpus group, not a single translator.</p>
      )}
      <p className="ev-limits">
        Similarity does not establish translator identity. Scores are not probabilities; repeated passages and genre formulae can affect them.
        </p>
      <div className="ev-next">
      <h3>Does the result depend on another text?</h3>
      <p>Exclude a suspected source of repeated wording from the comparison groups. Your target text stays unchanged.</p>
      <p className="hint small">Use exact IDs from the picker. For chaptered works, list each chapter ID separately.</p>
      <form
        className="ev-withhold"
        onSubmit={(e) => { e.preventDefault(); onWithhold(withholdDraft.trim()) }}
      >
        <label>
          <span className="hint small">Exclude additional texts (exact corpus unit IDs, separated by commas)</span>
          <input
            className="corpus-input"
            value={withholdDraft}
            placeholder="e.g. T1694"
            onChange={(e) => setWithholdDraft(e.target.value)}
          />
        </label>
        <button className="btn tiny" type="submit">Repeat comparison</button>
        {withhold && <button className="btn tiny" type="button" onClick={() => onWithhold('')}>Restore these texts</button>}
        {withholdDraft.trim() && <p className="ev-exclusion-names">
          {withholdDraft.split(',').map((id) => textName(id.trim())).join('; ')}
      </p>}
      </form>
      <p className="hint small">Applies to this calculation only. Sources and graph records are unchanged.</p>
      {data.withheld_extra.length > 0 && <ExclusionComparison key={`${data.uid}:${data.features}:${data.withheld_extra.join(',')}`} data={data} />}
      </div>
      <details className="ev-options">
      <summary>Highlighting groups</summary>
      <p>Sets the highlight colours; the overall ranking is unchanged.</p>

      <form
        className="ev-withhold"
        onSubmit={(e) => { e.preventDefault(); onPair(pairDraft.replace(/\s+/g, '')) }}
      >
        <label>
          <span className="hint small">Group codes for colours A and B (comma-separated; leave empty for automatic selection)</span>
          <input
            className="corpus-input"
            value={pairDraft}
            placeholder="e.g. Dhr,ZFn"
            onChange={(e) => setPairDraft(e.target.value)}
          />
        </label>
        <button className="btn tiny" type="submit">Update highlighting</button>
        {pinnedPair && <button className="btn tiny" type="button" onClick={() => onPair('')}>clear</button>}
      </form>
      </details>


      {pair && (
        <p className="hint small">
          Text highlighting: <b className="ev-a">{profileName(a)}</b> (A) vs <b className="ev-b">{profileName(b)}</b> (B)
          {pair.pinned ? '. Groups selected manually' : a === data.label ? '. A is the catalogue group; B is the highest-scoring other group' : '. A and B are the two highest-scoring groups'}.
          Selected-string occurrences in the reference texts: A {data.profiles[a].feature_tokens.toLocaleString()}; B {data.profiles[b].feature_tokens.toLocaleString()} (including repeats).
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

      <details className="ev-options">
      <summary>String counts and weights</summary>
      {pair && (
        <div className="ev-cols">
          <EvidenceTable title={`Toward ${profileName(a)}`} rows={data.for} a={profileName(a)} b={profileName(b)} />
          <EvidenceTable title={`Toward ${profileName(b)}`} rows={data.against} a={profileName(a)} b={profileName(b)} />
        </div>
      )}
      <p className="hint small">
        Weight = hits × log-odds, with add-half smoothing. Rates are per 100,000
        string hits, not characters. Overlapping strings are counted separately;
        weights are not confidence estimates. Strings absent from both profiles are omitted.
      </p>
      </details>
    </div>
  )
}

function ExclusionComparison({ data }) {
  const [before, setBefore] = useState(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    let live = true
    getEvidence(data.uid, data.features).then(r => { if (live) setBefore(r) })
      .catch(() => { if (live) setError(true) })
    return () => { live = false }
  }, [data.uid, data.features])
  if (error) return <p className="hint">The comparison without additional exclusions could not be loaded.</p>
  if (!before) return <p className="hint">Loading the comparison without additional exclusions…</p>
  const rows = [['Before', before], [`Without ${data.withheld_extra.join(', ')}`, data]]
  return <div className="ev-comparison">
    <h4>Effect of exclusion</h4>
    <div className="ev-comparison-scroll"><table className="ev-table">
      <thead><tr><th>Setup</th><th>First</th><th>Second</th><th>Margin</th></tr></thead>
      <tbody>{rows.map(([label,r]) => <tr key={label}><td>{label}</td>
        <td>{r.first ? profileName(r.first, false) : 'No ranking'}</td>
        <td>{r.second ? profileName(r.second, false) : '—'}</td>
        <td>{Number.isFinite(r.margin) ? r.margin.toFixed(3) : '—'}</td>
      </tr>)}</tbody>
    </table></div>
    {data.uid === 'T0603' && data.withheld_extra.includes('T1694') && <p className="hint small">
      T1694 is T0603’s commentary. Its wording contributes to the mixed group.
    </p>}
  </div>
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
          {!rows.length && <tr><td colSpan="5" className="hint small">No matching strings</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
