import { corpusInquiryDraft } from './corpus-inquiry'
import { useCallback, useEffect, useRef, useState } from 'react'
import { askQuestion, getQuestions, getRunConfig, getRuns, startRun, stopRun } from './api'

// Which questions the researcher has hidden from the Graph tab, so it stays a
// working view rather than an ever-growing history. Hiding removes nothing —
// docs/design.md principle 1 makes the event log the one place a question
// could be un-asked, and there is no un-ask event — it only changes what this
// browser draws (graph-model.js's `hiddenIdsForQuestions`), so it is a
// localStorage preference (Settings.jsx's pattern, wrapped in try/catch for
// the same reason: a private window must not white-screen the app) rather
// than a graph write.
const HIDDEN_KEY = 'cohort.hiddenQuestions'

export function loadHiddenQuestions() {
  try {
    const v = JSON.parse(localStorage.getItem(HIDDEN_KEY) || '[]')
    return new Set(Array.isArray(v) ? v : [])
  } catch {
    return new Set()
  }
}

export function saveHiddenQuestions(ids) {
  try {
    localStorage.setItem(HIDDEN_KEY, JSON.stringify([...ids]))
  } catch {
    /* storage unavailable: hiding still applies for this session */
  }
}

// Starting an agent run from the browser.
//
// This is the only part of the UI that spends money, and the design follows
// from that. Three things are deliberate:
//
//   * A configured spending threshold is visible. An operator can disable
//     monetary stopping; accounting remains visible for every run.
//
//   * Refusals are shown as results, not as errors. A run whose agent was
//     refused five times did not fail; that is the write boundary working, and
//     it is the most interesting thing on the screen (docs/design.md §15).
//
// A run is one *or several* agents. What several buy is declared viewpoint
// diversity, so each row asks for a corpus scope and a method — real research
// commitments that change what an agent looks at — rather than a personality.
// The agents cannot see each other: there is no channel and no shared
// transcript (docs/design.md §5 principle 3), and the panel says so rather than
// letting a viewer assume they collaborate.

const DEMO_EXAMPLES = [
  {
    label: 'Find related passages: T0603',
    question: 'Which passages elsewhere in the corpus are closely related to the Yin chi ru jing (陰持入經, T0603), and what might explain those relationships?',
    criteria: 'Find related passages and provide source references so I can inspect them. Consider quotation, commentary and recurring expressions as possible explanations. If you compare corpus groups, check whether repeated material drives the result by excluding the relevant comparison text and repeating the calculation. Report the computed results and their limitations. Do not infer a translator attribution.',
  },
  {
    label: 'T0453: find a parallel',
    question: 'Which texts in this corpus contain passages closely matching the Maitreya descent text (彌勒下生經, T0453)?',
    criteria: 'Find a matching text without being given its identifier. Return source references, matching passages and computed overlap. Explain whether shared wording is independent evidence for translator identity. Report no match if retrieval finds nothing; do not attribute the text.',
  },
  {
    label: 'Test recurring formulae',
    question: 'Which expressions in the Yin chi ru jing (陰持入經, T0603) are widespread in other texts, and which have a more restricted distribution?',
    criteria: 'List the strings actually returned by the evidence tools, inspect their occurrences in context and report which corpus groups contain them. Separate observed distribution from an interpretation about genre. State what cannot be established from these observations.',
  },
]

const ACTIVE = new Set(['starting', 'running'])

// A reviewer's task is nearly always the same sentence, and the list of what
// there is to review is appended by the server after the workers finish — the
// browser cannot know it at configuration time. So this is a real default, not
// placeholder text the researcher has to replace.
const REVIEWER_TASK =
  'Review each pending claim: re-check that its cited passages say what it '
  + 'claims they say, and give a verdict.'

