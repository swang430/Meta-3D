import test from 'node:test'
import assert from 'node:assert/strict'
import { buildRouteAcquisitionRequest, buildRouteConfirmation, routePreviewDisplay,
  routeMatchesSaved, canAdoptRoute, runningRouteIdentity, canReleaseRouteStart } from '../src/features/TopologyEditor/routeCalibrationState.ts'

const normalNodes=[{id:'ce',type:'ce_port',label:'B1.1',params:{}},{id:'pad',type:'pad',label:'显示名',params:{ports:['in','out']}},
  {id:'probe',type:'probe',label:'探头',params:{probe_id:0,polarization:'V'}}]
const normalEdges=[{id:'feed',source:'ce',target:'pad',source_pin:'out',target_pin:'in'},
  {id:'end',source:'pad',target:'probe',source_pin:'out',target_pin:'in'}]
const referenceNodes=['air','ref','rx','sa'].map((id,index)=>({id,type:['air_path','reference_antenna','receive_cable','signal_analyzer'][index],params:{connection_scope:'calibration'}}))
const referenceEdges=['probe','air','ref','rx'].map((source,index)=>({id:`ref-${index}`,source,target:referenceNodes[index].id,source_pin:'out',target_pin:'in'}))
const route = {lab_profile_id:'lab-a',topology_id:'topo-a',operating_mode:'mimo_ota',chain_id:'end',
  ce_port:'B1.1',probe_id:0,polarization:'V',route_digest:'a'.repeat(64),configuration_digest:'b'.repeat(64),
  node_ids:['ce','pad','probe'],connection_ids:['feed','end'],nodes:normalNodes,connections:normalEdges,
  ports:normalEdges.map(edge=>({connection_id:edge.id,...edge})),calibration_node_ids:['air','ref','rx','sa'],
  calibration_nodes:referenceNodes,calibration_connections:referenceEdges,calibration_connection_ids:referenceEdges.map(edge=>edge.id)} as never
const graph={nodes:[...normalNodes,...referenceNodes],connections:[...normalEdges,...referenceEdges],operating_modes:[
  {id:'mimo_ota',active_connections:['feed','end']},{id:'calibration',active_connections:referenceEdges.map(edge=>edge.id)}]} as never
const scope={labId:'lab-a',topologyId:'topo-a',mode:'mimo_ota',dirty:false,graph}
const form={frequency:'2595',power:'-30',antenna:'参考天线V/中心位置',cable:'2',cableSource:'接收线缆记录@2595MHz',samples:'5',fixed:true,safe:true}
const preview={selection:route,acquisition_run_id:'run-old',expected_current_application_id:null,
  old_value_db:null,new_net_loss_db:28,delta_db:null,eligibility:{eligible_for_adoption:true,
    measurement_provenance:'real',certification_status:'unknown',blockers:[],warnings:['完整不确定度待核']}} as never

