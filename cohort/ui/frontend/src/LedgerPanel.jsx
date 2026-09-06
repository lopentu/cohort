import { useEffect, useState } from 'react'
import { getLedger } from './api'

// Every candidate discriminator and what became of it.
//
// The discarded rows are the reason this exists. In ordinary stylometry the
// features that did not work are invisible — tried, disappointing, never
// written down — so a reader cannot tell a discovery from a fishing
// expedition, and neither can the author. Here they stay on the page, and the
// first number shown is how many were *tried*, not how many survived.
//
// Deliberately unsortable and unscored. `usable` means "survived one negative
// control", which is a fact about a test that was run, not a measure of how
// good a feature is; offering a sort would invent a ranking the data cannot
// support.
const FATE_ORDER = ['usable', 'untested', 'discarded']

export default function LedgerPanel({ onSelect }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getLedger().then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <section className="ledger"><p className="error">{error}</p></section>
  if (!data) return <section className="ledger"><p className="hint">Loading…</p></section>

  if (!data.tried) {
    return (
      <section className="ledger">
        <h2>Feature ledger</h2>
        <p className="hint">{data.reading}</p>
      </section>
    )
  }

  const groups = FATE_ORDER
    .map((fate) => [fate, data.features.filter((f) => f.fate === fate)])
    .filter(([, rows]) => rows.length)

  return (
    <section className="ledger">
      <h2>Feature ledger</h2>

      {/* The ratio leads, because it is the finding. Three survivors out of
          four is a different claim from three out of ninety, and a panel that
          showed only the survivors would make the second read like the first. */}
      <div className="ledger-ratio">
        <div className="ratio-figure">
          <strong>{data.by_fate.usable}</strong>
          <span>of {data.tried}</span>
        </div>
        <p>{data.reading}</p>
      </div>

      {groups.map(([fate, rows]) => (
        <div className={`ledger-group f-${fate}`} key={fate}>
          <h3>
            {fate === 'usable' ? 'Survived the control' : null}
            {fate === 'discarded' ? 'Discarded' : null}
            {fate === 'untested' ? 'Registered, not yet tested' : null}
            <span className="ledger-n">{rows.length}</span>
          </h3>
          <p className="hint small">{rows[0].licenses}</p>

          <div className="ledger-rows">
            {rows.map((row) => (
              <Feature key={row.conjecture_id} row={row} onSelect={onSelect} />
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}

function Feature({ row, onSelect }) {
  const [open, setOpen] = useState(false)
  const p = row.prediction
  const groups = row.control?.groups || []

  return (
    <div className={`ledger-row f-${row.fate}`}>
      <button className="ledger-head" onClick={() => setOpen(!open)}>
        <span className="ledger-feature">{row.feature}</span>
        <span className="ledger-pred">
          ≥{pct(p.min_benchmark_share)} {p.benchmark_label} · ≤{pct(p.max_control_share)} {p.control_label}
        </span>
        <span className="ledger-observed">
          {groups.length
            ? groups.map((g) => (
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
            : <span className="hint small">not run</span>}
        </span>
      </button>

      {open && (
        <div className="ledger-detail">
          {row.control ? (
            <>
              <p className="v-detail"><strong>Outcome:</strong> {row.control.detail}</p>
              {row.control.limitations && (
                <p className="v-limits"><strong>Does not establish:</strong> {row.control.limitations}</p>
              )}
            </>
          ) : (
            <p className="hint small">
              Registered with a prediction, but its control has not been run — so it
              may not be applied to a disputed work.
            </p>
          )}
          <button className="btn tiny" onClick={() => onSelect?.(row.conjecture_id)}>
            open the conjecture
          </button>
        </div>
      )}
    </div>
  )
}

//: shares are fractions of *works*, shown as percentages because a threshold
//: reads better that way; the underlying unit is stated in the row.
function pct(x) {
  return `${Math.round(x * 100)}%`
}
