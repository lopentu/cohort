export function inquiryReports(payload) {
  const reports = new Map((payload?.recorded || []).map(r => [r.run_id,{
    ...r,id:r.run_id,agent_id:r.agents.map(a=>a.agent_id).join(', '),
    agents:r.agents.map(a=>({...a,tool_calls:a.tool_calls || []})),
    spend:{budget_usd:r.budget_usd,spent_usd:r.spent_usd,calls:r.calls || 0},
    elapsed_s:r.finished_at ? Math.max(0,Math.round((Date.parse(r.finished_at)-Date.parse(r.started_at))/1000)) : '—',
    refusal_total:r.refusals,refusals:[],archived:true,
  }]))
  for(const r of payload?.history || []) reports.set(r.id,r)
  if(payload?.current) reports.set(payload.current.id,payload.current)
  return [...reports.values()].filter(r=>!r.agents.every(a=>a.role==='analyst'))
    .sort((a,b)=>(typeof b.started_at==='number'?b.started_at*1000:Date.parse(b.started_at))-(typeof a.started_at==='number'?a.started_at*1000:Date.parse(a.started_at)))
}
