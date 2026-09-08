import { explainProfileCodes } from './evidence-labels'
import { useCallback, useEffect, useState } from 'react'
import {
  getCitable,
  getDossier,
  getFindings,
  getIntegrity,
  getRebuild,
  getRejected,
} from './api'

// The researcher's output view, and the graph's self-checks.
//
// These four capabilities existed in the Python API and in the HTTP API but
// were unreachable from the browser, which broke the parity promise
// (tests/test_parity.py now fails if that happens again).
//
// Citable and rejected belong side by side deliberately. Only accepted nodes
// may be cited, and rejections-with-reasons are part of the scholarly output
// rather than a failure list (docs/design.md §8) — showing findings without
// showing what was thrown out and why would misrepresent the record.
//
// The two integrity checks are on demand, not ambient: `verify_integrity`'s
// own contract is that one tampered row must not turn every future read into
// a crash, so nothing here runs on a timer.

export default function FindingsPanel({ onSelect }) {
  const [citable, setCitable] = useState(null)
  const [rejected, setRejected] = useState(null)
  const [findings, setFindings] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let live = true
    Promise.all([getCitable(), getRejected(), getFindings()])
      .then(([c, r, f]) => {
        if (!live) return
        setCitable(c); setRejected(r); setFindings(f)
      })
      .catch((e) => live && setError(e.message))
    return () => { live = false }
  }, [])

  if (error) return <section className="findings"><p className="error">{error}</p></section>

  return (
    <section className="findings">

      <Hypotheses findings={findings} onSelect={onSelect} />

      <IntegrityStrip />

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
    </section>
  )
}

// The research questions, above everything else on this tab.
//
// A COHORT graph used to record what was *found* and never what was being
// asked, so this page had no title it could honestly give itself. A question
// is not evidence and not a query: it asserts nothing, and it is not runnable.
//
// What it shows is a tally, never a verdict. Three hypotheses under a question
// is not a question answered, which is also why the `addresses` edge points
// from the answer to the question rather than the other way round.
// Claims and conjectures as hypotheses rather than as node ids.
//
// All of this was already in the graph and reachable only by walking edges by
// hand — which is the step at which the honest fields get skipped. A dossier
// that names what could have gone wrong in the selection, and what else could
// explain the same evidence, is worth more than another support count.
//
// Deliberately unordered by support. A list sorted by "most attested" would be
// a confidence ranking wearing a different hat, which is the habit this whole
// system exists to break.
function Hypotheses({ findings, onSelect }) {
  const [open, setOpen] = useState(null)
  const [dossier, setDossier] = useState(null)

  const toggle = (id) => {
    if (open === id) { setOpen(null); setDossier(null); return }
    setOpen(id)
    setDossier(null)
    getDossier(id).then(setDossier).catch(() => setDossier(null))
  }

  if (!findings) return <p className="hint">Loading…</p>

  return (
    <div className="hypotheses">
      <h2>
        Hypotheses <span className="refusal-total">{findings.count}</span>
      </h2>
      <p className="hint small">
        Every claim and conjecture, newest first and <strong>not ranked</strong>.
        Sorting these by how much attests them would be a confidence score under
        another name.
      </p>

      {findings.findings.length === 0 ? (
        <p className="hint small">Nothing has been proposed yet.</p>
      ) : (
        <ul className="hyp-list">
          {findings.findings.map((f) => (
            <li key={f.id} className={`hyp ${open === f.id ? 'open' : ''}`}>
              <button className="hyp-head" onClick={() => toggle(f.id)}>
                <span className={`badge t-${f.type}`}>{f.type}</span>
                <span className="hyp-text">{f.assertion ? explainProfileCodes(f.assertion) : f.id}</span>
              </button>

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
                {f.prospective_result && (
                  <span className={`chip r-${f.prospective_result}`}>
                    prospective test: {f.prospective_result}
                  </span>
                )}
                {!f.prospective_result && f.has_prospective_query && (
                  <span className="chip">prospective query not yet run</span>
                )}
                {f.has_dossier && <span className="chip">dossier</span>}
              </div>

              {f.support.vacuous && (
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

              {open === f.id && <Dossier d={dossier} onSelect={onSelect} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Dossier({ d, onSelect }) {
  if (!d) return <p className="hint small">Loading the dossier…</p>
  const fields = Object.entries(d.dossier || {})
  const test = d.prospective_test
  return (
    <div className="dossier">
      {fields.length > 0 && (
        <dl className="dossier-fields">
          {fields.map(([k, v]) => (
            <div key={k}>
              <dt>{k.replace(/_/g, ' ')}</dt>
              <dd>{typeof v === 'string' ? explainProfileCodes(v) : v}</dd>
            </div>
          ))}
        </dl>
      )}

      {d.prior_art?.length > 0 && (
        <p className="hint small">
          Prior art actually searched before proposing: {d.prior_art.map((q) => q.text).join('; ')}
        </p>
      )}

      {d.prospective_queries?.map((q) => (
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
