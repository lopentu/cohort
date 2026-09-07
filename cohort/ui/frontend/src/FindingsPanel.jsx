import { useCallback, useEffect, useState } from 'react'
import {
  getCitable,
  getDossier,
  getFindings,
  getIntegrity,
  getLedger,
  getRebuild,
  getRejected,
  getStudy,
} from './api'
import Placements from './Placements'
import Reveal from './Reveal'

// The researcher's output view: everything the graph currently amounts to, on
// one page, in the order a reader needs it.
//
// It was three pages until 2026-09-06 — Findings, Ledger, Attribution — and
// that was the problem. The same conjecture appeared in two of them under two
// framings: once as an unranked hypothesis, once as a ledger row carrying the
// fate that is the single most informative thing about it. The Delta study sat
// in a third, measuring the works those hypotheses were about. Nothing was
// missing and nothing could be assembled.
//
// So the shape here is an argument, top to bottom:
//
//   1. what the whole exercise amounts to — the ratio, which is the finding
//   2. the hypotheses, grouped by what became of them
//   3. where the works in doubt sit, as the standing measurement
//   4. what may be cited, and what was thrown out and why
//   5. whether this record is internally consistent at all
//
// Citable and rejected stay side by side deliberately. Only accepted nodes may
// be cited, and rejections-with-reasons are part of the scholarly output
// rather than a failure list (docs/design.md §8).
//
// The two integrity checks are on demand, not ambient: `verify_integrity`'s
// own contract is that one tampered row must not turn every future read into
// a crash, so nothing here runs on a timer.

export default function FindingsPanel({ onSelect }) {
  const [citable, setCitable] = useState(null)
  const [rejected, setRejected] = useState(null)
  const [findings, setFindings] = useState(null)
  const [ledger, setLedger] = useState(null)
  const [study, setStudy] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let live = true
    Promise.all([getCitable(), getRejected(), getFindings(), getLedger()])
      .then(([c, r, f, l]) => {
        if (!live) return
        setCitable(c); setRejected(r); setFindings(f); setLedger(l)
      })
      .catch((e) => live && setError(e.message))
    // The study route is not mounted unless the server was started against
    // one, so its absence is a configuration, not a failure — it must not
    // blank the page the way a missing findings list would.
    getStudy().then((s) => live && setStudy(s)).catch(() => {})
    return () => { live = false }
  }, [])

  if (error) return <section className="findings"><p className="error">{error}</p></section>

  return (
    <section className="findings">
      <Reading ledger={ledger} study={study} />

      <Hypotheses findings={findings} onSelect={onSelect} />

      <Placements data={study} />

      <div className="findings-cols">
        <div>
          <h2>Citable</h2>
          <p className="hint small">
            Accepted nodes. The only ones output may cite, and the only ones
            another agent may build on.
          </p>
          <NodeList
            nodes={citable}
            onSelect={onSelect}
            empty="Nothing is citable yet — only accepted nodes are, and none are accepted."
          />
        </div>

        <div>
          <h2>Rejected</h2>
          <p className="hint small">
            Thrown out, with the reason. Part of the record, not a failure list —
            and a rejected node cannot be re-proposed.
          </p>
          <NodeList
            nodes={rejected}
            onSelect={onSelect}
            reason
            empty="Nothing has been rejected."
          />
        </div>
      </div>

      <IntegrityStrip />
    </section>
  )
}

