import assert from 'node:assert/strict'
import test from 'node:test'
import {buildRouteAcquisitionRequest,buildBatchRequest} from '../src/features/TopologyEditor/routeCalibrationState.ts'

const route:any={lab_profile_id:'lab',topology_id:'topo',operating_mode:'mimo_ota',chain_id:'route',ce_port:'B1',route_digest:'a',configuration_digest:'b',node_ids:['ce','probe'],connection_ids:['route'],nodes:[{id:'ce',type:'ce_port',params:{ce_port:'B1'}},{id:'probe',type:'probe',params:{}}],connections:[{id:'route',source:'ce',target:'probe'}],calibration_nodes:[],calibration_connections:[]}
const scope:any={labId:'lab',topologyId:'topo',mode:'mimo_ota',dirty:false,graph:{nodes:route.nodes,connections:route.connections,operating_modes:[{id:'mimo_ota',active_connections:['route']}]}}
const fields={frequency:'3500',power:'-30',antenna:'模拟SGH V 静区中心',cable:'2',cableSource:'旧手填声明',samples:'5',fixed:true,safe:true}
test('显式模型模式不沿用手填线损；普通请求保持原值',()=>{
 const model=buildRouteAcquisitionRequest(scope,route,fields,undefined,true)
 assert.equal(model.mock_model,'full_route_v1')
 assert.equal(model.receive_cable_loss_db,null)
 assert.equal(model.receive_cable_source,null)
 assert.equal(model.mock_input,undefined)
 assert.equal(buildRouteAcquisitionRequest(scope,route,fields).receive_cable_loss_db,2)
 assert.throws(()=>buildRouteAcquisitionRequest(scope,route,fields,{samples:Array(5).fill({source_before_dbm:-30,received_dbm:-40,source_after_dbm:-30})},true))
})
test('模型批次无需伪造线损或样本；参考位置及普通批次限制保留',()=>{
 const refs=[{chainId:'route',frequency:3500,antenna:fields.antenna,cable:'',cableSource:''}]
 const value=buildBatchRequest(scope,[route],['route'],[3500],refs,fields,undefined,true)
 assert.equal(value.mock_model,'full_route_v1');assert.equal(value.mock_inputs,undefined)
 assert.equal(value.references[0].receive_cable_loss_db,null)
 assert.throws(()=>buildBatchRequest(scope,[route],['route'],[3500],refs,fields))
 assert.throws(()=>buildBatchRequest(scope,[route],['route'],[3500],[{...refs[0],antenna:''}],fields,undefined,true))
})

import {exportMockCalibrationCsv} from '../src/features/TopologyEditor/mockCalibrationCsv.ts'
const cable={run_id:'cable-record',lab_profile_id:'lab',cable_node_id:'rx',frequency_mhz:3500,input_reference_plane:'rx:in',output_reference_plane:'rx:out',source_power_dbm:-20,received_power_dbm:-20.2,loss_db:.2,formula:'L_RX = P_SOURCE - P_RX',simulated:true,method:'synthetic_receive_cable_v1'}
const modelRecord:any={run_id:'run',lab_profile_id:'lab',status:'simulated',result:{run_id:'run',lab_profile_id:'lab',status:'simulated',formal_eligible:false,simulation_input_source:'model_synthetic',request:{mock_model:'full_route_v1',chain_id:'route',frequency_mhz:3500,receive_cable_loss_db:null,receive_cable_source:null},receive_cable_calibration:cable,samples:[{source_before_dbm:-30,source_after_dbm:-30,received_dbm:-56.2,host_time:'2026-11-08T00:00:00Z'}],net_loss_db:26,sample_std_db:0}}
test('模型CSV保留关联线缆观测及公式，拒绝跨实验室或跨频点记录',()=>{
 const csv=exportMockCalibrationCsv([modelRecord])
 assert.match(csv,/receive_cable_record_id/);assert.match(csv,/cable-record/)
 assert.match(csv,/model_synthetic/);assert.match(csv,/rx:in/);assert.match(csv,/L_RX = P_SOURCE - P_RX/)
 for(const replacement of [null,{...cable,lab_profile_id:'other'},{...cable,frequency_mhz:2595},{...cable,simulated:false}]){
  assert.throws(()=>exportMockCalibrationCsv([{...modelRecord,result:{...modelRecord.result,receive_cable_calibration:replacement}}]))
 }
})

import {fixedRouteDisplay} from '../src/features/LabWorkspace/fixedRouteDisplay.ts'
test('模型运行、失败与取消在来源尚未生成时也不显示为实测',()=>{
 for(const status of ['running','failed','cancelled']){
  const shown=fixedRouteDisplay({status,result:{status,request:{mock_model:'full_route_v1'}}} as any)
  assert.match(shown.label,/模拟演练/)
  assert.equal(shown.cleanup,'模拟模式，未操作真实仪器')
 }
})

import {simulationModelValid} from '../src/features/TopologyEditor/SimulationModelFields.tsx'
test('模拟参数明确区分未知与零，并拒绝负损耗及多余字段',()=>{
 assert.equal(simulationModelValid(undefined,'loss_db'),true)
 assert.equal(simulationModelValid({frequency_mhz:3500,loss_db:0},'loss_db'),true)
 for(const value of [null,{frequency_mhz:3500,loss_db:''},{frequency_mhz:3500,loss_db:-1},{frequency_mhz:0,loss_db:1},{frequency_mhz:3500,loss_db:1,extra:2}])assert.equal(simulationModelValid(value,'loss_db'),false)
 assert.equal(simulationModelValid({frequency_mhz:3500,gain_db:-3},'gain_db'),true)
})
