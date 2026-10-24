import test from 'node:test'
import assert from 'node:assert/strict'
import * as state from '../src/features/TopologyEditor/routeCalibrationState.ts'
import MockAdapter from 'axios-mock-adapter'
import client from '../src/api/client.ts'
import { updateInstrumentCategory } from '../src/api/service.ts'
import { withoutSynthesizedConnectionParams } from '../src/features/Equipment/invalidStoredFields.ts'

const route=(id:string)=>({lab_profile_id:'lab',topology_id:'topo',operating_mode:'mimo_ota',chain_id:id,
  ce_port:'B1.1',probe_id:0,polarization:'V',route_digest:'a'.repeat(64),configuration_digest:'b'.repeat(64),
  node_ids:['ce',id],connection_ids:[id],nodes:[{id:'ce',type:'ce_port',label:'B1.1',params:{}},{id,type:'probe',params:{}}],
  connections:[{id,source:'ce',target:id,source_pin:'out',target_pin:'in'}],calibration_nodes:[],calibration_node_ids:[],calibration_connections:[],calibration_connection_ids:[]})
const paths=[route('p1'),route('p2')]
const scope={labId:'lab',topologyId:'topo',mode:'mimo_ota',dirty:false,graph:{nodes:[paths[0].nodes[0],paths[0].nodes[1],paths[1].nodes[1]],
  connections:paths.flatMap(p=>p.connections),operating_modes:[{id:'mimo_ota',active_connections:['p1','p2']}]}}
const fields={power:'-30',samples:'3',fixed:true,safe:true}
const references=['p1','p2'].flatMap(chainId=>[100,200].map(frequency=>({chainId,frequency,antenna:`中心-${chainId}`,cable:'2',cableSource:'接收线记录'})))
const request=()=>state.buildBatchRequest(scope as never,paths as never,['p1','p2'],[100,200],references,fields)
const item={item_id:'i1',status:'completed',run_id:'r1',request:{reference_antenna:'中心-p1'}}
const job=(patch={})=>({job_id:'job',lab_id:'lab',status:'waiting_manual',current_index:0,transition_id:'t1',
  lease_id:'lease',finalization_committed:false,f64_control_released:null,items:[item],...patch}) as never
const child=(patch={})=>({run_id:'r1',status:'completed',result:{status:'completed',cleanup_confirmed:true,states:{batch_job_id:'job'}},
  batch_context:{job_id:'job',active:true,finalized:false},...patch}) as never

