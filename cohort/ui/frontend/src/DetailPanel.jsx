import { explainProfileCodes } from './evidence-labels'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  acceptNode, attestNode, getAgent, getNode, getPassageContext, rejectNode,
  reopenNode, restoreEdge, retractEdge,
} from './api'
import { EDGE_STYLE, nodeTitle } from './graph-model'
import { usePresence } from './motion'
import Reveal from './Reveal'

export default function DetailPanel({ nodeId, onSelect, onClose, canWrite, onChanged }) {
  const [node, setNode] = useState(null)
  const [error, setError] = useState(null)
  const cardRef = useRef(null)
  // The card outlives `nodeId` by the length of its exit animation, which is
  // why `load` below no longer clears the node on close: what fades out should
  // be the card the reader just had, not an empty one.
  const card = usePresence(!!nodeId, 190)

  const load = useCallback(() => {
    if (!nodeId) return undefined
    let live = true
    setError(null)
    getNode(nodeId)
      .then((d) => live && setNode(d))
      .catch((e) => live && setError(e.message))
    return () => { live = false }
  }, [nodeId])

  useEffect(load, [load])

  // Following a related node from inside the card used to leave it scrolled
  // where the previous node's edge list had been — part-way down a different
  // node's provenance, with its title off screen.
  useEffect(() => {
    if (nodeId && cardRef.current) cardRef.current.scrollTop = 0
  }, [nodeId])

  // While the next node is in flight the current one stays on screen, dimmed,
  // rather than being replaced by "Loading…". Clicking through a chain of
  // related nodes is how this panel is mostly read, and blanking it at every
  // hop makes a fast graph feel slow. The bare loading line is for the one
  // case with nothing to hold: the first selection.
  const fetching = !!nodeId && !error && node?.id !== nodeId

  return (
    <>
      {/* The hint stays mounted and fades out under the card, so selecting a
          node crossfades instead of swapping one box for another. It is
          already `pointer-events: none`, so an invisible one is never in the
          way of the graph. */}
      <aside className={`panel empty ${nodeId ? 'gone' : ''}`} aria-hidden={!!nodeId}>
        <p className="hint">Select a node to see its provenance — who wrote it, what
        attests it, how it was verified, and whether its support is independent.</p>
      </aside>

      {card.mounted && (
        <aside
          ref={cardRef}
          className={`panel ${card.closing ? 'closing' : ''} ${node && fetching ? 'fetching' : ''}`}
        >
          <CloseButton onClose={onClose} />
          {error && <p className="error">{error}</p>}
          {!error && !node && <p className="hint">Loading…</p>}
          {/* Keyed by node, so moving between nodes crossfades the contents of
              a card that stays put — the card itself only animates when it
              opens or closes. */}
          {!error && node && (
            <NodeCard
              key={node.id}
              node={node}
              onSelect={onSelect}
              canWrite={canWrite}
              reload={load}
              onGraphChanged={onChanged}
            />
          )}
        </aside>
      )}
    </>
  )
}

