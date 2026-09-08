// An activity overlay, never graph evidence. Only recorded tool results supply
// candidates; a model's proposal text is not a record of what it searched.
export function explorationFor(payload, visibleQuestions) {
  const nodes = [], edges = []
  const runs = new Map((payload?.history || []).map(r => [r.id, r]))
  if (payload?.current) runs.set(payload.current.id, payload.current)
  for (const run of runs.values()) {
    if (!visibleQuestions.has(run.question_id)) continue
    for (const agent of run.agents || []) {
      if (agent.role !== 'worker') continue
      const root = `exploration:${run.id}:${agent.agent_id}`
      const units = new Map()
      const add = (uid, action) => {
        if (!uid) return
        if (!units.has(uid)) units.set(uid, {id:`${root}:${uid}`,uid,label:uid,actions:[],runId:run.id,author:agent.agent_id,model:agent.model,exploration:true})
        units.get(uid).actions.push(action)
      }
      for (const [i, call] of (agent.tool_calls || []).entries()) {
        const a = call.args || {}, r = call.result || {}
        const base = {step:i+1,tool:call.tool,reason:call.reason || null}
        if (call.tool === 'semantic_neighbors') {
          add(a.uid, {...base,kind:call.is_error?'Search failed':'Similarity search',purpose:'Find passages with similar content.'})
          if (!call.is_error) {
            const candidates = new Set((r.nearest_unit_tally || []).map(([uid])=>uid))
            for (const window of r.shown || []) for (const n of window.neighbors || []) candidates.add(n.uid)
            for (const uid of candidates) add(uid,{...base,kind:'Candidate returned',purpose:`Returned by the similarity search for ${a.uid}; not necessarily inspected.`})
          }
        } else if (call.tool === 'align_passages') {
          for (const uid of new Set([a.uid_a,a.uid_b])) add(uid,{...base,kind:call.is_error?'Comparison failed':'Wording compared',purpose:`Compare shared wording in ${a.uid_a} and ${a.uid_b}.`,result:!call.is_error && Number.isFinite(r.longest_shared_run)?`Longest returned match: ${r.longest_shared_run} characters (minimum ${a.min_run ?? 12}).`:null})
        } else if (call.tool === 'attribution_evidence') {
          add(a.uid,{...base,kind:call.is_error?'Calculation failed':'Vocabulary compared',purpose:`Compare vocabulary profiles${a.withhold?.length?`; exclude ${a.withhold.join(', ')}`:''}.`})
        } else if (call.tool === 'find_attestations' && !call.is_error) {
          for (const id of r.witnesses || []) add(id.replace(/^witness:/,''),{...base,kind:'Citation recorded',purpose:'Attach a matching passage to a proposal.',query:a.query})
        }
      }
      if (!units.size) continue
      nodes.push({id:root,label:'Worker exploration',runId:run.id,author:agent.agent_id,model:agent.model,actions:[],exploration:true},...units.values())
      edges.push({id:`${root}:question`,from:run.question_id,to:root,exploration:true})
      for (const unit of units.values()) edges.push({id:`${unit.id}:activity`,from:root,to:unit.id,exploration:true})
    }
  }
  return {nodes,edges}
}
