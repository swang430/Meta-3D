import test from 'node:test'
import assert from 'node:assert/strict'
import { buildCalibrationGraph } from '../src/features/TopologyEditor/calibrationGraph.ts'

const topology = { id:'topo', chamber_id:'room', nodes:[
  {id:'ce',type:'ce_port',label:'B1.1',params:{}},
  {id:'switch',type:'rf_switch',label:'固定开关',params:{}},
  {id:'probe',type:'probe',label:'探头0',params:{probe_id:0}},
], connections:[{id:'feed',source:'ce',target:'switch',cable_loss_db:1},
  {id:'v',source:'switch',target:'probe',cable_loss_db:2}],
  operating_modes:[{id:'mimo_ota',active_connections:['feed','v']}] } as never
const scope = {digest:'a'.repeat(64),payload:{lab_profile_id:'lab',chamber_id:'room',operating_mode:'mimo_ota',
  topology:{id:'topo',nodes:topology.nodes.map(n=>({...n,parameters:n.params})),connections:topology.connections,
    active_connections:['feed','v']},chains:[{chain_id:'v',ce_port:'B1.1',probe_id:0,polarization:'V',cable_loss_db:2}]}} as never

test('从保存连接选择通路，补空口和参考天线而不修改开关拓扑', () => {
  const before = JSON.stringify(topology)
  const graph = buildCalibrationGraph(topology,scope,'lab','v')
  assert.equal(graph.problem,null)
  assert.deepEqual(graph.highlightedConnectionIds,['feed','v'])
  for (const role of ['air','reference','receive_cable','analyzer']) assert.ok(graph.nodes.some(n=>n.data.role===role))
  assert.equal(JSON.stringify(topology),before)
  assert.equal(graph.edges.find(e=>e.id==='v')?.data?.label,'配置损耗 2.00 dB')
  assert.ok(graph.nodes.some(n=>n.data.title==='F64 输出 B1.1'))
})

test('不把其它实验室或不同拓扑的解析通路绘为当前可测', () => {
  assert.ok(buildCalibrationGraph(topology,scope,'other','v').problem)
  assert.ok(buildCalibrationGraph({...topology,id:'other'} as never,scope,'lab','v').problem)
  assert.ok(buildCalibrationGraph(topology,scope,'lab','not-declared').problem)
})

test('缺节点或保存端口与解析不一致时不画假的输出位置', () => {
  const changed=(nodes:unknown[])=>({...scope,payload:{...scope.payload,topology:{...scope.payload.topology,nodes}}}) as never
  assert.ok(buildCalibrationGraph(topology,changed(scope.payload.topology.nodes.filter(n=>n.id!=='ce')),'lab','v').problem)
  assert.ok(buildCalibrationGraph(topology,changed(scope.payload.topology.nodes.map(n=>n.id==='ce'?{...n,label:'B1.2'}:n)),'lab','v').problem)
})

test('同编号图更新后只消费测量配置里的保存接线，不混旧图标签',()=>{
  const updated={...scope,payload:{...scope.payload,topology:{...scope.payload.topology,
    nodes:scope.payload.topology.nodes.map(n=>n.id==='probe'?{...n,label:'探头9 H'}:n)},
    chains:[{...scope.payload.chains[0],probe_id:9,polarization:'H'}]}}
  const graph=buildCalibrationGraph(topology,updated as never,'lab','v')
  assert.equal(graph.problem,null)
  assert.ok(graph.nodes.some(n=>n.data.title==='探头9 H'))
  assert.equal(graph.nodes.some(n=>n.data.title==='探头0'),false)
})

test('上游歧义、断路或非法端口受控拒绝，不把半条路径开放采集',()=>{
  const original=scope.payload.topology
  for(const graph of [
    {...original,connections:[...original.connections,{id:'another',source:'ce',target:'switch'}],active_connections:['feed','another','v']},
    {...original,connections:original.connections.filter(e=>e.id!=='feed')},
    {...original,nodes:original.nodes.map(n=>n.id==='ce'?{...n,parameters:{ce_port:42}}:n)},
  ])assert.ok(buildCalibrationGraph(topology,{...scope,payload:{...scope.payload,topology:graph}} as never,'lab','v').problem)
})

test('实测属于整条路径而非空口或电缆；冻结身份与摘要不符不覆盖当前图', () => {
  const result = {run_id:'r',lab_profile_id:'lab',status:'completed',result:{status:'completed',cleanup_confirmed:true,
    net_loss_db:-12,request:{chain_id:'v',configuration_digest:'a'.repeat(64),frequency_mhz:2595,requested_power_dbm:-20},
    configuration:{chain:{chain_id:'v',ce_port:'B1.1',probe_id:0,polarization:'V'}},
    samples:[{source_after_dbm:-20,received_dbm:-10}]}} as never
  const measured = buildCalibrationGraph(topology,scope,'lab','v',result)
  assert.ok(measured.nodes.some(n=>n.data.title==='整条通路测量' && n.data.reading.includes('-12.00')))
  assert.equal(measured.edges.find(e=>e.id==='v')?.data?.label,'配置损耗 2.00 dB')
  assert.equal(measured.edges.some(e=>e.data?.label?.includes('-12')),false)
  for (const changed of [{...result,lab_profile_id:'other'}, {...result,result:{...result.result,
    request:{...result.result.request,configuration_digest:'b'.repeat(64)}}},
    {...result,result:{...result.result,configuration:{chain:{chain_id:'v',ce_port:'B1.2',probe_id:0,polarization:'V'}}}}]) {
    const graph = buildCalibrationGraph(topology,scope,'lab','v',changed as never)
    assert.ok(graph.notice)
    assert.equal(graph.nodes.some(n=>n.data.reading?.includes('-12.00')),false)
  }
})

test('模拟或停发未确认不在图上显示夹带的实测数字', () => {
  for (const status of ['simulated','cleanup_unconfirmed','failed','cancelled','running']) {
    const record = {lab_profile_id:'lab',status,result:{status,cleanup_confirmed:false,net_loss_db:28,
      request:{chain_id:'v',configuration_digest:'a'.repeat(64)},configuration:{chain:scope.payload.chains[0]},
      samples:[{source_after_dbm:-20,received_dbm:-50}]}}
    const graph=buildCalibrationGraph(topology,scope,'lab','v',record as never)
    assert.equal(graph.nodes.some(n=>n.data.reading?.includes('28.00')),false)
  }
})
