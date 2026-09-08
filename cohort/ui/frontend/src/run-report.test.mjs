import test from 'node:test'
import assert from 'node:assert/strict'
import { inquiryReports } from './run-report.js'
test('completed reports remain available from durable history after restart',()=>{
 const r={run_id:'saved',started_at:'2026-09-08T01:00:00Z',finished_at:'2026-09-08T01:00:12Z',agents:[{agent_id:'worker',role:'worker',tool_calls:[{reason:'Check wording'}]}],state:'finished',spent_usd:0.1,calls:2,refusals:0}
 const [shown]=inquiryReports({current:null,history:[],recorded:[r]})
 assert.equal(shown.id,'saved');assert.equal(shown.agents[0].tool_calls[0].reason,'Check wording');assert.equal(shown.elapsed_s,12)
 const live={...shown,archived:false}
 assert.equal(inquiryReports({history:[live],recorded:[r]})[0].archived,false)
})
