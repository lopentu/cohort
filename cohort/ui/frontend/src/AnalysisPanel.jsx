import ActionList from './ActionList'
import { analysisContext, analysisThreads, makeAnalysisInstructions } from './analysis-conversation'
import AnalysisMarkdown from './AnalysisMarkdown'
import { useEffect, useRef, useState } from 'react'
import { getRunConfig, getRuns, startRun, stopRun } from './api'

export default function AnalysisPanel({ view, scope }) {
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
      const r=await startRun({agents:[{agent_id:`agent:analysis-${crypto.randomUUID()}`,role:'analyst',model:model.trim(),instructions,method_label:`${followup?context.view:view} analysis`,corpus_scope:'Original view and related local corpus material'}],question_id:(followup?run.question_id:scope.question_id) || null})
      setRunId(r.id)
      if(followup)setMessage('')
      setRuns(previous=>({...previous,current:r}))
    }catch(e){setError(e.message)}finally{setPending(false)}
  }
  if (!config?.analysis_enabled) return null
  return <div className="analysis-control">
    {['graph','evidence'].includes(view) && <button ref={trigger} className="btn tiny" onClick={()=>setOpen(v=>!v)} aria-expanded={open} aria-controls="ai-analysis-panel">Analyze this view</button>}
    {open && <section id="ai-analysis-panel" className="analysis-panel" aria-label="AI analysis">
      <div className="tc-head analysis-header"><h3>AI analysis</h3><button ref={closeButton} className="link" onClick={close}>Close</button></div>
      <div className="analysis-body">
      <p className="hint small">Ask about this view or investigate further. Graph records stay unchanged.</p>
      <div className="analysis-inputs">
        <label>Model<input className="corpus-input" value={model} onChange={e=>setModel(e.target.value)} /></label>
        <button className="btn" disabled={pending || active || otherActive || !config.model_configured || !config.corpus_available || !scope || !model.trim() || !['graph','evidence'].includes(view)} onClick={()=>start(false)}>{pending?'Starting…':run?'New analysis':'Start analysis'}</button>
        {active && <button className="btn tiny" onClick={()=>stopRun().catch(e=>setError(e.message))}>Stop analysis</button>}
      </div>
      {otherActive && <p className="hint small">Another run is active. Wait for it to finish.</p>}
      {available.size>0 && <label>Saved analyses<select value={runId || ''} onChange={e=>setRunId(e.target.value || null)}>
        <option value="">Choose an analysis</option>
        {threads.map(r=><option key={r.id} value={r.id}>{r.agents.find(a=>a.role==='analyst')?.method_label || 'Analysis'} · {r.id}</option>)}
      </select></label>}
      {error && <p className="error">{error}</p>}
      {run && <>
        <p className="hint small">{run.state || 'Open'} · {run.agents.find(a=>a.role==='analyst')?.model} · Original view: {context.view}.</p>
        {run.stopped_early && <p className="warn">{run.stopped_early}</p>}
        {run.error && <p className="error">{run.error}</p>}
        {context.messages.map((m,i)=><div className={`analysis-message ${m.role}`} key={i}>
          <h4>{m.role==='user'?'You':`AI · ${m.model || 'Model not recorded'}`}</h4>
          <AnalysisMarkdown>{m.content}</AnalysisMarkdown>
          {m.actions?.length>0 && <AnalysisActions calls={m.actions} />}
        </div>)}
        <div className="analysis-message user"><h4>You</h4><p>{context.request}</p></div>
        {run.agents.filter(a=>a.role==='analyst').map(a=><div className="analysis-message assistant" key={a.agent_id}>
          <h4>AI · {a.model}</h4>
          {a.error && <p className="error">{a.error}</p>}
          {a.analysis ? <AnalysisMarkdown>{a.analysis}</AnalysisMarkdown> : <p className="hint">{active?'Investigating…':'No final explanation was recorded. Inspect the actions below.'}</p>}
          <AnalysisActions key={`${run.id}:${a.agent_id}`} calls={a.tool_calls || []} active={active} />
        </div>)}
        <p className="hint small">AI interpretation, not a verification or researcher acceptance.</p>
      </>}
      </div>
      {run && <form className="analysis-composer" onSubmit={e=>{e.preventDefault();start(true)}}>
        <label htmlFor="analysis-followup">Follow-up question</label>
        <textarea id="analysis-followup" value={message} onChange={e=>setMessage(e.target.value)} rows={2} placeholder="Ask about the answer or request another check…" />
        <button className="btn" type="submit" disabled={pending || active || otherActive || !message.trim() || !model.trim() || !config.model_configured || !config.corpus_available}>Send</button>
      </form>}
    </section>}
  </div>
}

function AnalysisActions({ calls, active = false }) {
  return <details className="analysis-actions"><summary>Actions and reasons ({calls.length})</summary>
    <ActionList calls={calls} active={active} label="Analysis actions" />
  </details>
}
