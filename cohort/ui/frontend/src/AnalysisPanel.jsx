import { Button } from './components/ui'
import { useTranslation } from 'react-i18next'
import { tr } from './i18n'
import ActionList from './ActionList'
import { analysisContext, analysisThreads, makeAnalysisInstructions, analysisRunRequest } from './analysis-conversation'
import AnalysisMarkdown from './AnalysisMarkdown'
import { useEffect, useRef, useState } from 'react'
import { getRunConfig, getRuns, startRun, stopRun } from './api'

export default function AnalysisPanel({ view, scope }) {
  useTranslation()
  const trigger = useRef(null)
  const closeButton = useRef(null)
  const close = () => { setOpen(false); trigger.current?.focus() }
  const [config,setConfig] = useState(null)
  const [open,setOpen] = useState(false)
  const [model,setModel] = useState('google/gemini-3.8-flash')
  const [runs,setRuns] = useState(null)
  const [runId,setRunId] = useState(null)
  const [pending,setPending] = useState(false)
  const [error,setError] = useState(null)
  const [message,setMessage] = useState('')
  useEffect(()=>{setOpen(false)},[view])
  useEffect(()=>{getRunConfig().then(setConfig).catch(()=>setConfig(null))},[])
  useEffect(()=>{
    if (!open && !runId) return
    let live=true
    const load=()=>getRuns().then(r=>{if(live)setRuns(r)}).catch(e=>{if(live)setError(e.message)})
    load();const timer=setInterval(load,2000)
    return()=>{live=false;clearInterval(timer)}
  },[open,runId])
  useEffect(()=>{
    if (!open) return
    closeButton.current?.focus()
    const escape = e => { if(e.key==='Escape') { setOpen(false); trigger.current?.focus() } }
    document.addEventListener('keydown',escape)
    return()=>document.removeEventListener('keydown',escape)
  },[open])
  const available = new Map((runs?.recorded || []).filter(r=>r.agents.some(a=>a.role==='analyst')).map(r=>[r.run_id,{...r,id:r.run_id}]))
  for(const r of runs?.history || []) if(r.agents.some(a=>a.role==='analyst')) available.set(r.id,r)
  if(runs?.current?.agents.some(a=>a.role==='analyst')) available.set(runs.current.id,runs.current)
  const run=available.get(runId)
  const context=run ? analysisContext(run) : null
  const threads=analysisThreads([...available.values()])
  const active=!!run && ['starting','running'].includes(run.state)
  const otherActive=runs?.current && runs.current.id!==runId && ['starting','running'].includes(runs.current.state)
  const start=async(followup=false)=>{
    setError(null);setPending(true)
    try{
      const instructions=makeAnalysisInstructions({scope,view,conversationId:crypto.randomUUID(),run:followup?run:null,message:followup?message:null})
      const r=await startRun(analysisRunRequest({agents:[{agent_id:`agent:analysis-${crypto.randomUUID()}`,role:'analyst',model:model.trim(),instructions,method_label:`${followup?context.view:view} analysis`,corpus_scope:'Original view and related local corpus material'}],question_id:(followup?run.question_id:scope.question_id) || null},config))
      setRunId(r.id)
      if(followup)setMessage('')
      setRuns(previous=>({...previous,current:r}))
    }catch(e){setError(e.message)}finally{setPending(false)}
  }
  if (!config?.analysis_enabled) return null
  return <div className="analysis-control">
    {['graph','evidence'].includes(view) && <Button ref={trigger} className="btn tiny" onClick={()=>setOpen(v=>!v)} aria-expanded={open} aria-controls="ai-analysis-panel">{tr("Analyze this view")}</Button>}
    {open && <section id="ai-analysis-panel" className="analysis-panel" aria-label={tr("AI analysis")}>
      <div className="tc-head analysis-header"><h3>{tr("AI analysis")}</h3><Button ref={closeButton} className="link" onClick={close}>{tr("Close")}</Button></div>
      <div className="analysis-body">
      <p className="hint small">{tr("Ask about this view or investigate further. Graph records stay unchanged.")}</p>
      <div className="analysis-inputs">
        <label>{tr("Model")}<input className="corpus-input" value={model} onChange={e=>setModel(e.target.value)} /></label>
        <Button className="btn" disabled={pending || active || otherActive || !config.model_configured || !config.corpus_available || !scope || !model.trim() || !['graph','evidence'].includes(view)} onClick={()=>start(false)}>{pending?tr("Starting…"):run?tr("New analysis"):tr("Start analysis")}</Button>
        {active && <Button className="btn tiny" onClick={()=>stopRun().catch(e=>setError(e.message))}>{tr("Stop analysis")}</Button>}
      </div>
      {otherActive && <p className="hint small">{tr("Another run is active. Wait for it to finish.")}</p>}
      {available.size>0 && <label>{tr("Saved analyses")}<select value={runId || ''} onChange={e=>setRunId(e.target.value || null)}>
        <option value="">{tr("Choose an analysis")}</option>
        {threads.map(r=><option key={r.id} value={r.id}>{r.agents.find(a=>a.role==='analyst')?.method_label || tr("Analysis")} · {r.id}</option>)}
      </select></label>}
      {error && <p className="error">{error}</p>}
      {run && <>
        <p className="hint small">{tr(run.state || "Open")} · {run.agents.find(a=>a.role==='analyst')?.model} {tr("· Original view:")} {tr(({ graph: "Graph", evidence: "Vocabulary comparison", corpus: "Corpus", findings: "Findings", run: "Inquiry" })[context.view] || context.view)}.</p>
        {run.stopped_early && <p className="warn">{run.stopped_early}</p>}
        {run.error && <p className="error">{run.error}</p>}
        {context.messages.map((m,i)=><div className={`analysis-message ${m.role}`} key={i}>
          <h4>{m.role==='user'?tr("You"):`AI · ${m.model || tr("Model not recorded")}`}</h4>
          <AnalysisMarkdown>{m.content}</AnalysisMarkdown>
          {m.actions?.length>0 && <AnalysisActions calls={m.actions} />}
        </div>)}
        <div className="analysis-message user"><h4>{tr("You")}</h4><p>{context.request}</p></div>
        {run.agents.filter(a=>a.role==='analyst').map(a=><div className="analysis-message assistant" key={a.agent_id}>
          <h4>{tr("AI ·")} {a.model}</h4>
          {a.error && <p className="error">{a.error}</p>}
          {a.analysis ? <AnalysisMarkdown>{a.analysis}</AnalysisMarkdown> : <p className="hint">{active?tr("Investigating…"):tr("No final explanation was recorded. Inspect the actions below.")}</p>}
          <AnalysisActions key={`${run.id}:${a.agent_id}`} calls={a.tool_calls || []} active={active} />
        </div>)}
        <p className="hint small">{tr("AI interpretation, not a verification or researcher acceptance.")}</p>
      </>}
      </div>
      {run && <form className="analysis-composer" onSubmit={e=>{e.preventDefault();start(true)}}>
        <label htmlFor="analysis-followup">{tr("Follow-up question")}</label>
        <textarea id="analysis-followup" value={message} onChange={e=>setMessage(e.target.value)} rows={2} placeholder={tr("Ask about the answer or request another check…")} />
        <Button className="btn" type="submit" disabled={pending || active || otherActive || !message.trim() || !model.trim() || !config.model_configured || !config.corpus_available}>{tr("Send")}</Button>
      </form>}
    </section>}
  </div>
}

function AnalysisActions({ calls, active = false }) {
  useTranslation()
  return <details className="analysis-actions"><summary>{tr("Actions and reasons (")}{calls.length})</summary>
    <ActionList calls={calls} active={active} label="Analysis actions" />
  </details>
}
