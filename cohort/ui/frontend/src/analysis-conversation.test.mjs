import test from 'node:test'
import assert from 'node:assert/strict'
import { analysisContext, analysisMessages, analysisThreads, makeAnalysisInstructions } from './analysis-conversation.js'

const scope={view:'evidence',uid:'T0603',features:'radich',withhold:[]}
function run(id,instructions,analysis='First answer') {
 return {id,question_id:null,agents:[{role:'analyst',model:'test/model',instructions,analysis,tool_calls:[{tool:'attribution_evidence',args:{uid:'T0603'},reason:'Check scores'}]}]}
}
test('follow-up retains the original view and full exchange after reload',()=>{
 const first=run('first',makeAnalysisInstructions({scope,view:'evidence',conversationId:'thread'}))
 const instructions=makeAnalysisInstructions({run:first,message:'Why that group?',scope:{uid:'T0453'},view:'graph'})
 const second=run('second',instructions,'Second answer')
 const saved=JSON.parse(JSON.stringify(second))
 const context=analysisContext(saved)
 assert.equal(context.conversation_id,'thread')
 assert.deepEqual(context.scope,scope)
 assert.equal(context.view,'evidence')
 assert.equal(context.request,'Why that group?')
 assert.deepEqual(analysisMessages(saved).map(m=>m.content),['Explain this view.','First answer','Why that group?','Second answer'])
 assert.equal(analysisMessages(saved)[1].actions[0].reason,'Check scores')
})
test('older saved analyses can be continued using their recorded instructions',()=>{
 const first=run('old','Explain and investigate this view.\n'+JSON.stringify(scope))
 const next=run('new',makeAnalysisInstructions({run:first,message:'Check the commentary.'}))
 assert.deepEqual(analysisContext(next).scope,scope)
 assert.equal(analysisContext(next).conversation_id,'old')
 assert.equal(analysisMessages(next)[1].content,'First answer')
})
test('saved selector groups messages into conversations',()=>{
 const a=run('a',makeAnalysisInstructions({scope,view:'evidence',conversationId:'one'}))
 const b=run('b',makeAnalysisInstructions({run:a,message:'Explain further'}))
 const c=run('c',makeAnalysisInstructions({scope,view:'evidence',conversationId:'two'}))
 assert.deepEqual(analysisThreads([a,c,b]).map(r=>r.id).sort(),['b','c'])
})
test('a failed answer is not invented in the conversation',()=>{
 const a=run('a',makeAnalysisInstructions({scope,view:'evidence',conversationId:'one'}),'')
 assert.equal(analysisMessages(a).length,1)
})
