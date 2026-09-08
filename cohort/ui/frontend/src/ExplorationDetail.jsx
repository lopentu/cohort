export default function ExplorationDetail({ item, onClose }) {
  return <aside className="panel exploration-detail">
    <button className="link" onClick={onClose}>Close</button>
    <h2>{item.uid || 'Worker exploration'}</h2>
    <p className="hint">Activity record · not evidence of a relationship</p>
    <p>Worker: {item.author}<br />Model: {item.model || 'Not recorded'}</p>
    <p className="hint small">Run {item.runId}</p>
    {!item.actions.length && <p>Select a work to see what the worker did with it.</p>}
    <ol className="exploration-actions">{item.actions.map((a,i)=><li key={i}>
      <strong>{a.kind}</strong><p>{a.purpose}</p>
      {a.query && <p>Search: {a.query}</p>}
      {a.result && <p>{a.result}</p>}
      <p className="hint small">Why this input: {a.reason || 'Reason not recorded.'}</p>
      <small>Action {a.step} · {a.tool}</small>
    </li>)}</ol>
  </aside>
}