function NodeCard({ node, onSelect, canWrite, reload, onGraphChanged }) {
  const support = node.independent_support

  return (
    <div className="panel-body">
      <header className="panel-head">
        <div className={`badge t-${node.type}`}>{node.type}</div>
        <div className={`badge s-${node.status}`}>{node.status}</div>
        {/* the level travels as a class too, so CSS can single out A0 —
            "nothing has been verified" is the one value not to skim past */}
        <div className={`badge assurance lvl-${node.assurance}`}>{node.assurance}</div>
      </header>

      <h2>{['claim', 'conjecture'].includes(node.type) && node.payload?.text
        ? explainProfileCodes(node.payload.text) : nodeTitle(node)}</h2>
      <code className="node-id">{node.id}</code>

      {/* Where this text is published, for a reader who wants to see the
          passage in its own context. Not what any check reads: verification
          re-fetches from the local archive whose bytes were hashed. */}
      {node.cbeta_url && (
        <a
          className="cbeta-link block"
          href={node.cbeta_url}
          target="_blank"
          rel="noreferrer noopener"
        >
          Read in CBETA Online ↗
        </a>
      )}

      {node.type === 'passage' && <PassageContext passageId={node.id} />}

      {canWrite && (
        <Verdict
          node={node}
          onDone={() => { reload(); onGraphChanged?.() }}
        />
      )}

      {node.rejected_reason && (
        <Section title="Rejected because">
          <p className="reason">{node.rejected_reason}</p>
        </Section>
      )}

      {support && (
        <Section title="Independent support">
          <div className={`support ${support.independent ? 'ok' : 'discounted'}`}>
            <div className="support-row">
              <span>attesting passages</span><strong>{support.attesting_count}</strong>
            </div>
            <div className="support-row">
              <span>distinct witnesses</span><strong>{support.distinct_witnesses}</strong>
            </div>
            <div className="support-row">
              <span>independent</span>
              <strong>{support.independent ? 'yes' : 'no'}</strong>
            </div>
          </div>
          {!support.independent && (
            <p className="note">
              Agreement here is evidence of shared transmission, not independent
              confirmation — the count above is unchanged, but these witnesses are
              related:
            </p>
          )}
          {support.non_independent_pairs.map(([a, b]) => (
            <div className="pair" key={`${a}|${b}`}>
              <button onClick={() => onSelect(a)}>{short(a)}</button>
              <span>↔</span>
              <button onClick={() => onSelect(b)}>{short(b)}</button>
            </div>
          ))}
        </Section>
      )}

      <Section title="Payload">
        <dl className="kv">
          {Object.entries(node.payload || {}).map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd>
            </div>
          ))}
        </dl>
      </Section>

      {node.verifications?.length > 0 && (
        <Section title={`Verifications (${node.verifications.length})`}>
          {node.verifications.map((v) => (
            <div className={`verification r-${v.payload.result}`} key={v.id}>
              <div className="v-head">
                <strong>{v.payload.method}</strong>
                <span className={`badge r-${v.payload.result}`}>{v.payload.result}</span>
                <span className={`badge assurance lvl-${v.payload.assurance_level}`}>
                  {v.payload.assurance_level}
                </span>
              </div>
              <p>{v.payload.detail}</p>
              {v.payload.limitations && (
                <p className="limitations"><em>Limitations:</em> {v.payload.limitations}</p>
              )}
            </div>
          ))}
        </Section>
      )}

      <EdgeList title="Outgoing" edges={node.edges_out} field="dst" onSelect={onSelect}
                canWrite={canWrite} onChanged={reload} />
      <EdgeList title="Incoming" edges={node.edges_in} field="src" onSelect={onSelect}
                canWrite={canWrite} onChanged={reload} />

      <Section title="Authorship">
        <ul className="authorship">
          {node.authorship.map((a, i) => (
            <li key={i}>
              <span className="action">{a.action}</span>
              <AuthorLink author={a.author} />
              <time>{a.at}</time>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  )
}

// A passage's excerpt, in its source — a KWIC line, like a corpus search
// result, but re-fetched live for this one already-recorded passage rather
// than read off the stored `excerpt`. That field can be as short as the
// matched span itself (find_attestations.py records whatever the source's own
// snippet was — sometimes a two-character run), which is not enough on its
// own for a reader to judge the citation against.
//
// Silent, not an error, when it 404s: a corpus not configured on this server
// and a passage recorded before `source_ref` existed both fail the same way,
// and the excerpt already shown above stands on its own either way — see
// `getPassageContext` in api.js.
function PassageContext({ passageId }) {
  const [ctx, setCtx] = useState(null)
  const [unavailable, setUnavailable] = useState(false)

  useEffect(() => {
    let live = true
    setCtx(null)
    setUnavailable(false)
    getPassageContext(passageId)
      .then((c) => { if (live) setCtx(c) })
      .catch(() => { if (live) setUnavailable(true) })
    return () => { live = false }
  }, [passageId])

  if (unavailable || !ctx) return null
  return (
    <p className="passage-context" title={`located by ${ctx.location}`}>
      {ctx.has_more_before && <span className="ctx-ellipsis">…</span>}
      {ctx.before}
      <mark>{ctx.excerpt}</mark>
      {ctx.after}
      {ctx.has_more_after && <span className="ctx-ellipsis">…</span>}
    </p>
  )
}

// An author's contribution history, one click from a node they wrote. The
// endpoint has always existed; nothing in the browser reached it until now.
//
// It is counts and never a score. A reputation number would reward volume, and
// an agent that proposes ten weak claims would outrank one that proposes a
// single good one — which is why docs/design.md §9 rules it out.
function AuthorLink({ author }) {
  const [report, setReport] = useState(null)
  const [open, setOpen] = useState(false)

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next && !report) getAgent(author).then(setReport).catch(() => setReport(false))
  }

  // A div rather than a span: it holds a `Reveal`, and a block inside an
  // inline element is invalid nesting. The layout is unchanged — `.author-wrap`
  // sets `display` explicitly.
  return (
    <div className="author-wrap">
      <button className={`author link ${open ? 'on' : ''}`} onClick={toggle} title="Contribution history">
        {author}
      </button>
      <Reveal open={open}>
        <div className="author-report">
          {report === false && <em>no report available</em>}
          {report === null && <em>loading…</em>}
          {report && (
            <>
              {Object.entries(report)
                .filter(([, v]) => typeof v === 'number')
                .map(([k, v]) => (
                  <span key={k}><b>{v}</b> {k.replace(/_/g, ' ')}</span>
                ))}
              <span className="hint small">counts, not a score</span>
            </>
          )}
        </div>
      </Reveal>
    </div>
  )
}

