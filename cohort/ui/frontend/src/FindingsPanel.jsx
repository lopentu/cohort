import { Button, Badge } from './components/ui'
import { useTranslation } from 'react-i18next'
import { tr } from './i18n'
import CbetaLink from './CbetaLink'
import ProposalFieldHelp, { proposalFieldLabel } from './ProposalFieldHelp'
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
  useTranslation()
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

      <details className="inquiry-details">
        <summary>{tr("Record integrity checks")}</summary>
        <IntegrityStrip />
      </details>

      <details className="inquiry-details">
      <summary>{tr("Researcher decisions: accepted and rejected records")}</summary>
      <div className="findings-cols">
        <div>
          <h2>{tr("Researcher-approved")}</h2>
          <p className="hint small">{tr("Records approved by the researcher.")}</p>
          <NodeList
            nodes={citable}
            onSelect={onSelect}
            empty="No researcher-approved records yet."
          />
        </div>

        <div>
          <h2>{tr("Rejected")}</h2>
          <p className="hint small">{tr("Researcher rejections and their reasons.")}</p>
          <NodeList
            nodes={rejected}
            onSelect={onSelect}
            reason
            empty="Nothing has been rejected."
          />
        </div>
      </div>
      </details>
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
  useTranslation()
  const [open, setOpen] = useState(null)
  const [dossier, setDossier] = useState(null)

  const toggle = (id) => {
    if (open === id) { setOpen(null); setDossier(null); return }
    setOpen(id)
    setDossier(null)
    getDossier(id).then(setDossier).catch(() => setDossier(null))
  }

  if (!findings) return <p className="hint">{tr("Loading…")}</p>

  return (
    <div className="hypotheses">
      <h2>{tr("Hypotheses")}<span className="refusal-total">{findings.count}</span>
      </h2>
      <p className="hint small">{tr("Claims and conjectures, newest first. Not ranked by confidence.")}</p>

      {findings.findings.length === 0 ? (
        <p className="hint small">{tr("Nothing has been proposed yet.")}</p>
      ) : (
        <ul className="hyp-list">
          {findings.findings.map((f) => (
            <li key={f.id} className={`hyp ${open === f.id ? 'open' : ''}`}>
              <Button className="hyp-head" onClick={() => toggle(f.id)}>
                <Badge className={`badge t-${f.type}`}>{tr(f.type)}</Badge>
                <span className="hyp-text">{f.assertion ? explainProfileCodes(f.assertion) : f.id}</span>
              </Button>

              <div className="hyp-marks">
                <span className={`chip s-${f.status}`}>{tr(f.status)}</span>
                {f.review_state && <span className="chip review-state" title={tr(f.review_state.explanation)}>{tr(f.review_state.label)}</span>}
                <span className="chip">{f.assurance.replace(/_/g, ' ').toLowerCase()}</span>
                <span
                  className={`chip ${
                    f.support.vacuous ? 'unsupported' : f.support.independent ? '' : 'discounted'
                  }`}
                >
                  {f.support.vacuous ? (
                    tr("nothing attests it yet")
                  ) : (
                    <>
                      {f.support.attesting_count} {tr("attesting ·")}{' '}
                      {tr('{{count}} witnesses', { count: f.support.distinct_witnesses })} ·{' '}
                      {f.support.independent ? tr('independent') : tr('shared descent')}
                    </>
                  )}
                </span>
                {f.prospective_result && (
                  <span className={`chip r-${f.prospective_result}`}>{tr("prospective test:")}{tr(f.prospective_result)}
                  </span>
                )}
                {!f.prospective_result && f.has_prospective_query && (
                  <span className="chip">{tr("prospective query not yet run")}</span>
                )}
                {f.has_dossier && <span className="chip">{tr("dossier")}</span>}
              </div>

              {f.support.vacuous && (
                <p className="hint small discount-note">{tr("No supporting passage is recorded.")}</p>
              )}

              {!f.support.vacuous && !f.support.independent && (
                <p className="hint small discount-note">{tr("Related source texts support this proposal; their support is not independent.")}</p>
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
  useTranslation()
  if (!d) return <p className="hint small">{tr("Loading the dossier…")}</p>
  const fields = Object.entries(d.dossier || {})
  const test = d.prospective_test
  return (
    <div className="dossier">
      {fields.length > 0 && (
        <dl className="dossier-fields">
          {fields.map(([k, v]) => (
            <div key={k}>
              <dt>{proposalFieldLabel(k)}</dt>
              <dd><ProposalFieldHelp field={k} />{typeof v === 'string' ? explainProfileCodes(v) : v}</dd>
            </div>
          ))}
        </dl>
      )}

      {d.prior_art?.length > 0 && (
        <p className="hint small">{tr("Searches before proposal:")}{d.prior_art.map((q) => q.text).join('; ')}
        </p>
      )}

      {d.prospective_queries?.map((q) => (
        <div className="prospective" key={q.id}>
          <h4>{tr("Prospective test")}</h4>
          <p className="prospective-q"><code>{q.text}</code></p>
          {q.expectation ? (
            <p className="prospective-pred">{tr("Predicted")}<strong>{q.expectation === 'at_most' ? tr('at most') : tr('at least')}{' '}
              {q.expected_hits}</strong>{tr("— saved with the proposal. This may reuse an earlier search.")}</p>
          ) : (
            <p className="hint small">{tr("No prediction was recorded for this query.")}</p>
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
          <h4>{tr("Evidence (")}{d.evidence.length})</h4>
          <ul>
            {d.evidence.map((e) => (
              <li key={e.passage_id}>
                <Button className="ev-ref" onClick={() => onSelect(e.passage_id)}>
                  <code>{e.canonical_ref}</code>
                </Button>
                <CbetaLink url={e.cbeta_url} />
                <span className="chip">{tr(e.assurance.replace(/_/g, ' ').toLowerCase())}</span>
                <p className="ev-excerpt">{e.excerpt}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {d.latest_verifications?.length > 0 && (
        <div className="dossier-verifications">
          <h4>{tr("Verifications")}</h4>
          <p className="hint small">{tr("Latest check for each method. Mechanical results and reviewer comments are shown separately.")}</p>
          {d.latest_verifications.map((v) => (
            <div key={v.id} className="verification">
              <div className="verification-head">
                <Badge className={`badge r-${v.payload.result}`}>{tr(v.payload.result)}</Badge>
                <span>{tr(v.payload.method)}</span>
              </div>
              <p className="v-detail"><strong>{tr("Machine:")}</strong> {v.payload.detail}</p>
              {v.payload.limitations && (
                <p className="v-limits"><strong>{tr("Does not establish:")}</strong>{' '}
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
  useTranslation()
  if (!nodes) return <p className="hint">{tr("Loading…")}</p>
  if (!nodes.length) return <p className="hint small">{empty}</p>
  return (
    <ul className="finding-list">
      {nodes.map((n) => (
        <li key={n.id}>
          <Button className="finding-row" onClick={() => onSelect(n.id)}>
            <Badge className={`badge t-${n.type}`}>{tr(n.type)}</Badge>
            <code>{n.id}</code>
          </Button>
          {reason && (
            <p className="finding-reason">
              {n.rejected_reason || <em>{tr("no reason recorded")}</em>}
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}

function IntegrityStrip() {
  useTranslation()
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
        <h2>{tr("Integrity")}</h2>
        <Button className="btn" onClick={check} disabled={busy}>
          {busy ? tr("Checking…") : tr("Re-check")}
        </Button>
      </div>

      <div className="integrity-rows">
        <Check
          label={tr('Rebuild from the log')}
          detail={
            rebuild == null ? tr('not run')
              : !rebuild.available ? tr('no event log beside this projection')
                : rebuild.ok
                  ? tr('Replayed {{events}} events to {{nodes}} nodes / {{edges}} edges, matching', { events: rebuild.events_replayed, nodes: rebuild.nodes, edges: rebuild.edges })
                  : tr('the projection disagrees with the log')
          }
          state={rebuild == null || !rebuild.available ? 'unknown' : rebuild.ok ? 'pass' : 'fail'}
        />
        <Check
          label={tr('Payload hashes')}
          detail={
            integrity == null ? tr('not run')
              : tr('{{checked}} checked · {{mismatched}} mismatched · {{unhashed}} unhashed', { checked: integrity.checked, mismatched: integrity.mismatched.length, unhashed: integrity.unhashed.length })
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

      <p className="hint small">{tr("Checks whether the database matches the event log.")}</p>
    </div>
  )
}

function Check({ label, detail, state }) {
  return (
    <div className={`integrity-row r-${state}`}>
      <Badge className={`badge r-${state}`}>
        {state === 'pass' ? tr('pass') : state === 'fail' ? tr('fail') : '—'}
      </Badge>
      <span className="integrity-label">{label}</span>
      <span className="integrity-detail">{detail}</span>
    </div>
  )
}
