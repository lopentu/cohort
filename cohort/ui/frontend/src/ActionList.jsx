import { useEffect, useRef } from 'react'

// Stable row keys preserve an open action during polling. A growing log must
// not move someone reading an earlier action or its expanded result.
export default function ActionList({ calls = [], active = false, label = 'Agent actions' }) {
  const viewport = useRef(null)
  const following = useRef(true)
  useEffect(() => {
    const el = viewport.current
    if (active && el && following.current && !el.querySelector('.action-row[open]')) {
      el.scrollTo({ top: el.scrollHeight, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
    }
  }, [calls.length, active])
  if (!calls.length) return null
  return <div className={`action-list ${active ? 'is-live' : ''}`}>
    <div className="action-list-heading">Actions <span>{calls.length}</span></div>
    <div ref={viewport} className="action-viewport" role="region" aria-label={label} tabIndex={0}
      onScroll={e => { const el = e.currentTarget; following.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32 }}>
      <ol className="action-rows">
        {calls.map((c, i) => {
          const state = c.pending ? (active ? 'Running' : 'Unrecorded') : c.is_error ? 'Failed' : 'Done'
          return <li key={i}>
            <details className={`action-row ${c.pending ? 'is-pending' : c.is_error ? 'is-error' : ''}`}>
              <summary>
                <span className="action-number">{i + 1}</span>
                <code className="action-tool">{c.tool}</code>
                <span className="action-reason">{c.reason || 'Reason not recorded'}</span>
                <span className="action-state">{state}</span>
              </summary>
              <div className="action-detail">
                <code>{c.tool}</code>
                {c.agent_id && <small> · {c.agent_id}</small>}
                <p>{c.reason || 'Reason not recorded.'}</p>
                {c.pending && !active && <p className="hint small">The outcome was not recorded.</p>}
                <details><summary>Inputs and result</summary><pre>{JSON.stringify({ inputs: c.args, result: c.result }, null, 2)}</pre></details>
              </div>
            </details>
          </li>
        })}
      </ol>
    </div>
  </div>
}
