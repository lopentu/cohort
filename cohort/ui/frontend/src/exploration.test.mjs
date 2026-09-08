import test from 'node:test'
import assert from 'node:assert/strict'
import { explorationFor } from './exploration.js'
const run = {id:'r',question_id:'q',agents:[{agent_id:'worker',role:'worker',model:'test/model',tool_calls:[
  {tool:'semantic_neighbors',args:{uid:'A'},result:{nearest_unit_tally:[['B',3],['C',1]]}},
  {tool:'align_passages',args:{uid_a:'A',uid_b:'B'},result:{longest_shared_run:12}},
  {tool:'align_passages',args:{uid_a:'A',uid_b:'D'},is_error:true,result:'failed'},
]}]}
test('exploration distinguishes returned candidates, completed comparisons and failed attempts',()=>{
 const {nodes,edges}=explorationFor({history:[run],current:run},new Set(['q']))
 assert.equal(nodes.length,5)
 assert.equal(nodes.find(n=>n.uid==='C').actions[0].kind,'Candidate returned')
 assert.equal(nodes.find(n=>n.uid==='B').actions.length,2)
 assert.equal(nodes.find(n=>n.uid==='D').actions[0].kind,'Comparison failed')
 assert.ok(edges.every(e=>e.exploration))
 assert.equal(nodes.filter(n=>n.runId==='r'&&!n.uid).length,1)
})
test('hidden questions and unavailable histories do not acquire invented activity',()=>{
 assert.equal(explorationFor({history:[run]},new Set(['other'])).nodes.length,0)
 assert.equal(explorationFor({recorded:[{run_id:'old',question_id:'q',agents:[]}]},new Set(['q'])).nodes.length,0)
})

test('saved action reasons survive restarting the server',()=>{
 const saved = {...run,run_id:run.id}
 saved.agents[0].tool_calls[0].reason='Find similar passages beyond this work.'
 const overlay=explorationFor({recorded:[saved]},new Set(['q']))
 assert.equal(overlay.nodes.find(n=>n.uid==='C').actions[0].reason,'Find similar passages beyond this work.')
})