function CloseButton({ onClose }) {
  if (!onClose) return null
  return (
    <button className="panel-close" onClick={onClose} aria-label="Close inspector"
            title="Close (Esc)">
      <CloseIcon />
    </button>
  )
}

function CloseIcon() {
  // Two strokes, not a `×` character. `place-items: center` centres the *line
  // box*, and the multiplication sign's ink sits low inside its em box — a
  // measured 0.96px below the middle of a 24px button, which is plainly
  // visible on a circle that small. It also varies by font, so the glyph is
  // not something this button can centre reliably. Same reasoning as
  // `GearIcon` above: geometry, symmetric about (6,6).
  return (
    <svg viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path
        d="M3 3 L9 9 M9 3 L3 9"
        stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
      />
    </svg>
  )
}

function EdgeList({ title, edges, field, onSelect, canWrite, onChanged }) {
  if (!edges?.length) return null
  const live = edges.filter((e) => !e.retracted).length
  return (
    <Section title={`${title} (${live})`}>
      {edges.map((e) => (
        <EdgeRow
          key={e.id} edge={e} field={field} onSelect={onSelect}
          canWrite={canWrite} onChanged={onChanged}
        />
      ))}
    </Section>
  )
}

// One edge, and the researcher's ability to withdraw it.
//
// Edges have no promotion ladder, so until retraction existed a wrong one was
// permanent — and the edges drawn most prominently here (`parallel_of`,
// `descends_from`, `contradicts`) are exactly the ones that change conclusions.
// A mistaken `parallel_of` does not add noise; it *suppresses* independent
// support that genuinely exists, in the direction of this system's own thesis.
//
// A retracted edge is shown struck through with its reason rather than removed:
// "the researcher withdrew this" and "this was never asserted" are different
// facts about the record, and only one of them is worth reading.
function EdgeRow({ edge: e, field, onSelect, canWrite, onChanged }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [refusal, setRefusal] = useState(null)

  const act = async () => {
    if (!reason.trim()) {
      setRefusal({ rule: 'MissingRejectionReason', message: 'a reason is required' })
      return
    }
    setBusy(true)
    setRefusal(null)
    try {
      await (e.retracted ? restoreEdge : retractEdge)(e.id, reason)
      setOpen(false)
      setReason('')
      onChanged?.()
    } catch (err) {
      setRefusal({ rule: err.rule, message: err.message, status: err.status })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`edge-row ${e.discounts ? 'discount' : ''} ${e.retracted ? 'retracted' : ''}`}>
      <div className="edge-line">
        <span className="edge-type">{EDGE_STYLE[e.type]?.label || e.type}</span>
        {e.discounts && !e.retracted && <span className="chip">discounts</span>}
        {e.retracted && <span className="chip withdrawn">withdrawn</span>}
        <button onClick={() => onSelect(e[field])}>{short(e[field])}</button>
        {canWrite && (
          <button className="edge-act" onClick={() => setOpen((v) => !v)} disabled={busy}>
            {e.retracted ? 'restore' : 'retract'}
          </button>
        )}
      </div>
      {/* A contradicts edge is drawn as heavily as evidence, so the grounds
          for it belong next to it — an unexplained disagreement asserted
          this prominently is worse than none. */}
      {e.reason && <p className="edge-reason">{e.reason}</p>}
      {e.retracted && e.retracted_reason && (
        <p className="edge-reason withdrawn">withdrawn: {e.retracted_reason}</p>
      )}
      <Reveal open={open}>
        <div className="edge-verdict">
          <textarea
            rows={2} className="reason-input"
            placeholder={e.retracted ? 'Why restore it?' : 'Why withdraw it?'}
            value={reason} onChange={(ev) => setReason(ev.target.value)}
          />
          <button className={`btn ${e.retracted ? 'accept' : 'reject'}`} disabled={busy} onClick={act}>
            {e.retracted ? 'Restore edge' : 'Retract edge'}
          </button>
          <p className="hint small">
            Nothing is deleted. The edge stays in the log and in the graph,
            marked withdrawn, and stops counting toward independence.
          </p>
          <Reveal open={!!refusal}>
            <div className="refusal">
              {refusal?.rule && <strong>{refusal.rule}</strong>}
              <p>{refusal?.message}</p>
            </div>
          </Reveal>
        </div>
      </Reveal>
    </div>
  )
}

