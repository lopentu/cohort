// The refused writes.
//
// This is an output surface, not a log viewer. docs/design.md §15 claims the
// system's "refusals are part of its scholarly output", and §5 principle 4
// makes the write boundary the thing that produces them — so a refusal shown
// here is the system declining to record something, with the name of the
// commitment that made it decline. That is the most distinctive thing COHORT
// does, and until this panel existed it was visible only in terminal output.
//
// Presented most-recent-first, because the useful question is almost always
// "what did the run I just watched refuse to do?".

// What each category asks the reader to go and look at. Mirrors
// `RefusalCategory` in cohort/errors.py, which is where the taxonomy is
// decided; this is only how it reads on screen.
const CATEGORY_NOTE = {
  evidence: 'the corpus did not support it',
  standing: "who was writing, or the node's state, forbade it",
  expression: 'the writer could not say what it meant',
  operational: "the system's own preconditions",
  unclassified: "a rule this version's taxonomy does not know",
}

const RULE_NOTE = {
  UnattestableClaim: 'The claim needs an attested supporting passage.',
  UnattestableConjecture: 'The conjecture needs a test query.',
  PersistentRejection: 'A rejected node cannot be re-proposed. Reopening is a researcher action.',
  NotResearcher: 'Only the researcher may accept, reject or reopen.',
  MissingRejectionReason: 'Rejection requires a stated reason.',
  RungSkipped: 'The required prior status has not been reached.',
  NodeNotFound: 'The referenced record does not exist.',
  EdgeDomainViolation: 'That edge type is not valid between those two node types.',
  EdgeEndpointMissing: 'An edge pointed at a node that does not exist.',
  EdgeSelfLoop: 'A node cannot be linked to itself.',
  SingleWriterViolation: 'Another process held the write lock.',
  PassageNotLocated: 'The passage needs a source-text link.',
}

export default function RefusalsPanel({ refusals, closing }) {
  // `closing` is set while the panel is on its way out (see motion.js): the
  // pill that opens it is a toggle, and a toggled surface that vanishes on a
  // frame reads as a glitch rather than a dismissal.
  const cls = `refusals ${closing ? 'closing' : ''}`

  if (!refusals?.available) {
    return (
      <section className={cls}>
        <h2>Refused writes</h2>
        <p className="hint">
          Event log unavailable. Refusal history cannot be loaded.
        </p>
      </section>
    )
  }

  const rows = [...refusals.refusals].reverse()
  // From the census, not from `rows`: the list is a truncated tail, and a
  // tally computed over it would quietly understate every rule once a log
  // grows past the limit.
  const census = refusals.census
  const byRule = census?.by_rule ?? {}
  const streaks = census?.streaks ?? []

  return (
    <section className={cls}>
      <h2>
        Refused writes <span className="refusal-total">{refusals.total}</span>
      </h2>
      <p className="hint">
        Blocked changes and the rules they violated.
      </p>

      {rows.length === 0 ? (
        <p className="hint">
          No refused writes recorded.
        </p>
      ) : (
        <>
          {census && (
            <ul className="refusal-cats">
              {Object.entries(census.by_category)
                .filter(([, n]) => n > 0)
                .map(([name, n]) => (
                  <li key={name} className={`refusal-cat cat-${name}`}>
                    <span className="cat-n">{n}</span>
                    <span className="cat-name">{name}</span>
                    <span className="cat-note">{CATEGORY_NOTE[name]}</span>
                  </li>
                ))}
            </ul>
          )}

          <div className="rule-tally">
            {Object.entries(byRule).map(([rule, n]) => (
              <span className="rule-chip" key={rule}>
                {rule} <strong>{n}</strong>
              </span>
            ))}
          </div>

          {streaks.length > 0 && (
            <div className="streaks">
              <h3>
                {streaks.length} streak{streaks.length > 1 ? 's' : ''}
                <span className="streak-share">
                  {census.streaked_count} of {census.total} refusals
                </span>
              </h3>
              <p className="hint small">
                Consecutive refusals for the same agent and rule. Inspect the attempts to identify a recurring problem.
              </p>
              <ul className="streak-list">
                {streaks.map((s) => (
                  <li key={`${s.authored_by}-${s.first_seq}`} className="streak-item">
                    <div className="streak-head">
                      <span className="streak-count">{s.count}&times;</span>
                      <span className="refusal-rule">{s.rule}</span>
                      <span className={`cat-tag cat-${s.category}`}>{s.category}</span>
                      <span className="refusal-author">{s.authored_by}</span>
                      <code className="refusal-attempted">{s.attempted.join(', ')}</code>
                    </div>
                    {s.node_ids.length > 0 && (
                      <p className="streak-ids">
                        tried {s.node_ids.length} id
                        {s.node_ids.length > 1 ? 's' : ''}:{' '}
                        {s.node_ids.slice(0, 3).map((id) => (
                          <code key={id}>{id}</code>
                        ))}
                        {s.node_ids.length > 3 && ` +${s.node_ids.length - 3} more`}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {refusals.truncated && (
            <p className="hint small">
              Showing the most recent {rows.length} of {refusals.total}.
            </p>
          )}

          <ul className="refusal-list">
            {rows.map((r) => (
              <li key={r.seq} className="refusal-item">
                <div className="refusal-head">
                  <span className="refusal-rule">{r.rule}</span>
                  <code className="refusal-attempted">{r.attempted}</code>
                  <span className="refusal-author">{r.authored_by}</span>
                  <time>{r.at}</time>
                </div>
                <p className="refusal-message">{r.message}</p>
                {RULE_NOTE[r.rule] && (
                  <p className="refusal-note">{RULE_NOTE[r.rule]}</p>
                )}
                <div className="refusal-meta">
                  {r.node_id && <code>{r.node_id}</code>}
                  {r.model_call_id !== null && r.model_call_id !== undefined && (
                    <span className="chip">model call #{r.model_call_id}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
