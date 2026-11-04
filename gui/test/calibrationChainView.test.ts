import { test } from 'node:test'
import assert from 'node:assert/strict'
import { calibrationCanvasConnections, calibrationNodeVisible, instrumentPresentation } from '../src/features/TopologyEditor/calibrationChainView.ts'
import type { SwitchTopology } from '../src/api/switchTopologyService.ts'
import type { HALReadinessResponse, InstrumentCategory } from '../src/types/api.ts'
const graph = {nodes:[],connections:[{id:'ref',modes:['calibration']},{id:'legacy'}],operating_modes:[{id:'calibration',active_connections:['ref','wire']}]} as unknown as SwitchTopology
test('校准视图并入已声明参考边且不修改原图，关闭时恢复正常模式',()=>{
  const before=structuredClone(graph)
  assert.deepEqual(calibrationCanvasConnections(graph,['normal'],true),['normal','ref','wire'])
  assert.deepEqual(calibrationCanvasConnections(graph,['normal'],false),['normal'])
  assert.deepEqual(graph,before)
})
test('未接线的矢网、分析仪与信号源仍可见，不创造端口与连接',()=>{
  for(const type of ['vna','signal_analyzer','signal_generator']){
    const node={id:type,type,label:type,position:{x:0,y:0},params:{}}
    assert.equal(calibrationNodeVisible(node,true),true)
    assert.equal(calibrationNodeVisible(node,false),false)
    assert.deepEqual(node.params,{})
  }
})
test('目录存在不是运行就绪；错实验室快照拒绝发布',()=>{
  const node={id:'sa',type:'signal_analyzer',label:'SA',position:{x:0,y:0},params:{instrument_category_id:'cat'}}
  const categories=[{categoryId:'cat',key:'signalAnalyzer',label:'分析仪',models:[],driverMode:'mock',selectedModelId:null}] as InstrumentCategory[]
  const report={lab_profile:{profile_id:'other'},drivers:[{category:'signalAnalyzer',status:'ok',model:'设备',detail:'driver'}]} as HALReadinessResponse
  assert.equal(instrumentPresentation(node,categories,report,'lab').snapshot,'运行状态未知')
  report.lab_profile.profile_id='lab'
  assert.match(instrumentPresentation(node,categories,report,'lab').binding,/未提供/)
  assert.match(instrumentPresentation(node,categories,report,'lab').resource,/配置模式 mock/)
  assert.match(instrumentPresentation(node,[],report,'lab').resource,/未关联/)
})
