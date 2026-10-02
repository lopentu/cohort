import { Button } from './components/ui'
import { useTranslation } from 'react-i18next'
import { tr, formatNumber, metadataLabel } from './i18n'
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
  useTranslation()
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
      <h2>{tr("Compare a text's wording")}</h2>
      <p className="ev-introduction">{tr("Compare short-string counts across corpus groups.")}</p>

      <div className="suggested-inputs" aria-label={tr("Suggested evidence texts")}>
        <span className="hint small">{tr("Try a text:")}</span>
        {[
          ['T0263-rest', tr("Lotus Sūtra · Dharmarakṣa")],
          ['T0603', tr("Yin chi ru jing 陰持入經 · T0603")],
          ['T0453', tr("Maitreya’s descent 彌勒下生經 · T0453")],
        ].map(([id, label]) => <Button type="button" className="btn tiny" key={id}
          onClick={() => { choose(id); setQuery(id); setFeatures('radich'); setWithhold(''); setPair('') }}>
          {label}
        </Button>)}
      </div>
      <p className="hint small">{tr("Examples start with the curated strings and no additional exclusions.")}</p>

      <details className="ev-options ev-chooser" open={!uid}>
        <summary>{uid ? tr("Change the selected text") : tr("Choose a text to examine")}</summary>
      <div className="ev-controls">
        <label className="ev-filter">
          <span>{tr("Choose a text")}</span>
          <input
            className="corpus-input"
            placeholder={tr("Search by title, catalogue ID or translator name")}
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
                <Button
                  className={`ev-unit ${uid === r.uid ? 'on' : ''}`}
                  onClick={(e) => { choose(r.uid); e.currentTarget.closest('details').open = false }}
                  title={`${r.uid} — ${r.profiled ? tr("in the profiles; its whole work is withheld when judged") : tr("not in the profiles")}`}
                >
                  <span className="ev-uid">{textName(r.uid)}</span>
                  <span className={`ev-label ${r.label === 'grey' ? 'grey' : ''}`}>{profileName(r.label)}</span>
                  <span className="ev-chars">{formatNumber(r.han_chars)}</span>
                </Button>
              </li>
            ))}
            {matches.length === 60 && <li className="hint small">{tr("first 60 shown; narrow the filter")}</li>}
          </ul>
          <div className="ev-ledger">
            <Button className="btn tiny" onClick={() => setShowLedger((v) => !v)} aria-expanded={showLedger}>
              {showLedger ? tr("Hide") : tr("Show")}{' '}{tr("corpus exclusions and counts")}</Button>
            {showLedger && (
              <table className="ev-table">
                <tbody>
                  {Object.entries(units.ledger).map(([k, v]) => (
                    <tr key={k}><td>{metadataLabel(k)}</td><td className="num">{formatNumber(v)}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
            {showLedger && units.notes.map((n) => <p key={n} className="hint small">{tr(n)}</p>)}
          </div>
        </div>
      )}

      </details>

      <div aria-live="polite">
        {error && <p className="error">{error}</p>}
        {busy && <p className="hint">{tr("Counting…")}</p>}
      </div>
      <details className="ev-options">
        <summary>{tr("Vocabulary and method")}</summary>
        <p>{tr("Here, “vocabulary” means a list of two-, three- and four-character sequences to count. They are not necessarily whole words.")}</p>
        <div className="ev-features" role="radiogroup" aria-label={tr("feature vocabulary")}>
          {Object.entries(FEATURE_LABEL).map(([k, label]) => (
            <Button
              key={k}
              role="radio"
              aria-checked={features === k}
              className={`btn tiny ${features === k ? 'on' : ''}`}
              onClick={() => setFeatures(k)}
            >{tr(label)}</Button>
          ))}
        </div>
        <p className="hint small">{features === 'radich'
          ? tr("Two-, three- and four-character strings selected for work on a Dharmarakṣa (竺法護) dictionary. They are not exclusive to his translations, and coverage differs across translators.")
          : features === 'generic'
          ? tr("Frequent strings selected from texts whose translator is uncertain in this catalogue, without using translator labels. Common religious expressions can dominate.")
          : tr("The union of both lists, with duplicate strings counted once in the list. Combining them does not remove their biases.")}</p>
        <p>{tr("The calculation stays the same when you switch lists; you change which strings it counts.")}</p>
        <Button className="btn" onClick={() => setShowHow((v) => !v)} aria-expanded={showHow}>
          {showHow ? tr("Hide method explanation") : tr("Explain the calculation and its limits")}
        </Button>
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
  useTranslation()
  return (
    <div className="ev-how">
      <p>
        <b>{tr("How the score is made.")}</b>{tr("Count the selected strings in your text. For each comparison group, use its relative string frequencies to score those matches. More frequent matches contribute more. The highest score determines the first-ranked group.")}</p>
      <p>
        <b>{tr("Score difference.")}</b>{tr("The highest score minus the next highest, divided by the number of distinct matched strings. Near zero means little separates those scores. It is not a probability, and there is no validated cutoff for assigning a translator.")}</p>
      <p>
        <b>{tr("Colours.")}</b>{tr("Teal and rust show which group a string favours. Stronger colour means greater weight. Fix the group pair before switching string sets.")}</p>
      <p>
        <b>{tr("Text overview.")}</b>{tr("Click a cell to read that section. Colour changes may reflect subject, genre or textual history.")}</p>
      <p>
        <b>{tr("Exclusions.")}</b>{tr("All profiled chapters of the target work are excluded automatically. You can exclude additional texts to test dependence on repeated material.")}</p>
      <p>
        <b>{tr("String sets.")}</b>{tr("The curated list was developed for a Dharmarakṣa dictionary and covers An Shigao poorly. The alternative uses frequent strings from uncertain texts without consulting translator labels.")}</p>
      <p>
        <b>{tr("Limits.")}</b>{tr("No matching strings means no ranking. Similar scores do not establish an attribution. Texts composed in Chinese may have no translator.")}</p>
    </div>
  )
}

function rgba(which, a) {
  return `rgba(var(--ev-${which}-rgb), ${Math.max(0, Math.min(a, ALPHA_CAP)).toFixed(2)})`
}

function Reading({ data, withhold, onWithhold, pair: pinnedPair, onPair, onOffset }) {
  useTranslation()
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
        <p className="ev-catalogue">{tr("Catalogue classification:")} <b>{profileName(data.label)}</b></p>
        <p className="hint small">
          {formatNumber(data.han_chars)} {tr("Han characters (")}{formatNumber(data.code_points)} {tr("code points) ·")} {formatNumber(data.hits)} {tr("matched string occurrences ·")} {formatNumber(data.distinct)} {tr("different strings · vocabulary:")} {tr(FEATURE_LABEL[data.features])} ({formatNumber(data.n_features)} {tr("strings)")}{data.withheld_units > 0 && (
            <> · <b>{data.withheld_units} {tr("unit")}{data.withheld_units > 1 ? 's' : ''} {tr("withheld")}</b> {tr("from the profiles")}{data.withheld_extra.length > 0 && <> {tr("(incl.")} {data.withheld_extra.join(', ')})</>}</>
          )}
        </p>
      </div>

      {data.verdict === 'no evidence' ? (
        <div className="ev-verdict">
          <div><b className="warn">{tr("no evidence")}</b>
            <span className="hint small"> {tr("not one string of this vocabulary occurs in the text; nothing is ranked")}</span></div>
        </div>
      ) : (
        <div className="ev-verdict">
          <div><span className="hint small">{tr("Highest-ranked comparison group")}</span><b>{profileName(data.first)}</b></div>
          <div><span className="hint small">{tr("Next comparison group")}</span><b>{profileName(data.second)}</b></div>
          <div>
            <span className="hint small">{tr("Score difference")}</span>
            <b>{data.margin > 0 ? '+' : ''}{data.margin.toFixed(3)}</b>
            <span className="hint small">{tr("log-odds per distinct string; not comparable across texts")}</span>
          </div>
          {data.verdict === 'low evidence' && (
            <div><b className="warn">{tr("low evidence")}</b><span className="hint small">{tr("fewer than 10 distinct strings")}</span></div>
          )}
        </div>
      )}

      {data.verdict !== 'no evidence' && (
        <section className="ev-ranking" aria-label={tr("Full group ranking")}>
          <h4>{tr("All")} {data.ranking.length} {tr("groups, ranked")}</h4>
          <p className="hint small">{tr("The leader is 0. Negative scores fall below it; more negative means further behind. These are total score differences, not the per-string margin above or probabilities.")}</p>
          <div className="ev-comparison-scroll" tabIndex={0} role="region" aria-label={tr("Full group ranking")}>
          <table className="ev-table">
            <thead><tr><th>{tr("Rank")}</th><th className="g">{tr("Group")}</th><th>{tr("Score relative to leader")}</th><th>{tr("Texts/chapters used")}</th></tr></thead>
            <tbody>
              {data.ranking.map((r, index) => {
                const p = data.profiles[r.label] || {}
                return (
                  <tr key={r.label} className={p.thin ? 'thin' : ''}>
                    <td className="num">{index + 1}</td>
                    <td className="g">{profileName(r.label)}{p.thin && <span className="warn small"> {tr("thin")}</span>}</td>
                    <td className="num">{formatNumber(r.delta, { maximumFractionDigits: 1 })}</td>
                    <td className="num">{p.units} {tr("of")} {p.units_before_withholding}</td>
                  </tr>
                )
              })}
              {data.no_profile.map((n) => (
                <tr key={n.label}><td>—</td><td className="g">{profileName(n.label)}</td><td colSpan="2" className="hint small">{tr("not judged:")} {tr(n.reason)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        </section>
      )}

      {(data.first === 'pre-Dhr-other' || data.second === 'pre-Dhr-other') && (
        <p className="hint small">{tr("“Other material before Dharmarakṣa 竺法護” is a mixed corpus group, not a single translator.")}</p>
      )}
      <p className="ev-limits">{tr("Similarity does not establish translator identity. Scores are not probabilities; repeated passages and genre formulae can affect them.")}</p>
      <div className="ev-next">
      <h3>{tr("Does the result depend on another text?")}</h3>
      <p>{tr("Exclude a suspected source of repeated wording from the comparison groups. Your target text stays unchanged.")}</p>
      <p className="hint small">{tr("Use exact IDs from the picker. For chaptered works, list each chapter ID separately.")}</p>
      <form
        className="ev-withhold"
        onSubmit={(e) => { e.preventDefault(); onWithhold(withholdDraft.trim()) }}
      >
        <label>
          <span className="hint small">{tr("Exclude additional texts (exact corpus unit IDs, separated by commas)")}</span>
          <input
            className="corpus-input"
            value={withholdDraft}
            placeholder={tr("e.g. T1694")}
            onChange={(e) => setWithholdDraft(e.target.value)}
          />
        </label>
        {data.uid === 'T0603' && <Button className="btn tiny ev-commentary-shortcut" type="button"
          disabled={withhold.split(',').some(id => id.trim() === 'T1694')}
          onClick={() => {
            const ids = [...new Set([...withholdDraft.split(',').map(id => id.trim()).filter(Boolean), 'T1694'])].join(',')
            setWithholdDraft(ids)
            onWithhold(ids)
          }}>
          {withhold.split(',').some(id => id.trim() === 'T1694') ? tr("T1694 commentary excluded") : tr("Exclude T1694 commentary")}
        </Button>}
        <Button className="btn tiny" type="submit">{tr("Repeat comparison")}</Button>
        {withhold && <Button className="btn tiny" type="button" onClick={() => onWithhold('')}>{tr("Restore these texts")}</Button>}
        {withholdDraft.trim() && <p className="ev-exclusion-names">
          {withholdDraft.split(',').map((id) => textName(id.trim())).join('; ')}
      </p>}
      </form>
      <p className="hint small">{tr("Applies to this calculation only. Sources and graph records are unchanged.")}</p>
      {data.withheld_extra.length > 0 && <ExclusionComparison key={`${data.uid}:${data.features}:${data.withheld_extra.join(',')}`} data={data} />}
      </div>
      <details className="ev-options">
      <summary>{tr("Highlighting groups")}</summary>
      <p>{tr("Sets the highlight colours; the overall ranking is unchanged.")}</p>

      <form
        className="ev-withhold"
        onSubmit={(e) => { e.preventDefault(); onPair(pairDraft.replace(/\s+/g, '')) }}
      >
        <label>
          <span className="hint small">{tr("Group codes for colours A and B (comma-separated; leave empty for automatic selection)")}</span>
          <input
            className="corpus-input"
            value={pairDraft}
            placeholder={tr("e.g. Dhr,ZFn")}
            onChange={(e) => setPairDraft(e.target.value)}
          />
        </label>
        <Button className="btn tiny" type="submit">{tr("Update highlighting")}</Button>
        {pinnedPair && <Button className="btn tiny" type="button" onClick={() => onPair('')}>{tr("clear")}</Button>}
      </form>
      </details>


      {pair && (
        <p className="hint small">{tr("Text highlighting:")} <b className="ev-a">{profileName(a)}</b> {tr("(A) vs")} <b className="ev-b">{profileName(b)}</b>{tr("(B)")}{pair.pinned ? tr(". Groups selected manually") : a === data.label ? tr(". A is the catalogue group; B is the highest-scoring other group") : tr(". A and B are the two highest-scoring groups")}{tr(". Selected-string occurrences in the reference texts: A")} {formatNumber(data.profiles[a].feature_tokens)}{tr("; B")} {formatNumber(data.profiles[b].feature_tokens)} {tr("(including repeats).")}</p>
      )}

      <p className="hint small">{tr("Whole text, one cell per {{count}} characters. Click a cell to read that part.", { count: formatNumber(data.strip_cell) })}</p>
      <div className="ev-strip" role="group" aria-label={tr("evidence across the whole text")}>
        {data.strip.map((c) => (
          <Button
            key={c.start}
            type="button"
            className={`ev-cell ${c.start <= data.excerpt.start && data.excerpt.start < c.end ? 'here' : ''}`}
            title={tr('Characters {{start}}–{{end}}: {{direction}} ({{weight}})', { start: formatNumber(c.start), end: formatNumber(c.end), direction: c.mean ? tr('Toward {{group}}', { group: profileName(c.mean > 0 ? a : b) }) : tr('nothing'), weight: c.mean.toFixed(3) })}
            aria-label={tr('Characters {{start}} to {{end}}', { start: c.start, end: c.end })}
            style={{ background: c.mean ? rgba(c.mean > 0 ? 'a' : 'b', Math.abs(c.mean) / stripScale * ALPHA_CAP) : 'transparent' }}
            onClick={() => onOffset(c.start)}
          />
        ))}
      </div>

      <p className="hint small">{tr("Characters")} {formatNumber(data.excerpt.start)}–{formatNumber(excerptEnd)}{tr(". Saturation is capped at the 95th percentile of evidence weight.")}{data.excerpt.start > 0 && <> <Button className="btn tiny" type="button" onClick={() => onOffset(0)}>{tr("back to the start")}</Button></>}
      </p>
      <div className="ev-text" lang="zh-Hant">
        {spans.map(([bk, s], i) => bk
          ? <mark key={i} className={bk[0] === 'a' ? 'a' : 'b'} style={{ background: bucketColour(bk) }}>{s}</mark>
          : <span key={i}>{s}</span>)}
      </div>

      <details className="ev-options">
      <summary>{tr("String counts and weights")}</summary>
      {pair && (
        <div className="ev-cols">
          <EvidenceTable title={tr('Toward {{group}}', { group: profileName(a) })} rows={data.for} a={profileName(a)} b={profileName(b)} />
          <EvidenceTable title={tr('Toward {{group}}', { group: profileName(b) })} rows={data.against} a={profileName(a)} b={profileName(b)} />
        </div>
      )}
      <p className="hint small">{tr("Weight = hits × log-odds, with add-half smoothing. Rates are per 100,000 string hits, not characters. Overlapping strings are counted separately; weights are not confidence estimates. Strings absent from both profiles are omitted.")}</p>
      </details>
    </div>
  )
}

function ExclusionComparison({ data }) {
  useTranslation()
  const [before, setBefore] = useState(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    let live = true
    getEvidence(data.uid, data.features).then(r => { if (live) setBefore(r) })
      .catch(() => { if (live) setError(true) })
    return () => { live = false }
  }, [data.uid, data.features])
  if (error) return <p className="hint">{tr("The comparison without additional exclusions could not be loaded.")}</p>
  if (!before) return <p className="hint">{tr("Loading the comparison without additional exclusions…")}</p>
  const rows = [[tr('Before'), before], [tr('Without {{texts}}', { texts: data.withheld_extra.join(', ') }), data]]
  return <div className="ev-comparison">
    <h4>{tr("Effect of exclusion")}</h4>
    <div className="ev-comparison-scroll" tabIndex={0} role="region" aria-label={tr("Effect of exclusion")}><table className="ev-table">
      <thead><tr><th>{tr("Setup")}</th><th>{tr("Leading group")}</th><th>{tr("Second-ranked group")}</th><th>{tr("Margin")}</th></tr></thead>
      <tbody>{rows.map(([label,r]) => <tr key={label}><td>{label}</td>
        <td>{r.first ? profileName(r.first, false) : tr("No ranking")}</td>
        <td>{r.second ? profileName(r.second, false) : '—'}</td>
        <td>{Number.isFinite(r.margin) ? r.margin.toFixed(3) : '—'}</td>
      </tr>)}</tbody>
    </table></div>
    {data.uid === 'T0603' && data.withheld_extra.includes('T1694') && <p className="hint small">{tr("T1694 is T0603’s commentary. Its wording contributes to the mixed group.")}</p>}
  </div>
}

function EvidenceTable({ title, rows, a, b }) {
  useTranslation()
  return (
    <div>
      <table className="ev-table">
        <thead>
          <tr>
            <th className="g">{title}</th><th>{tr("hits")}</th>
            <th title={tr("raw count, and per 100,000 feature tokens in that profile")}>{a} {tr("n · /100k")}</th>
            <th title={tr("raw count, and per 100,000 feature tokens in that profile")}>{b} {tr("n · /100k")}</th>
            <th>{tr("weight")}</th>
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
          {!rows.length && <tr><td colSpan="5" className="hint small">{tr("No matching strings")}</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