// What the whole exercise amounts to, before any individual row.
//
// The ratio leads because it *is* the finding, and it is the one number a
// reader cannot reconstruct from the list below without counting the rows
// themselves. Three survivors out of four is a different claim from three out
// of ninety; a page that opened with the survivors would make the second read
// like the first, which is the failure mode of most stylometry.
//
// The band sentence sits beside it because every distance on this page is read
// against it, and a calibration one section away from the numbers it calibrates
// is a calibration nobody applies.
function Reading({ ledger, study }) {
  if (!ledger) return null
  const tried = ledger.tried

  return (
    <div className="reading">
      {tried > 0 && (
        <div className="ledger-ratio">
          <div className="ratio-figure">
            <strong>{ledger.by_fate.usable}</strong>
            <span>of {tried}</span>
          </div>
          <p>{ledger.reading}</p>
        </div>
      )}

      {study && (
        <p className="study-null">
          The benchmark <strong>{study.benchmark_label}</strong> has {study.null.n} works,
          and they sit <strong>Δ {study.null.min}–{study.null.max}</strong> from
          each other (median {study.null.median}). Anything inside that band is no
          further from {study.benchmark_label} than {study.benchmark_label} is from
          itself. {study.features} character-bigram features over {study.corpus_size}{' '}
          works; works under {study.min_chars.toLocaleString()} characters are not
          profiled.
        </p>
      )}

      {tried === 0 && !study && (
        <p className="hint">{ledger.reading}</p>
      )}
    </div>
  )
}

//: The order hypotheses are grouped in, and what each group licenses. A fate is
//: a fact about a test that was run — it is not a score, and this is not a
//: ranking: `usable` means "survived one negative control", nothing more.
//: Grouping by it is allowed for exactly that reason, where grouping by
//: support count would not be (see `findings_json`).
const GROUPS = [
  ['usable', 'Survived the negative control',
    'Tested against works believed not to belong, and separated them. May now be applied to a work in doubt.'],
  ['untested', 'Registered, control not yet run',
    'A prediction is on the record and nothing has been counted against it yet. May not be applied to anything.'],
  ['discarded', 'Discarded by the control',
    'Failed against works believed not to belong, so it tracks something other than membership of the group. Kept on the page: these are the rows that make the ratio above mean anything.'],
  ['other', 'Other hypotheses',
    'Hypotheses that are not candidate discriminators, so no control applies to them.'],
]

//: Discarded features are the majority of a real ledger — twenty-two candidates
//: produced twenty discards — and twenty open rows would bury everything above
//: them. Collapsed, not omitted: the count stays on screen, which is the part
//: that carries the argument.
const COLLAPSED_BY_DEFAULT = new Set(['discarded'])

function Hypotheses({ findings, onSelect }) {
  const [open, setOpen] = useState(null)
  const [dossier, setDossier] = useState(null)
  const [shut, setShut] = useState(COLLAPSED_BY_DEFAULT)

  const toggle = (id) => {
    if (open === id) { setOpen(null); setDossier(null); return }
    setOpen(id)
    setDossier(null)
    getDossier(id).then(setDossier).catch(() => setDossier(null))
  }

  const toggleGroup = (key) => setShut((s) => {
    const next = new Set(s)
    if (next.has(key)) next.delete(key); else next.add(key)
    return next
  })

  if (!findings) return <p className="hint">Loading…</p>

  const groups = GROUPS
    .map(([key, title, licenses]) => [
      key, title, licenses,
      findings.findings.filter((f) => (f.ledger ? f.ledger.fate : 'other') === key),
    ])
    .filter(([, , , rows]) => rows.length)

  return (
    <div className="hypotheses">
      <h2>
        Hypotheses <span className="refusal-total">{findings.count}</span>
      </h2>
      <p className="hint small">
        Every hypothesis, grouped by what became of it and{' '}
        <strong>not ranked</strong> inside a group. Sorting these by how much
        attests them would be a confidence score under another name.
      </p>

      {findings.findings.length === 0 ? (
        <p className="hint small">Nothing has been proposed yet.</p>
      ) : (
        groups.map(([key, title, licenses, rows]) => (
          <div className={`hyp-group f-${key}`} key={key}>
            <button className="hyp-group-head" onClick={() => toggleGroup(key)}
                    aria-expanded={!shut.has(key)}>
              <span className={`caret ${shut.has(key) ? '' : 'down'}`}>›</span>
              <h3>{title}</h3>
              <span className="ledger-n">{rows.length}</span>
            </button>
            <Reveal open={!shut.has(key)}>
              <p className="hint small group-licenses">{licenses}</p>
              <ul className="hyp-list">
                {rows.map((f) => (
                  <Hypothesis
                    key={f.id} f={f} open={open === f.id} dossier={dossier}
                    onToggle={() => toggle(f.id)} onSelect={onSelect}
                  />
                ))}
              </ul>
            </Reveal>
          </div>
        ))
      )}
    </div>
  )
}

