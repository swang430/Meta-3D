import test from 'node:test'
import assert from 'node:assert/strict'
import {fixedRouteDisplay} from '../src/features/LabWorkspace/fixedRouteDisplay.ts'
import {batchResultRecord,adoptionHistoryLabel} from '../src/features/TopologyEditor/calibrationResultView.ts'
const item={item_id:'item',run_id:'run'} as never
const job={job_id:'job',lab_id:'lab'} as never
const make=()=>({run_id:'run',lab_profile_id:'lab',status:'completed',result:{run_id:'run',lab_profile_id:'lab',status:'completed',cleanup_confirmed:true,
  sample_std_db:0,states:{batch_job_id:'job',batch_item_id:'item'},configuration:{}}})
test('重复性保留真实零、排除缺测模拟失败和未清理',()=>{
  const value=make()
  assert.equal(fixedRouteDisplay(value as never).repeatability,'0.000 dB')
  for(const sample_std_db of [null,undefined,NaN,Infinity])assert.equal(fixedRouteDisplay({...value,result:{...value.result,sample_std_db}} as never).repeatability,'未知')
  for(const status of ['simulated','failed','running','cancelled','cleanup_unconfirmed'])assert.equal(fixedRouteDisplay({...value,status} as never).repeatability,'未知')
  assert.equal(fixedRouteDisplay({...value,result:{...value.result,cleanup_confirmed:false}} as never).repeatability,'未知')
  assert.equal(fixedRouteDisplay({...value,result:{...value.result,configuration:{binding:{execution_mode:'simulated'}}}} as never).repeatability,'未知')
})
test('批摘要只接受同实验室同run同父批同项目的子记录',()=>{
  const value=make()
  assert.equal(batchResultRecord(job,item,[value as never]),value)
  for(const record of [{...value,lab_profile_id:'other'},{...value,run_id:'other'},
    {...value,result:{...value.result,run_id:'other'}},{...value,result:{...value.result,lab_profile_id:'other'}},
    {...value,result:{...value.result,states:{batch_job_id:'other',batch_item_id:'item'}}},
    {...value,result:{...value.result,states:{batch_job_id:'job',batch_item_id:'other'}}},
    {...value,batch_context:{job_id:'other'}}])assert.equal(batchResultRecord(job,item,[record as never]),undefined)
  assert.equal(batchResultRecord(job,item,[]),undefined)
})
test('未读采用历史不是未采用；有记录也不宣称当前有效',()=>{
  const record=make() as never
  assert.match(adoptionHistoryLabel(record,undefined),/尚未核对/)
  assert.match(adoptionHistoryLabel(record,[]),/本页历史未见/)
  assert.match(adoptionHistoryLabel(record,[{acquisition_run_id:'run',selection_snapshot:{lab_profile_id:'lab'}} as never]),/当前适用性及撤销状态另核/)
})
