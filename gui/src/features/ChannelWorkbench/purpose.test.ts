import test from 'node:test'
import assert from 'node:assert/strict'
import { purposeParameters, readPurpose, frameRange } from './purpose.ts'
const defaults={selection_start:0,selection_end:25,holdout_start:26,holdout_end:37,tap_budget_max:31,matrix_nmse_p95_max:1,phase_error_p95_max_deg:60,objective:'phase',mode:'conducted',manual_candidate:''}
test('冻结连续相邻非重叠区间与有限约束，拒绝非法手选',()=>{
 assert.deepEqual(purposeParameters(defaults),defaults)
 for(const change of [{holdout_start:25},{holdout_start:27},{selection_start:-1},{holdout_end:NaN},{tap_budget_max:32},{phase_error_p95_max_deg:181},{matrix_nmse_p95_max:-1},{manual_candidate:'best'}]) assert.throws(()=>purposeParameters({...defaults,...change}))
})
test('拒绝正式通过、自动采纳以及无达标却返回留出推荐',()=>{
 const raw={schema:'mpdb-purpose/1',status:'no_candidate_meets_constraints',formal_verdict:null,hardware_verified:false,alignment_status:'unverified',simulated:false,source_frame_count:38,common_frame_ids:Array.from({length:38},(_,i)=>i),frame_ids:Array.from({length:38},(_,i)=>i),evaluation:{schema:'candidate-evaluation/1',status:'no_candidate_meets_constraints',selected_candidate:null,holdout:null,manual_candidate:null,manual_holdout:null,formal_verdict:null,alignment_status:'unverified',automatic_adoption:false,ota_status:'not_evaluated',selection:Object.fromEntries(['independent-24','independent-26','independent-31','shared-24','shared-26','shared-31'].map(c=>[c,{}])),candidate_parameters:Object.fromEntries(['independent-24','independent-26','independent-31','shared-24','shared-26','shared-31'].map(c=>[c,{}])),plan:{},provenance:{},plan_fingerprint:'a'.repeat(64),selection_fingerprint:'b'.repeat(64),selection_input_fingerprint:'c'.repeat(64)},download_url:'/api/v1/channel-assets/mpdb-projects/purpose-evaluations/123/report.zip',points_url:'/api/v1/channel-assets/mpdb-projects/purpose-evaluations/123/points.csv'}
 assert.equal(readPurpose(raw).evaluation.selected_candidate,null)
 for(const change of [{formal_verdict:'pass'},{hardware_verified:true},{evaluation:{...raw.evaluation,automatic_adoption:true}},{evaluation:{...raw.evaluation,holdout:{}}},{points_url:'https://evil.example/points.csv'}]) assert.throws(()=>readPurpose({...raw,...change}))
})

test('可选 ASC 冻结共同范围并允许第七个人工候选',()=>{
 assert.equal(purposeParameters({...defaults,holdout_end:36,manual_candidate:'existing-asc'},true).manual_candidate,'existing-asc')
 assert.throws(()=>purposeParameters({...defaults,holdout_end:36,manual_candidate:'existing-asc'}))
 assert.deepEqual(purposeParameters(defaults,true),defaults)
 assert.equal(purposeParameters({...defaults,holdout_end:null},true).holdout_end,null)
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

test('共同范围按实际来源与 ASC 恢复帧交集校验，支持不同长度及全覆盖',async()=>{
 const {readFileSync}=await import('node:fs')
 const fixture=JSON.parse(readFileSync(new URL('./purpose.asc.fixture.json',import.meta.url),'utf8'))
 for(const count of [5,42]) {
  const r=structuredClone(fixture), ids=Array.from({length:count},(_,i)=>i+10)
  r.frame_ids=ids;r.source_frame_count=count;r.common_frame_ids=ids
  r.evaluation.provenance.existing_asc_reference.applicable_frames=ids
  r.evaluation.provenance.existing_asc_reference.unmatched_frames=[]
  assert.doesNotThrow(()=>readPurpose(r))
  for(const invalid of [[...ids,999],ids.slice(1),[...ids,ids[0]]]) assert.throws(()=>readPurpose({...r,common_frame_ids:invalid}))
  r.evaluation.provenance.existing_asc_reference.applicable_frames=ids.slice(0,-1)
  r.evaluation.provenance.existing_asc_reference.unmatched_frames=[ids.at(-1)]
  assert.throws(()=>readPurpose(r))
  r.common_frame_ids=ids.slice(0,-1)
  assert.doesNotThrow(()=>readPurpose(r))
 }
})

test('无 ASC 时共同帧等于实际来源，面板不预设 ASC 缺帧',async()=>{
 const {readFileSync}=await import('node:fs')
 const raw=JSON.parse(readFileSync(new URL('./purpose.asc.fixture.json',import.meta.url),'utf8'))
 delete raw.evaluation.candidate_parameters['existing-asc'];delete raw.evaluation.selection['existing-asc']
 raw.evaluation.manual_candidate=null
 for(const ids of [[2,3,4],[0,1,2,3,4,5,6,7,8,9]]) {
  raw.frame_ids=ids;raw.source_frame_count=ids.length;raw.common_frame_ids=ids
  assert.doesNotThrow(()=>readPurpose(raw))
  assert.throws(()=>readPurpose({...raw,common_frame_ids:ids.slice(1)}))
 }
 const panel=readFileSync(new URL('./MpdbPurposePanel.tsx',import.meta.url),'utf8')
 assert.doesNotMatch(panel,/\b(?:36|37|38)\b/)
 assert.match(panel,/未核验/)
 assert.match(panel,/required=\{name!=='holdout_end'\}/)
 assert.match(panel,/v===null\?body.delete\(key\)/)
})