function Hypothesis({ f, open, dossier, onToggle, onSelect }) {
  const led = f.ledger
  const tallies = led?.control?.groups || []

  return (
    <li className={`hyp ${open ? 'open' : ''} ${led ? `f-${led.fate}` : ''}`}>
      <button className="hyp-head" onClick={onToggle}>
        <span className={`badge t-${f.type}`}>{f.type}</span>
        <span className="hyp-text">{f.assertion || f.id}</span>
      </button>

      {/* A registered discriminator's prediction and what was observed against
          it, on the row rather than behind the click. These four numbers are
          the whole content of a control test, and a reader scanning twenty
          features is deciding which to open on exactly them. */}
      {led && (
        <div className="hyp-test">
          <span className="ledger-pred">
            predicted ≥{pct(led.prediction.min_benchmark_share)}{' '}
            {led.prediction.benchmark_label} · ≤{pct(led.prediction.max_control_share)}{' '}
            {led.prediction.control_label}
          </span>
          <span className="ledger-observed">
            {tallies.length
              ? tallies.map((g) => (
                  <span className="tally" key={g.label}>
                    <span className="tally-label">{g.label}</span>
                    <strong>{g.works_attesting}/{g.works_measured}</strong>
                    {g.works_skipped_short > 0 && (
                      <em title={`${g.works_skipped_short} work(s) below the character floor`}>
                        +{g.works_skipped_short} short
                      </em>
                    )}
                  </span>
                ))
              : <span className="hint small">control not run</span>}
          </span>
        </div>
      )}

      <div className="hyp-marks">
        <span className={`chip s-${f.status}`}>{f.status}</span>
        <span className="chip">{f.assurance.replace(/_/g, ' ').toLowerCase()}</span>
        <span
          className={`chip ${
            f.support.vacuous ? 'unsupported' : f.support.independent ? '' : 'discounted'
          }`}
        >
          {f.support.vacuous ? (
            'nothing attests it yet'
          ) : (
            <>
              {f.support.attesting_count} attesting ·{' '}
              {f.support.distinct_witnesses} witness
              {f.support.distinct_witnesses === 1 ? '' : 'es'} ·{' '}
              {f.support.independent ? 'independent' : 'shared descent'}
            </>
          )}
        </span>
        {f.prospective_result && !led && (
          <span className={`chip r-${f.prospective_result}`}>
            prospective test: {f.prospective_result}
          </span>
        )}
        {!f.prospective_result && f.has_prospective_query && !led && (
          <span className="chip">prospective query not yet run</span>
        )}
        {f.measurements.length > 0 && (
          <span className="chip">
            {f.measurements.length} measurement
            {f.measurements.length === 1 ? '' : 's'} recorded
          </span>
        )}
        {f.has_dossier && <span className="chip">dossier</span>}
      </div>

      {f.support.vacuous && !led && (
        <p className="hint small discount-note">
          No passage cites this yet, so &ldquo;independent&rdquo; would be
          true only because there is nothing that could make it false. A
          conjecture is <em>allowed</em> to exceed its evidence &mdash;
          that is what separates it from a claim &mdash; but a dossier
          asserting measurements with nothing attesting them is the shape
          to distrust first.
        </p>
      )}

      {!f.support.vacuous && !f.support.independent && (
        <p className="hint small discount-note">
          A <code>parallel_of</code> or <code>descends_from</code> edge
          links witnesses behind this, so their agreement is evidence of
          shared descent rather than independent confirmation. The
          attesting count is unchanged; what it <em>means</em> is not.
        </p>
      )}

      {open && <Dossier d={dossier} led={led} onSelect={onSelect} />}
    </li>
  )
}