// The researcher's own actions. Deliberately the only writes in the UI, and
// only mounted when the server was started with --allow-writes: docs/design.md §8
// makes accept/reject the one thing agents may never do, so the interface for
// it should look like an authority being exercised, not a form being filled.
function Verdict({ node, onDone }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [refusal, setRefusal] = useState(null)

  const act = async (fn, needsReason) => {
    if (needsReason && !reason.trim()) {
      // Mirrors MissingRejectionReason locally so the researcher gets the
      // answer immediately; the server enforces it regardless.
      setRefusal({ rule: 'MissingRejectionReason', message: 'a reason is required' })
      return
    }
    setBusy(true)
    setRefusal(null)
    try {
      await fn()
      setReason('')
      onDone()
    } catch (e) {
      setRefusal({ rule: e.rule, message: e.message, status: e.status })
    } finally {
      setBusy(false)
    }
  }

  const isRejected = node.status === 'rejected'
  const canAccept = node.status === 'attested'
  // A proposed node is one rung short, not a refusal. Telling the researcher
  // "only an attested node can be accepted" and stopping there was a dead end:
  // attestation is a mechanical check, not a judgement, so offer to run it.
  const canAttest = node.status === 'proposed'

  return (
    <section className="verdict">
      <h3>Researcher decision</h3>
      {!isRejected && (
        <p className="hint small">
          {canAccept
            ? 'Accepting makes this citable and usable as a premise by other agents.'
            : canAttest
              ? 'The ladder runs proposed → attested → accepted, and no rung may be '
                + 'skipped. Attesting is the mechanical check — do this node\u2019s '
                + 'citations resolve? — not a judgement about whether it is right. '
                + 'The graph refuses it if nothing attests this node.'
              : `Only an attested node can be accepted — this one is ${node.status}.`}
        </p>
      )}
      <textarea
        className="reason-input"
        placeholder={isRejected ? 'Why reopen it?' : 'Reason (required to reject)'}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={2}
      />
      <div className="verdict-actions">
        {isRejected ? (
          <button
            className="btn reopen" disabled={busy}
            onClick={() => act(() => reopenNode(node.id, reason), true)}
          >Reopen</button>
        ) : (
          <>
            {canAttest && (
              <button
                className="btn attest" disabled={busy}
                onClick={() => act(() => attestNode(node.id), false)}
                title="Run the mechanical check: do this node's citations resolve?"
              >Attest</button>
            )}
            <button
              className="btn accept" disabled={busy || !canAccept}
              onClick={() => act(() => acceptNode(node.id), false)}
            >Accept</button>
            <button
              className="btn reject" disabled={busy}
              onClick={() => act(() => rejectNode(node.id, reason), true)}
            >Reject</button>
          </>
        )}
      </div>
      {/* A refusal is the system declining to record something, so it arrives
          rather than blinking into place — and it is the last thing in a
          scrolling panel, where a jump would move the buttons just pressed. */}
      <Reveal open={!!refusal}>
        <div className={`refusal ${refusal?.status === 409 ? 'conflict' : ''}`}>
          {refusal?.rule && <strong>{refusal.rule}</strong>}
          <p>{refusal?.message}</p>
          {refusal?.status === 409 && (
            <p className="small">Single-writer discipline: nothing was changed.</p>
          )}
        </div>
      </Reveal>
    </section>
  )
}

function Section({ title, children }) {
  return (
    <section className="section">
      <h3>{title}</h3>
      {children}
    </section>
  )
}

const short = (id) => {
  const s = String(id)
  return s.length > 34 ? `${s.slice(0, 33)}…` : s
}