test('未保存草稿/跨实验室或模式的路径不能触发旧服务器图采集',()=>{
  assert.equal(routeMatchesSaved(scope,route),true)
  for(const changed of [{dirty:true},{labId:'lab-b'},{topologyId:'other'},{mode:'trp_tis'},{mode:'calibration'}]){
    assert.equal(routeMatchesSaved({...scope,...changed},route),false)
    assert.throws(()=>buildRouteAcquisitionRequest({...scope,...changed},route,form))
  }
})
test('开始请求显式发送完整保存路径身份，不能漏route_digest或用设置功率算实测值',()=>{
  const request=buildRouteAcquisitionRequest(scope,route,form)
  assert.equal(request.topology_id,'topo-a');assert.equal(request.operating_mode,'mimo_ota')
  assert.equal(request.route_digest,'a'.repeat(64));assert.equal(request.configuration_digest,'b'.repeat(64))
  assert.equal(request.requested_power_dbm,-30);assert.equal(request.receive_cable_loss_db,2)
  assert.equal('net_loss_db' in request,false)
  assert.throws(()=>buildRouteAcquisitionRequest(scope,route,{...form,frequency:''}))
  assert.throws(()=>buildRouteAcquisitionRequest(scope,route,{...form,safe:false}))
})
test('活动记录身份从该run快照读取，切模式不能把历史run冒充当前选择',()=>{
  const record={run_id:'run-old',lab_profile_id:'lab-a',status:'running',result:{version:2,configuration:{route_selection:route}}} as never
  assert.deepEqual(runningRouteIdentity(record),route)
  assert.equal(runningRouteIdentity({...record,result:{version:1,configuration:{route_selection:route}}} as never),undefined)
  assert.equal(canAdoptRoute({...scope,mode:'trp_tis'},route,preview),false)
  assert.equal(canAdoptRoute(scope,route,{...preview,acquisition_run_id:'another'} as never,'run-old'),false)
})
test('旧新差值只格式化服务器字段，缺值未知且负增益不取绝对值',()=>{
  assert.deepEqual(routePreviewDisplay(preview),{old:'未知',next:'28.00 dB',delta:'未知'})
  assert.equal(routePreviewDisplay({...preview,new_net_loss_db:-12,old_value_db:20,delta_db:-32} as never).next,'-12.00 dB')
  assert.equal(routePreviewDisplay({...preview,new_net_loss_db:28,old_value_db:20,delta_db:null} as never).delta,'未知')
})
test('只有服务器真实可采用资格及同一保存路径允许确认，Mock/未知不能借确认洗白',()=>{
  assert.equal(canAdoptRoute(scope,route,preview),true)
  for(const provenance of ['simulated','unknown']) assert.equal(canAdoptRoute(scope,route,
    {...preview,eligibility:{...preview.eligibility,measurement_provenance:provenance}} as never),false)
  assert.equal(canAdoptRoute(scope,route,{...preview,eligibility:{...preview.eligibility,eligible_for_adoption:false}} as never),false)
})
test('确认只带服务器run和CAS身份、显式截止及幂等键，不传loss/认证布尔',()=>{
  const body=buildRouteConfirmation(scope,route,preview,'2099-01-01T00:00:00Z','idempotency-a')
  assert.equal(body.acquisition_run_id,'run-old');assert.equal(body.expected_current_application_id,null)
  assert.equal(body.idempotency_key,'idempotency-a');assert.equal(body.adoption_valid_until,'2099-01-01T00:00:00.000Z')
  assert.equal('net_loss_db' in body,false);assert.equal('certification_status' in body,false)
  assert.throws(()=>buildRouteConfirmation(scope,route,preview,'','key'))
  assert.throws(()=>buildRouteConfirmation(scope,route,preview,'2000-01-01T00:00:00Z','key'))
})
test('恢复空历史不能提前释放pending开始锁，也不能把网络/5xx未知当未启动',()=>{
  assert.equal(canReleaseRouteStart(true,422,[]),false)
  assert.equal(canReleaseRouteStart(false,undefined,[]),false)
  assert.equal(canReleaseRouteStart(false,500,[]),false)
  assert.equal(canReleaseRouteStart(false,422,undefined),false)
  assert.equal(canReleaseRouteStart(false,409,[{status:'running'}] as never),false)
  assert.equal(canReleaseRouteStart(false,422,[]),true)
})
test('服务器新候选不能高亮旧保存图；只比所选身份，不阻断坐标或无关显示变化',()=>{
  const changed=()=>structuredClone(graph) as any
  let view=changed();view.nodes[0].label='B1.3'
  assert.equal(routeMatchesSaved({...scope,graph:view},route),false)
  view=changed();view.connections[1].target_pin='other'
  assert.equal(routeMatchesSaved({...scope,graph:view},route),false)
  view=changed();view.nodes.find(n=>n.id==='sa').params.instrument_category_id='another-device'
  assert.equal(routeMatchesSaved({...scope,graph:view},route),false)
  view=changed();view.nodes[1].label='无关显示文案';view.nodes[1].position={x:999,y:99};view.nodes[1].params.notes='说明'
  assert.equal(routeMatchesSaved({...scope,graph:view},route),true)
  view=changed();view.nodes[0].label='只是显示';view.connections[0].ce_port='B1.1'
  assert.equal(routeMatchesSaved({...scope,graph:view},route),true)
})