test('多选保存路径及逐频点参考位置生成完整请求，不补造缺少的参考量',()=>{
  const body=request()
  assert.deepEqual(body.chain_ids,['p1','p2']);assert.deepEqual(body.frequencies_mhz,[100,200])
  assert.equal(body.references.length,4)
  assert.deepEqual(body.references[3],{chain_id:'p2',frequency_mhz:200,reference_antenna:'中心-p2',receive_cable_loss_db:2,receive_cable_source:'接收线记录'})
  assert.throws(()=>state.buildBatchRequest(scope as never,paths as never,['p1','p2'],[100,200],references.slice(1),fields))
  assert.throws(()=>state.buildBatchRequest({...scope,dirty:true} as never,paths as never,['p1'],[100],references,fields))
})
test('同请求未知回执重试保持UUID；变更请求不能复用未知尝试',()=>{
  const attempt=state.batchStartAttempt(null,request(),'uuid-one')
  assert.equal(state.batchStartAttempt(attempt,request(),'uuid-two').key,'uuid-one')
  assert.throws(()=>state.batchStartAttempt(attempt,{...request(),requested_power_dbm:-20},'uuid-two'))
})
test('开始只接受含接线声明重预览后的同一摘要，不拿旧摘要启动',()=>{
  const body=request(),plan={lab_profile_id:'lab',topology_id:'topo',operating_mode:'mimo_ota',preview_digest:'preview',switch_scope_digest:'switch',items:[]}
  assert.throws(()=>state.batchStartRequest(scope as never,body,plan as never))
  const confirmation={operator:'操作员自述',confirmed_at:'2026-10-25T01:00:00+08:00',note:'已核对',switch_scope_digest:'switch'}
  assert.throws(()=>state.batchStartRequest(scope as never,{...body,switch_wiring_confirmation:confirmation},plan as never))
  assert.equal(state.batchStartRequest(scope as never,{...body,switch_wiring_confirmation:confirmation},{...plan,switch_wiring_confirmation:confirmation} as never).preview_digest,'preview')
  assert.throws(()=>state.batchStartRequest({...scope,dirty:true} as never,body,{...plan,switch_scope_digest:null} as never))
})
test('活动批不会因空历史、单项完成、网络空值或未落盘提前解锁',()=>{
  for(const value of [undefined,job(),job({status:'completed'}),job({status:'completed',f64_control_released:true,finalization_committed:false})])
    assert.equal(state.batchCanRelease(value),false)
  assert.equal(state.batchCanRelease(job({status:'completed',f64_control_released:true,finalization_committed:true,finalization_id:'final',all_started_cleanup_confirmed:true})),true)
  assert.equal(state.batchCanRelease(job({status:'completed',f64_control_released:null,finalization_committed:true,finalization_id:'final',all_started_cleanup_confirmed:true})),false)
  assert.equal(state.batchCanRelease(job({status:'completed',f64_control_released:true,finalization_committed:true,finalization_id:'final',all_started_cleanup_confirmed:true,
    items:[{...item,run_id:null}]})),false)
  assert.equal(state.batchCanRelease(job({status:'completed',f64_control_released:true,finalization_committed:true,finalization_id:'final',
    all_started_cleanup_confirmed:false,items:[{...item,status:'simulated'}]})),true)
  const mixed=job({status:'completed',f64_control_released:true,finalization_committed:true,finalization_id:'final',all_started_cleanup_confirmed:false,
    items:[{...item,status:'simulated'},{...item,item_id:'i2',run_id:'r2'}]})
  assert.equal(state.batchCanRelease(mixed),false)
  assert.equal(state.batchCanRelease(mixed,[child({run_id:'r2'})]),true)
  assert.equal(state.batchCanRelease(mixed,[child({run_id:'r2',result:{cleanup_confirmed:null}})]),false)
})
test('人工继续必须匹配当前transition/项，cleanup未知不允许换线',()=>{
  const current=job({items:[{...item,status:'waiting_manual',run_id:null}]})
  assert.equal(state.buildBatchContinue(current,[],'i1','t1','中心-p1',true).transition_id,'t1')
  assert.throws(()=>state.buildBatchContinue(current,[],'i1','old-transition','中心-p1',true))
  assert.throws(()=>state.buildBatchContinue(job(),[child({result:{status:'completed',cleanup_confirmed:null}})],'i1','t1','中心-p1',true))
  assert.throws(()=>state.buildBatchContinue(current,[],'i1','t1','其他位置',true))
})
test('模拟等待能继续但绝不显示实物换线安全；未读到所有child也未知',()=>{
  assert.equal(state.batchToneState(job(),[]),'unknown')
  assert.equal(state.batchToneState(job(),[child()]),'confirmed')
  assert.equal(state.batchToneState(job(),[child({status:'simulated',result:{status:'simulated',cleanup_confirmed:false}})]),'simulated')
})
test('批子项采用入口沿服务器资格且等待父终止、释放与最终提交，unknown不能洗白',()=>{
  assert.equal(state.batchChildReady(child()),false)
  assert.equal(state.batchChildReady(child({batch_context:{active:false,finalized:true,job_id:'job',lease_id:'lease',finalization_id:'final'}})),true)
  assert.equal(state.batchChildReady(child({batch_context:{active:false,finalized:false,job_id:'job'}})),false)
  assert.equal(state.batchChildReady(child({batch_context:undefined})),false)
  assert.equal(state.batchChildReady({run_id:'standalone',status:'completed',result:{configuration:{}}} as never),true)
})
test('清单进度逐项对应，不把首项完成显示整套成功',()=>{
  assert.deepEqual(state.batchCounts(job({items:[item,{...item,item_id:'i2',status:'waiting_manual',run_id:null}]})),{total:2,completed:1,simulated:0,failed:0})
})
test('原图正常模式同时显示所选参考段，其他模式不注入该参考段',()=>{
  const selected={...paths[0],calibration_node_ids:['air'],calibration_nodes:[{id:'air',type:'air_path',params:{}}],calibration_connection_ids:['ref'],
    calibration_connections:[{id:'ref',source:'p1',target:'air',source_pin:'out',target_pin:'in'}]}
  const graph={...scope.graph,nodes:[...scope.graph.nodes,...selected.calibration_nodes],connections:[...scope.graph.connections,...selected.calibration_connections],
    operating_modes:[...scope.graph.operating_modes,{id:'calibration',active_connections:['ref']}]}
  assert.deepEqual(state.routeCanvasConnections(graph as never,'mimo_ota',selected as never),['p1','p2','ref'])
  assert.deepEqual(state.routeCanvasConnections(graph as never,'other',selected as never),[])
})
test('显式路径按操作员选取顺序保存，精确映射节点名，不由标签推算端口',()=>{
  const graph={nodes:[{id:'ce',type:'ce_port'},{id:'sw',type:'switch_slot'},{id:'pv',type:'probe'}],connections:[
    {id:'a',source:'ce',target:'sw',source_pin:'out',target_pin:'actual-in'},
    {id:'b',source:'sw',target:'pv',source_pin:'actual-out',target_pin:'in'}]}
  assert.deepEqual(state.probePathDeclaration(graph as never,'pv',['a','b'],[{node_id:'sw',path_name:'现场映射'}]),
    {connection_ids:['a','b'],switch_mappings:[{node_id:'sw',path_name:'现场映射'}]})
  assert.throws(()=>state.probePathDeclaration(graph as never,'pv',['b','a'],[{node_id:'sw',path_name:'现场映射'}]))
  assert.throws(()=>state.probePathDeclaration(graph as never,'pv',['a','b'],[]))
})
test('确定的请求校验拒绝可修正输入，空历史本身及网络未知不可释放开始锁',()=>{
  assert.equal(state.batchRejectionCanRelease(422,[],'key'),true)
  assert.equal(state.batchRejectionCanRelease(undefined,[],'key'),false)
  assert.equal(state.batchRejectionCanRelease(500,[],'key'),false)
  assert.equal(state.batchRejectionCanRelease(422,undefined,'key'),false)
  assert.equal(state.batchRejectionCanRelease(422,[job()],'key'),false)
  assert.equal(state.batchRejectionCanRelease(422,[job({status:'completed',idempotency_key:'key'})],'key'),false)
})
test('既有仪器JSON保存链序列化保留操作员端口配对，不删掉映射扩展字段（既有行为刻画）',async()=>{
  const adapter=new MockAdapter(client)
  try{
    const parsed=JSON.parse('{"port_maps":{"route-v":{"switch_id":"1:INT_RELAY_A","relay_type":"sp6t","input_port":0,"output_port":2,"topology_input_pin":"physical-in","topology_output_pin":"physical-out","note":"现场声明"}}}')
    const connection=withoutSynthesizedConnectionParams({connection_params:parsed},{},'operator')
    let wire:unknown
    adapter.onPut('/instruments/rfSwitch').reply(config=>{wire=JSON.parse(config.data);return [200,{key:'rfSwitch'}]})
    await updateInstrumentCategory('rfSwitch',{connection})
    assert.deepEqual(wire,{connection:{connection_params:{port_maps:{'route-v':{switch_id:'1:INT_RELAY_A',relay_type:'sp6t',input_port:0,output_port:2,
      topology_input_pin:'physical-in',topology_output_pin:'physical-out',note:'现场声明'}}}}})
  }finally{adapter.restore()}
})
test('新页面恢复服务器未安全结束批，不只恢复运行三态，也不锁已安全真实或模拟历史',()=>{
  const safe=job({job_id:'safe',status:'completed',f64_control_released:true,finalization_committed:true,finalization_id:'final',all_started_cleanup_confirmed:true})
  const simulated=job({job_id:'safe-simulated',status:'completed',f64_control_released:true,finalization_committed:true,finalization_id:'final',
    all_started_cleanup_confirmed:false,items:[{...item,status:'simulated'}]})
  assert.equal(state.findUnsettledBatch([]),undefined)
  assert.equal(state.findUnsettledBatch([safe,simulated]),undefined)
  for(const status of ['running','waiting_manual','paused_failure','interrupted','cleanup_unconfirmed','incomplete','completed','failed','cancelled']){
    const unsafe=job({job_id:`unsafe-${status}`,status,finalization_committed:false,f64_control_released:null})
    assert.equal(state.findUnsettledBatch([safe,simulated,unsafe])?.job_id,`unsafe-${status}`)
    assert.equal(state.batchRejectionCanRelease(422,[safe,unsafe],'new-key'),false)
  }
  assert.equal(state.findUnsettledBatch([job({status:'completed',finalization_committed:true,finalization_id:'final',f64_control_released:null})])?.job_id,'job')
  const mixed=job({status:'completed',f64_control_released:true,finalization_committed:true,finalization_id:'final',all_started_cleanup_confirmed:false,
    items:[{...item,status:'simulated'},{...item,item_id:'i2',run_id:'r2'}]})
  assert.equal(state.findUnsettledBatch([mixed])?.job_id,'job')
  assert.equal(state.findUnsettledBatch([mixed],[child({run_id:'r2'})]),undefined)
})
test('人工等待不得把completed等缺run身份的已启动项过滤成空；合法首次人工步骤仍可确认',()=>{
  const waiting={...item,item_id:'next',status:'waiting_manual',run_id:null}
  const first=job({items:[waiting]})
  assert.equal(state.batchToneState(first,[]),'confirmed')
  assert.equal(state.buildBatchContinue(first,[],'next','t1','中心-p1',true).item_id,'next')
  for(const status of ['completed','simulated','measuring','running','cleanup_unconfirmed','interrupted','incomplete']){
    const corrupt=job({current_index:1,items:[{...item,status,run_id:null},waiting]})
    assert.equal(state.batchToneState(corrupt,[]),'unknown',status)
    assert.throws(()=>state.buildBatchContinue(corrupt,[],'next','t1','中心-p1',true),status)
  }
})