function Dossier({ d, led, onSelect }) {
  if (!d) return <p className="hint small">Loading the dossier…</p>
  const fields = Object.entries(d.dossier || {})
  const test = d.prospective_test
  return (
    <div className="dossier">
      {led?.control && (
        <div className="prospective">
          <h4>Negative control</h4>
          <p className={`prospective-result r-${led.control.result}`}>
            {led.control.result.toUpperCase()} — {led.control.detail}
          </p>
          {led.control.limitations && (
            <p className="v-limits"><strong>Does not establish:</strong>{' '}
              {led.control.limitations}</p>
          )}
          <p className="hint small">{led.licenses}</p>
        </div>
      )}

      {d.measurements?.length > 0 && (
        <Measurements rows={d.measurements} />
      )}

      {fields.length > 0 && (
        <dl className="dossier-fields">
          {fields.map(([k, v]) => (
            <div key={k}>
              <dt>{k.replace(/_/g, ' ')}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      )}

      {d.prior_art?.length > 0 && (
        <p className="hint small">
          Prior art actually searched before proposing: {d.prior_art.map((q) => q.text).join('; ')}
        </p>
      )}

      {!led && d.prospective_queries?.map((q) => (
        <div className="prospective" key={q.id}>
          <h4>Prospective test</h4>
          <p className="prospective-q"><code>{q.text}</code></p>
          {q.expectation ? (
            <p className="prospective-pred">
              Predicted <strong>{q.expectation === 'at_most' ? 'at most' : 'at least'}{' '}
              {q.expected_hits}</strong> — recorded when this was proposed, before the
              query was ever run.
            </p>
          ) : (
            <p className="hint small">No prediction was recorded for this query.</p>
          )}
          {test && (
            <p className={`prospective-result r-${test.payload.result}`}>
              {test.payload.result.toUpperCase()} — {test.payload.detail}
            </p>
          )}
        </div>
      ))}

      {d.evidence?.length > 0 && (
        <div className="dossier-evidence">
          <h4>Evidence ({d.evidence.length})</h4>
          <ul>
            {d.evidence.map((e) => (
              <li key={e.passage_id}>
                <button className="ev-ref" onClick={() => onSelect(e.passage_id)}>
                  <code>{e.canonical_ref}</code>
                </button>
                <span className="chip">{e.assurance.replace(/_/g, ' ').toLowerCase()}</span>
                <p className="ev-excerpt">{e.excerpt}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {d.latest_verifications?.length > 0 && (
        <div className="dossier-verifications">
          <h4>Verifications</h4>
          <p className="hint small">
            Latest per method, so a stale pass cannot outrank a later failure.
            The machine&apos;s finding and a reviewer&apos;s reading are separate
            fields on purpose &mdash; that is what stops a confident sentence
            from reading later as a mechanical result.
          </p>
          {d.latest_verifications.map((v) => (
            <div key={v.id} className="verification">
              <div className="verification-head">
                <span className={`badge r-${v.payload.result}`}>{v.payload.result}</span>
                <span>{v.payload.method.replace(/_/g, ' ')}</span>
              </div>
              <p className="v-detail"><strong>Machine:</strong> {v.payload.detail}</p>
              {v.payload.limitations && (
                <p className="v-limits"><strong>Does not establish:</strong>{' '}
                  {v.payload.limitations}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Recorded measurements, as the table they always were.
//
// These rendered as one English sentence per measurement until now, which meant
// a reader wanting to know which disputed work carried a feature had to parse
// the sentence — and the counting rules the payload enforces (never pool, one
// base edition, no rate below the floor) were invisible in prose. `per_10k` is
// null rather than zero below the floor, and that shows here as an em dash: a
// work this method cannot speak to, rather than a work with a rate of nothing.
function Measurements({ rows }) {
  return (
    <div className="measurements">
      <h4>Measurements ({rows.length})</h4>
      {rows.map((m) => (
        <div className={`measurement k-${m.kind}`} key={m.id}>
          <p className="v-detail">
            <span className={`badge r-${m.result}`}>{m.result}</span> {m.detail}
          </p>
          {m.association && <AssociationTable a={m.association} />}
          {m.works.length > 0 && (
            <div className="work-scroll"><table className="work-table">
              <thead>
                <tr>
                  <th>work</th><th>label</th><th className="num">chars</th>
                  <th className="num">count</th><th className="num">per 10k</th>
                  <th className="num">editions</th>
                </tr>
              </thead>
              <tbody>
                {m.works.map((w) => (
                  <tr key={w.work} className={w.sufficient ? '' : 'short'}>
                    <td>{w.work}</td>
                    <td className="dim">{w.label || '—'}</td>
                    <td className="num">{w.chars.toLocaleString()}</td>
                    <td className="num">{w.count}</td>
                    <td className="num" title={w.note || undefined}>
                      {w.per_10k == null ? '—' : w.per_10k}
                    </td>
                    <td className="num dim">
                      {w.editions_attesting}/{w.editions_total}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          )}
          {m.works.some((w) => !w.sufficient) && (
            <p className="hint small">
              A dash means the work is below the character floor, so this method
              reports no rate for it — not a rate of zero.
            </p>
          )}
          {m.limitations && (
            <p className="v-limits"><strong>Does not establish:</strong> {m.limitations}</p>
          )}
          <p className="hint small mono-note">{m.fingerprint}</p>
        </div>
      ))}
    </div>
  )
}

// An association, as the three numbers that make it readable.
//
// The share is never shown without its calibration, because a share against
// chance says only that the overlap is not an accident — not that it is as
// strong as membership normally looks. `blind` is on screen for the same
// reason: while a third of a group's undisputed members score zero, a zero is
// not an exclusion, and a table that omitted that would be inviting one.
function AssociationTable({ a }) {
  return (
    <div className="assoc-detail">
      <p className="assoc-summary">
        <code>{a.work}</code> against <strong>{a.group_label}</strong> over{' '}
        {a.corpus_size.toLocaleString()} profiled works
        {a.first_rank
          ? <> — nearest {a.group_label} work at rank <strong>{a.first_rank}</strong></>
          : <> — no {a.group_label} work anywhere in the ranking</>}
      </p>

      <div className="work-scroll"><table className="work-table">
        <thead>
          <tr>
            <th>k nearest</th><th className="num">in group</th>
            <th className="num">share</th><th className="num">p</th>
            <th className="num">known members reach</th>
            <th className="num">cannot see</th>
          </tr>
        </thead>
        <tbody>
          {a.enrichment.map((e) => (
            <tr key={e.k} className={e.within_calibration ? 'assoc-strong' : ''}>
              <td>{e.k}</td>
              <td className="num">{e.hits}</td>
              <td className="num">{(e.share * 100).toFixed(1)}%</td>
              <td className="num">{e.p_value < 1 ? e.p_value.toExponential(1) : '—'}</td>
              <td className="num dim">
                {(e.calibration_min * 100).toFixed(0)}–{(e.calibration_max * 100).toFixed(0)}%
                {' '}(med {(e.calibration_median * 100).toFixed(0)}%)
              </td>
              <td className="num dim">{e.calibration_blind}/{e.calibration_n}</td>
            </tr>
          ))}
        </tbody>
      </table></div>

      <p className="hint small">
        Chance would give {(a.expected_share * 100).toFixed(1)}%. &ldquo;Known
        members reach&rdquo; is what an undisputed {a.group_label} work scores
        with itself held out; &ldquo;cannot see&rdquo; is how many of them score
        zero, which is what a null result here has to be read against.
      </p>

      {a.nearest_in_group && a.nearest_outside_group && (
        <p className="assoc-control">
          nearest {a.group_label}: <code>{a.nearest_in_group.work}</code> Δ{' '}
          {a.nearest_in_group.delta}
          <span className="sep" />
          nearest outside: <code>{a.nearest_outside_group.work}</code> Δ{' '}
          {a.nearest_outside_group.delta}
        </p>
      )}

      {/* The second branch. Kept as its own block rather than folded into the
          table above, because it is group-blind: these percentiles say where
          the work sits in the canon and nothing about who wrote it, and across
          sixteen undisputed members of one group they span almost the whole
          range. */}
      {a.neighbourhood && (
        <div className={`hood-block ${a.neighbourhood.dominant ? 'lead' : ''}`}>
          <p className="hood-reading">{a.neighbourhood.reading}</p>
          <p className="hint small">
            nearest Δ {a.neighbourhood.nearest_delta}{' '}
            ({ordinal(a.neighbourhood.nearest_percentile)} pct) ·{' '}
            gap to next {a.neighbourhood.gap_to_second}{' '}
            ({ordinal(a.neighbourhood.gap_percentile)}) ·{' '}
            neighbourhood cohesion {a.neighbourhood.cohesion}{' '}
            ({ordinal(a.neighbourhood.cohesion_percentile)}).
            Percentiles of this corpus&apos;s own distribution — they say where
            the work sits, not who produced it.
          </p>
        </div>
      )}
    </div>
  )
}

//: `63rd`, not `63th` — the same rule the server applies to the prose it
//: writes, kept in step here because both end up on one screen.
function ordinal(n) {
  const i = Math.round(n)
  if (i % 100 >= 11 && i % 100 <= 13) return `${i}th`
  return `${i}${ { 1: 'st', 2: 'nd', 3: 'rd' }[i % 10] || 'th' }`
}

//: shares are fractions of *works*, shown as percentages because a threshold
//: reads better that way; the underlying unit is named in the row beside it.
function pct(x) {
  return `${Math.round(x * 100)}%`
}

function NodeList({ nodes, onSelect, reason, empty }) {
  if (!nodes) return <p className="hint">Loading…</p>
  if (!nodes.length) return <p className="hint small">{empty}</p>
  return (
    <ul className="finding-list">
      {nodes.map((n) => (
        <li key={n.id}>
          <button className="finding-row" onClick={() => onSelect(n.id)}>
            <span className={`badge t-${n.type}`}>{n.type}</span>
            <code>{n.id}</code>
          </button>
          {reason && (
            <p className="finding-reason">
              {n.rejected_reason || <em>no reason recorded</em>}
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}

function IntegrityStrip() {
  const [rebuild, setRebuild] = useState(null)
  const [integrity, setIntegrity] = useState(null)
  const [busy, setBusy] = useState(false)

  const check = useCallback(() => {
    setBusy(true)
    Promise.all([getRebuild(), getIntegrity()])
      .then(([rb, ig]) => { setRebuild(rb); setIntegrity(ig) })
      .catch(() => { setRebuild(null); setIntegrity(null) })
      .finally(() => setBusy(false))
  }, [])

  useEffect(check, [check])

  return (
    <div className="integrity">
      <div className="integrity-head">
        <h2>Integrity</h2>
        <button className="btn" onClick={check} disabled={busy}>
          {busy ? 'Checking…' : 'Re-check'}
        </button>
      </div>

      <div className="integrity-rows">
        <Check
          label="Rebuild from the log"
          detail={
            rebuild == null ? 'not run'
              : !rebuild.available ? 'no event log beside this projection'
                : rebuild.ok
                  ? `replayed ${rebuild.events_replayed} events to ${rebuild.nodes} nodes / ${rebuild.edges} edges, matching`
                  : 'the projection disagrees with the log'
          }
          state={rebuild == null || !rebuild.available ? 'unknown' : rebuild.ok ? 'pass' : 'fail'}
        />
        <Check
          label="Payload hashes"
          detail={
            integrity == null ? 'not run'
              : `${integrity.checked} checked · ${integrity.mismatched.length} mismatched · ${integrity.unhashed.length} unhashed`
          }
          state={
            integrity == null ? 'unknown'
              : integrity.mismatched.length ? 'fail' : 'pass'
          }
        />
      </div>

      {rebuild && rebuild.available && !rebuild.ok && (
        <pre className="integrity-diff">{rebuild.mismatch}</pre>
      )}

      <p className="hint small">
        The event log is ground truth and this database is a projection of it, so
        a mismatch means the database is wrong — not the log.
      </p>
    </div>
  )
}

function Check({ label, detail, state }) {
  return (
    <div className={`integrity-row r-${state}`}>
      <span className={`badge r-${state}`}>
        {state === 'pass' ? 'pass' : state === 'fail' ? 'fail' : '—'}
      </span>
      <span className="integrity-label">{label}</span>
      <span className="integrity-detail">{detail}</span>
    </div>
  )
}
