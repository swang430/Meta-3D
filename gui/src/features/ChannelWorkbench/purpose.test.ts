import test from 'node:test'
import assert from 'node:assert/strict'
import { purposeParameters, readPurpose, frameRange } from './purpose.ts'
const defaults={selection_start:0,selection_end:25,holdout_start:26,holdout_end:37,tap_budget_max:31,matrix_nmse_p95_max:1,phase_error_p95_max_deg:60,objective:'phase',mode:'conducted',manual_candidate:''}
test('冻结连续相邻非重叠区间与有限约束，拒绝非法手选',()=>{
 assert.deepEqual(purposeParameters(defaults),defaults)
 for(const change of [{holdout_start:25},{holdout_start:27},{selection_start:-1},{holdout_end:NaN},{tap_budget_max:32},{phase_error_p95_max_deg:181},{matrix_nmse_p95_max:-1},{manual_candidate:'best'}]) assert.throws(()=>purposeParameters({...defaults,...change}))
})
test('拒绝正式通过、自动采纳以及无达标却返回留出推荐',()=>{
 const raw={schema:'mpdb-purpose/1',status:'no_candidate_meets_constraints',formal_verdict:null,hardware_verified:false,alignment_status:'unverified',simulated:false,source_frame_count:38,common_frame_ids:Array.from({length:38},(_,i)=>i),frame_ids:[0,37],evaluation:{schema:'candidate-evaluation/1',status:'no_candidate_meets_constraints',selected_candidate:null,holdout:null,manual_candidate:null,manual_holdout:null,formal_verdict:null,alignment_status:'unverified',automatic_adoption:false,ota_status:'not_evaluated',selection:Object.fromEntries(['independent-24','independent-26','independent-31','shared-24','shared-26','shared-31'].map(c=>[c,{}])),candidate_parameters:Object.fromEntries(['independent-24','independent-26','independent-31','shared-24','shared-26','shared-31'].map(c=>[c,{}])),plan:{},provenance:{},plan_fingerprint:'a'.repeat(64),selection_fingerprint:'b'.repeat(64),selection_input_fingerprint:'c'.repeat(64)},download_url:'/api/v1/channel-assets/mpdb-projects/purpose-evaluations/123/report.zip',points_url:'/api/v1/channel-assets/mpdb-projects/purpose-evaluations/123/points.csv'}
 assert.equal(readPurpose(raw).evaluation.selected_candidate,null)
 for(const change of [{formal_verdict:'pass'},{hardware_verified:true},{evaluation:{...raw.evaluation,automatic_adoption:true}},{evaluation:{...raw.evaluation,holdout:{}}},{points_url:'https://evil.example/points.csv'}]) assert.throws(()=>readPurpose({...raw,...change}))
})

test('可选 ASC 冻结共同范围并允许第七个人工候选',()=>{
 assert.equal(purposeParameters({...defaults,holdout_end:36,manual_candidate:'existing-asc'},true).manual_candidate,'existing-asc')
 assert.throws(()=>purposeParameters({...defaults,holdout_end:36,manual_candidate:'existing-asc'}))
 assert.throws(()=>purposeParameters(defaults,true))
})
test('真实报告严格校验六或七候选及共同帧',async()=>{
 const {readFileSync}=await import('node:fs')
 const raw=JSON.parse(readFileSync(new URL('./purpose.asc.fixture.json',import.meta.url),'utf8'))
 assert.equal(readPurpose(raw).evaluation.manual_candidate,'existing-asc')
 for(const mutate of [
  (r:any)=>{delete r.evaluation.selection['existing-asc']},
  (r:any)=>{delete r.evaluation.candidate_parameters['shared-31']},
  (r:any)=>{r.common_frame_ids.push(37)},
  (r:any)=>{delete r.evaluation.provenance.asc_sha256},
 ]) {const r=structuredClone(raw);mutate(r);assert.throws(()=>readPurpose(r))}
})

test('冻结帧数组展示真实起止帧',()=>{assert.equal(frameRange([26,27,36]),'26–36');assert.equal(frameRange([]),'无');assert.equal(frameRange(undefined),'无')})