export default function RunPanel({ instructionSeed, onSeedConsumed, onGraphChanged, hiddenQuestions, onToggleHiddenQuestion }) {
  const [config, setConfig] = useState(null)
  const [runs, setRuns] = useState(null)
  const [agents, setAgents] = useState([blankAgent(0)])
  // Auto by default. A launcher whose first screen is an empty task box asks
  // the researcher to write agent instructions before they have written the
  // question, and what comes out is a task with no recorded question behind
  // it — which is how every run so far ended up unattached to anything the
  // graph could group it under. Customize is one click away and changes
  // nothing about what the run may do; the ceilings are the server's either
  // way.
  const [mode, setMode] = useState('auto')
  const [questionId, setQuestionId] = useState(null)
  const [budget, setBudget] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const settledRef = useRef(null)

  useEffect(() => {
    getRunConfig()
      .then((c) => { setConfig(c); setBudget(c.default_budget_usd == null ? '' : String(c.default_budget_usd)) })
      .catch((e) => setError(e.message))
  }, [])

  const [draftSeed] = useState(() => corpusInquiryDraft(instructionSeed))
  useEffect(() => {
    // Consume the handoff once so a later visit cannot resurrect an old draft.
    if (instructionSeed) onSeedConsumed?.()
  }, [instructionSeed, onSeedConsumed])

  const poll = useCallback(async () => {
    try {
      const data = await getRuns()
      setRuns(data)
      // Reload the graph once, when a run stops being active — an agent run
      // writes continuously, so the view behind this panel is stale.
      const id = data.current?.id ?? data.history?.[0]?.id
      const active = ACTIVE.has(data.current?.state)
      if (!active && id && settledRef.current !== id) {
        settledRef.current = id
        onGraphChanged?.()
      }
      return active
    } catch {
      return false
    }
  }, [onGraphChanged])

  useEffect(() => {
    let timer
    let cancelled = false
    const tick = async () => {
      const active = await poll()
      if (cancelled) return
      timer = setTimeout(tick, active ? 900 : 4000)
    }
    tick()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [poll])

  const current = runs?.current
  const active = ACTIVE.has(current?.state)
  const last = runs?.history?.[0]
  const shown = current || last

  const update = (i, patch) =>
    setAgents((prev) => prev.map((a, j) => (j === i ? { ...a, ...patch } : a)))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await startRun(mode === 'auto' ? {
        budget_usd: config.max_budget_usd == null ? null : Number(budget),
        auto: true,
        question_id: questionId,
      } : {
        budget_usd: config.max_budget_usd == null ? null : Number(budget),
        question_id: questionId,
        agents: agents.map((a) => ({
          agent_id: a.agent_id,
          instructions: a.instructions,
          corpus_scope: a.corpus_scope,
          method_label: a.method_label,
          model: a.model,
          role: a.role,
        })),
      })
      settledRef.current = null
      await poll()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (error && !config) return <section className="runs"><p className="error">{error}</p></section>
  if (!config) return <section className="runs"><p className="hint">Loading…</p></section>

  const blocked = !config.model_configured || !config.corpus_available

  return (
    <section className="runs">
      <h2>Inquiry</h2>
      <p className="hint">Choose an example or write a question to begin.</p>

      {blocked && (
        <p className="warn">
          {!config.corpus_available
            ? 'No corpus is configured on this server, so an agent would have nothing to search.'
            : config.config_error}
      </p>
      )}

      <Questions
        draft={draftSeed}
        selected={questionId}
        onSelect={setQuestionId}
        hidden={hiddenQuestions}
        onToggleHidden={onToggleHiddenQuestion}
      />

      <form className="run-form" onSubmit={submit}>
        <h3>2. Start a new agent run</h3>
        <details className="inquiry-details" open={mode === 'custom' ? true : undefined}>
        <summary>Agent roles and settings</summary>
        <p className="hint small">Workers retrieve evidence and propose findings. Reviewers check citations using a different model family. Only you can accept findings.
      </p>
        {mode === 'auto' ? (
          <AutoPlan config={config} question={questionId} />
        ) : agents.map((a, i) => (
          <div className="agent-card" key={a.key}>
            <div className="agent-head">
              <span className="agent-n">
                {a.role === 'reviewer' ? `Reviewer ${i + 1}` : `Worker ${i + 1}`}
              </span>
              <input
                className="agent-id"
                value={a.agent_id}
                onChange={(e) => update(i, { agent_id: e.target.value })}
                aria-label={`Agent ${i + 1} id`}
              />
              {agents.length > 1 && (
                <button
                  type="button" className="btn tiny"
                  onClick={() => setAgents(agents.filter((_, j) => j !== i))}
                >remove</button>
              )}
            </div>
            <label className="field">
              <span>Task</span>
              <textarea
                rows={3}
                placeholder="e.g. Find attestations for 色即是空 and propose one claim about how it is distributed."
                value={a.instructions}
                onChange={(e) => update(i, { instructions: e.target.value })}
              />
            </label>
            <div className="field-row">
              <label className="field">
                <span>Model</span>
                <select
                  value={a.model}
                  onChange={(e) => update(i, { model: e.target.value })}
                >
                  <option value="">{config.model || 'server default'}</option>
                  {(config.models || [])
                    .filter((m) => m !== config.model)
                    .map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </label>
              <label className="field">
                <span>Corpus scope</span>
                <input
                  placeholder="e.g. Prajñāpāramitā translations only"
                  value={a.corpus_scope}
                  onChange={(e) => update(i, { corpus_scope: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Method</span>
                <input
                  placeholder="e.g. phrase distribution"
                  value={a.method_label}
                  onChange={(e) => update(i, { method_label: e.target.value })}
                />
              </label>
            </div>
            <p className="hint small">
              {a.role === 'reviewer' ? (
                <>
                  Reviews worker proposals after retrieval. Failed citation checks block attestation.
                </>
              ) : (
                <>
                  Scope and method are saved and included in the task. Each agent needs a different model family.
                </>
              )}
            </p>
          </div>
        ))}

        {mode === 'auto' ? (
          <button type="button" className="btn customize-open"
                  onClick={() => setMode('custom')}>
            Customize the roster…
          </button>
        ) : (
        <div className="agent-add">
          <button
            type="button" className="btn"
            disabled={agents.length >= (config.max_agents || 1)}
            onClick={() => setAgents([...agents, blankAgent(agents.length)])}
          >
            + Add agent
          </button>
          <button
            type="button" className="btn"
            disabled={agents.length >= (config.max_agents || 1)}
            onClick={() => setAgents([...agents, blankAgent(agents.length, 'reviewer')])}
          >
            + Add reviewer
          </button>
          <span className="hint small">
            {agents.length} of {config.max_agents} agents. Each uses a different model family.
            Agents cannot review their own claims.
            {agents.length > 1 && (config.models || []).length < agents.length && (
              <> Set <code>OPENROUTER_MODELS</code> to add more.</>
            )}
          </span>
          <button type="button" className="btn tiny"
                  onClick={() => setMode('auto')}>
            back to auto
          </button>
        </div>
        )}

        </details>
        {config.max_budget_usd != null && <div className="field-row">
          <label className="field">
            <span>Budget (USD)</span>
            <input
              type="number" step="0.01" min="0.01" max={config.max_budget_usd}
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
            />
            <small>
              stopping threshold for later calls; server ceiling ${config.max_budget_usd.toFixed(2)}
            </small>
          </label>
        </div>}

        <div className="run-actions">
          <button
            className="btn accept" type="submit"
            disabled={
              busy || active || blocked
              || (mode === 'auto'
                ? !questionId
                : agents.some((a) => !a.instructions.trim()))
            }
          >
            {active
              ? 'Run in progress…'
              : mode === 'auto'
                ? `Inquire (${(config.plan || []).length} agent${(config.plan || []).length === 1 ? '' : 's'})`
                : `Start run (${agents.length} agent${agents.length === 1 ? '' : 's'})`}
          </button>
          {active && (
            <button className="btn reject" type="button" onClick={() => stopRun().then(poll)}>
              Stop after this turn
            </button>
          )}
        </div>
        <p className="hint small">
          Model {config.model || '—'} · at most {config.max_turns} turns each · the
          run holds this graph&apos;s writer lock, so accept/reject will conflict
          until it finishes.
        </p>
      </form>

      {error && <p className="error">{error}</p>}

      {shown && (active ? <RunReport run={shown} active={active} /> :
        <details className="inquiry-details"><summary>Latest completed run</summary>
          <RunReport run={shown} active={false} /></details>)}

      <RunHistory runs={runs?.recorded} />
    </section>
  )
}

// Runs read back out of the event log, not out of this process's memory.
//
// `history` above is what this server has run since it started; before runs
// were events, that was the only record there was, and a restart erased every
// run ever launched from here. These survive, which is also what makes a run
// something you can go back and census one at a time.
function RunHistory({ runs }) {
  if (!runs?.length) return null
  return (
    <details className="run-history inquiry-details">
      <summary>Previous agent runs ({runs.length})</summary>
      <p className="hint small">
        Earlier runs saved in this session.
      </p>
      <ul className="run-history-list">
        {runs.map((r) => (
          <li key={r.run_id} className="run-history-item">
            <div className="run-history-head">
              <code className="run-id">{r.run_id}</code>
              <span className={`run-state state-${r.state || 'open'}`}>
                {r.state || 'open'}
              </span>
              <time>{r.started_at}</time>
              <span className="run-figures">
                {r.spent_usd != null ? `$${r.spent_usd.toFixed(5)}` : '—'} ·{' '}
                {r.calls} call{r.calls === 1 ? '' : 's'} · {r.events} event
                {r.events === 1 ? '' : 's'}
                {r.refusals > 0 && ` · ${r.refusals} refused`}
              </span>
            </div>
            <div className="run-history-agents">
              {r.agents.map((a) => (
                <span key={a.agent_id} className="chip">
                  {a.role === 'reviewer' ? '\u2713 ' : ''}
                  {a.agent_id} · {a.model || 'default model'}
                  {a.corpus_scope ? ` · ${a.corpus_scope}` : ''}
                </span>
              ))}
            </div>
            {r.error && <p className="error small">{r.error}</p>}
          </li>
        ))}
      </ul>
    </details>
  )
}

// The question, and asking one. Moved here from Findings: a question is where
// work starts, not something that was found, and asking it in one tab to run
// against it in another made the connection between them a thing the
// researcher had to remember rather than a thing the tool did.
//
// Only the researcher may ask — setting the agenda is the supervision, so the
// form is absent rather than disabled on a read-only server (the route is not
// mounted either).
function Questions({ draft, selected, onSelect, hidden, onToggleHidden }) {
  const [data, setData] = useState(null)
  const [asking, setAsking] = useState(!!draft)
  const [text, setText] = useState(draft?.question || '')
  const [answerable, setAnswerable] = useState(draft?.instructions || '')
  const [sourceRef, setSourceRef] = useState(draft?.sourceRef || '')
  const [error, setError] = useState(null)
  const [showHidden, setShowHidden] = useState(false)

  const load = useCallback(() => {
    getQuestions().then(setData).catch((e) => setError(e.message))
  }, [])
  useEffect(load, [load])

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const asked = await askQuestion({ text, answerable_by: answerable })
      setText(''); setAnswerable(''); setAsking(false)
      const fresh = await getQuestions()
      setData(fresh)
      // Selected on being asked. The researcher wrote it in order to inquire
      // into it; making them then pick it out of a list is a step that exists
      // only because the form and the list are different components.
      if (asked?.id) onSelect(asked.id)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="questions">
      <div className="questions-head">
        <h3>1. Choose or record a research question</h3>
        <button className="btn" type="button" onClick={() => setAsking(!asking)}>
          {asking ? 'Cancel' : 'Ask a question'}
        </button>
      </div>

      <div className="demo-examples">
        <p className="hint small">Choose an example, then edit and record it.</p>
        {DEMO_EXAMPLES.map((example) => <button type="button" className="btn" key={example.label}
          onClick={() => { setText(example.question); setAnswerable(example.criteria); setSourceRef(''); setAsking(true) }}>
          {example.label}
        </button>)}
      </div>

      {asking && (
        <form className="ask-form" onSubmit={submit}>
          {sourceRef && <p className="hint small">Starting source: <code>{sourceRef}</code></p>}
          <label>
            Research question
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} required />
          </label>
          <label>
            Research instructions
            <textarea
              value={answerable}
              onChange={(e) => setAnswerable(e.target.value)}
              rows={2}
              required
            />
          </label>
          <p className="hint small">
            Specify the approach, evidence to return and limits. These instructions are saved and sent to the agents.
        </p>
          <button className="btn accept" type="submit">Record question</button>
        </form>
      )}

      {error && <p className="error">{error}</p>}

      {data && data.count === 0 && !asking && (
        <p className="hint small">
          Record a question to begin, or choose Customize to enter agent tasks directly.
        </p>
      )}

      <details className="inquiry-details" open={selected ? true : undefined}>
      <summary>Saved questions{data ? ` (${data.count})` : ''}{selected ? ' · one selected' : ''}</summary>
      <p className="hint small">Select a question to investigate again.</p>
      <ul className="question-list">
        {data?.questions?.filter((q) => !hidden?.has(q.id)).map((q) => (
          <li
            key={q.id}
            className={`question pick${selected === q.id ? ' on' : ''}`}
            onClick={() => onSelect(selected === q.id ? null : q.id)}
          >
            <div className="question-row">
              <p className="question-text">{q.question}</p>
              {/* Hides the question and, in the Graph tab, whatever was only
                  there to support it (graph-model.js `hiddenIdsForQuestions`).
                  A view preference, not a graph write — nothing in the event
                  log changes, so this never conflicts with a run holding the
                  writer lock and needs no researcher permission. */}
              <button
                type="button" className="btn tiny"
                title="Hide from the Graph tab, along with anything only there for it — a display filter, not a graph edit"
                onClick={(e) => { e.stopPropagation(); onToggleHidden?.(q.id) }}
              >Hide</button>
            </div>
            <p className="question-answerable">
              <span>Research instructions</span> {q.answerable_by}
              </p>
            <p className="hint small">
              {q.addressed_by === 0
                ? 'No proposals yet.'
                : `${q.addressed_by} hypothes${q.addressed_by === 1 ? 'is' : 'es'} address this question.`}
            </p>
          </li>
        ))}
      </ul>

      </details>
      {!!hidden?.size && (
        <div className="questions-hidden">
          <button
            type="button" className="btn tiny"
            onClick={() => setShowHidden((v) => !v)}
          >
            {showHidden ? 'Hide' : 'Show'} hidden questions ({hidden.size})
          </button>
          {showHidden && (
            <ul className="question-list dim">
              {data?.questions?.filter((q) => hidden.has(q.id)).map((q) => (
                <li key={q.id} className="question">
                  <div className="question-row">
                    <p className="question-text">{q.question}</p>
                    <button
                      type="button" className="btn tiny"
                      onClick={() => onToggleHidden?.(q.id)}
                    >Unhide</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

// What auto mode will actually do, named before it is paid for.
//
// The roster comes from the server (`/api/run/config`), not from a guess made
// here: its shape depends on how many model *families* the pool has rather
// than how many models, and a panel that promised three agents and started two
// would be worse than one that promised nothing.
function AutoPlan({ config, question }) {
  const plan = config.plan || []
  const reviewing = plan.some((a) => a.role === 'reviewer')

  return (
    <div className="auto-plan">
      {!question && (
        <p className="hint small">
          Select a saved question or record a new one.
                    </p>
      )}

      <ul className="plan-list">
        {plan.map((a) => (
          <li key={a.agent_id} className={`plan-row r-${a.role}`}>
            <span className="plan-role">{a.role}</span>
            <span className="plan-method">{a.method_label}</span>
            <span className="plan-model">{a.model || config.model || 'server default'}</span>
          </li>
        ))}
      </ul>

      <p className="hint small">
        Each agent receives your question and research instructions.
      </p>
      {reviewing ? (
        <p className="hint small">
          The reviewer checks worker proposals after retrieval finishes.
        </p>
      ) : (
        <p className="warn small">
          No separate reviewer is configured. Claims remain proposed until reviewed.
        </p>
      )}
    </div>
  )
}

function blankAgent(i, role = 'worker') {
  return {
    key: `a${i}-${Math.random().toString(36).slice(2, 7)}`,
    agent_id: role === 'reviewer' ? `agent:ui-reviewer-${i + 1}` : `agent:ui-${i + 1}`,
    instructions: role === 'reviewer' ? REVIEWER_TASK : '',
    corpus_scope: '',
    method_label: '',
    model: '',
    role,
  }
}

function RunReport({ run, active }) {
  const s = run.spend
  const pct = s.budget_usd == null ? null : Math.min(100, (s.spent_usd / s.budget_usd) * 100)
  return (
    <div className={`run-report ${active ? 'active' : ''}`}>
      <div className="run-head">
        <span className={`badge run-${run.state}`}>{run.state}</span>
        <code>{run.id}</code>
        <span>{run.elapsed_s}s</span>
        <span>{run.agent_id}</span>
      </div>

      <div className="spend">
        {pct != null && <div className="spend-bar"><i style={{ width: `${pct}%` }} /></div>}
        <div className="spend-row">
          <span>
            <strong>${s.spent_usd.toFixed(5)}</strong> recorded cost
            {s.budget_usd != null && <> of ${s.budget_usd.toFixed(2)}</>}
          </span>
          <span>{s.calls} model call{s.calls === 1 ? '' : 's'}</span>
        </div>
        {s.unpriced_calls > 0 && (
          <p className="warn small">
            {s.unpriced_calls} call{s.unpriced_calls === 1 ? '' : 's'} reported no
            cost and {s.unpriced_calls === 1 ? 'was' : 'were'} charged at an
            estimate; the total includes those estimates.
          </p>
        )}
      </div>

      {run.stopped_early && <p className="warn small">{run.stopped_early}</p>}
      {run.error && <p className="error">{run.error}</p>}

      {(run.agents || []).map((a) => (
        <div className="agent-report" key={a.agent_id}>
          <h3>
            {a.agent_id}
            {a.model && <code className="agent-model">{a.model}</code>}
            {a.corpus_scope && <em> · {a.corpus_scope}</em>}
          </h3>
          {a.error && <p className="error">{a.error}</p>}
          {a.tool_calls.length === 0 && !a.error && (
            <p className="hint small">No tool calls yet.</p>
          )}
          <ul className="tool-calls">
            {a.tool_calls.map((c, i) => (
              <li key={i} className={c.is_error ? 'refused' : ''}>
                <div className="tc-head">
                  <code>{c.tool}</code>
                  <span className={`badge ${c.is_error ? 'tc-refused' : 'tc-ok'}`}>
                    {c.is_error ? 'refused' : 'ok'}
                  </span>
                </div>
                <p className="tc-result">{String(c.result)}</p>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {run.refusals.length > 0 && (
        <>
          <h3>Refusals this run ({run.refusals.length})</h3>
          <p className="hint small">
            Writes the graph declined. Not failures — the boundary holding.
                </p>
          <ul className="tool-calls">
            {run.refusals.map((r) => (
              <li key={r.seq} className="refused">
                <div className="tc-head">
                  <code>{r.rule}</code>
                  <span>{r.attempted}</span>
                </div>
                <p className="tc-result">{r.message}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
