import { Button } from './components/ui'
import { useTranslation } from 'react-i18next'
import { tr, explorationLabel } from './i18n'
export default function ExplorationDetail({ item, onClose }) {
  useTranslation()
  return <aside className="panel exploration-detail">
    <Button className="link" onClick={onClose}>{tr("Close")}</Button>
    <h2>{item.uid || tr("Worker exploration")}</h2>
    <p className="hint">{tr("Activity record · not evidence of a relationship")}</p>
    <p>{tr("Worker:")} {item.author}<br />{tr("Model:")} {item.model || tr("Not recorded")}</p>
    <p className="hint small">{tr("Run")} {item.runId}</p>
    {!item.actions.length && <p>{tr("Select a work to see what the worker did with it.")}</p>}
    <ol className="exploration-actions">{item.actions.map((a,i)=><li key={i}>
      <strong>{tr(a.kind)}</strong><p>{explorationLabel(a.purpose)}</p>
      {a.query && <p>{tr("Search:")} {a.query}</p>}
      {a.result && <p>{explorationLabel(a.result)}</p>}
      <p className="hint small">{tr("Why this input:")} {a.reason || tr("Reason not recorded.")}</p>
      <small>{tr("Action")} {a.step} · {a.tool}</small>
    </li>)}</ol>
  </aside>
}
