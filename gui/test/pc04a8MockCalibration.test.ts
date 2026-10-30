import assert from 'node:assert/strict'
import test from 'node:test'
import {parseMockCalibrationCsv,exportMockCalibrationCsv} from '../src/features/TopologyEditor/mockCalibrationCsv.ts'
import {fixedRouteDisplay} from '../src/features/LabWorkspace/fixedRouteDisplay.ts'
import {buildRouteAcquisitionRequest,buildBatchRequest} from '../src/features/TopologyEditor/routeCalibrationState.ts'
const header='chain_id,frequency_mhz,sample_index,source_before_dbm,received_dbm,source_after_dbm,receive_cable_loss_db,receive_cable_source,expected_loss_db'
const csv=[header,'route-a,2595,1,-20,-50,-18,2,"synthetic, cable",29','route-a,2595,2,-22,-52,-20,2,"synthetic, cable",29'].join('\n')
const selection={chainIds:['route-a'],frequenciesMhz:[2595],sampleCount:2,referenceAntennas:{'route-a':'synthetic REF at centre V'}}
test('按通路频率及1起始样本编号组合，保留引号来源',()=>{
 const v=parseMockCalibrationCsv(csv,selection)
 assert.equal(v.mockInputs[0].samples.length,2);assert.equal(v.references[0].receive_cable_source,'synthetic, cable');assert.equal(v.mockInputs[0].expected_loss_db,29)
})
test('重复缺组额外组空数字公共值冲突不发请求',()=>{
 for(const bad of [csv+'\n'+csv.split('\n')[1],csv.split('\n').slice(0,2).join('\n'),csv.replace('route-a,2595,2','route-b,2595,2'),csv.replace('1,-20','1,'),csv.replace('2,-22,-52,-20,2','2,-22,-52,-20,3')])assert.throws(()=>parseMockCalibrationCsv(bad,selection))
})
test('BOM CRLF 引号转义空行以及空线损与已知零严格区分',()=>{
 assert.equal(parseMockCalibrationCsv('\uFEFF'+csv.replaceAll('\n','\r\n')+'\r\n',selection).mockInputs.length,1)
 assert.equal(parseMockCalibrationCsv(csv.replaceAll('"synthetic, cable"','"a""b"'),selection).references[0].receive_cable_source,'a"b')
 assert.equal(parseMockCalibrationCsv(csv.replaceAll(',2,"synthetic, cable"',',,"synthetic, cable"'),selection).references[0].receive_cable_loss_db,null)
 assert.equal(parseMockCalibrationCsv(csv.replaceAll(',2,"synthetic, cable"',',0,"synthetic, cable"'),selection).references[0].receive_cable_loss_db,0)
 for(const bad of [csv+'"',csv.replace('sample_index','frequency_mhz'),csv.replace('sample_index','unknown'),csv.replace(',1,-20',',1.0,-20'),csv.replace(',-50,',',Infinity,')])assert.throws(()=>parseMockCalibrationCsv(bad,selection))
})
const record=(expected=29)=>({run_id:'run',lab_profile_id:'lab',status:'simulated',result:{run_id:'run',lab_profile_id:'lab',status:'simulated',formal_eligible:false,simulation_input_source:'operator_supplied_synthetic',request:{chain_id:'=route',frequency_mhz:2595,receive_cable_loss_db:0,receive_cable_source:' @formula',mock_input:{samples:[{source_before_dbm:-20,received_dbm:-50,source_after_dbm:-18},{source_before_dbm:-22,received_dbm:-52,source_after_dbm:-20}],expected_loss_db:expected}},samples:[{index:1,source_before_dbm:-20,received_dbm:-50,source_after_dbm:-18,host_time:'2026-10-30T00:00:00Z'},{index:2,source_before_dbm:-22,received_dbm:-52,source_after_dbm:-20,host_time:'2026-10-30T00:00:01Z'}],net_loss_db:-2,sample_std_db:0,configuration:{binding:{execution_mode:'simulated'}}}}) as never
test('服务器模拟数值独立呈现，篡改状态不能洗为实测',()=>{
 const v=fixedRouteDisplay(record());assert.equal(v.loss,'未计算');assert.equal(v.mock?.netLoss,-2);assert.equal(v.mock?.expectedDelta,-31)
 assert.equal(fixedRouteDisplay(record(10)).mock?.netLoss,-2)
 assert.equal(fixedRouteDisplay({...record(),status:'completed'} as never).source,'无实测读数')
 assert.equal(fixedRouteDisplay({status:'simulated',result:{request:{},configuration:{}}} as never).mock,undefined)
})
test('CSV逐样本保零空值，文本防公式且拒绝旧preview及跨run结果',()=>{
 const out=exportMockCalibrationCsv([record()]);assert.equal(out.split('\r\n').length,3)
 assert.match(out,/'=route/);assert.match(out,/' @formula/);assert.match(out,/,-2,0,-31,operator_supplied_synthetic,false,/);assert.match(out,/simulation_processing_time/)
 assert.throws(()=>exportMockCalibrationCsv([{status:'simulated',result:{request:{}}} as never]))
 const crossed={...record(),run_id:'other'};assert.throws(()=>exportMockCalibrationCsv([crossed as never]))
 assert.throws(()=>exportMockCalibrationCsv([{...record(),lab_profile_id:'other'} as never]))
})
test('可选线损来源保持null；多频独立组不混样本，样本按编号排序',()=>{
 const text=csv.replaceAll(',2,"synthetic, cable",29',',,,')
 const value=parseMockCalibrationCsv(text,selection)
 assert.equal(value.references[0].receive_cable_loss_db,null);assert.equal(value.references[0].receive_cable_source,null)
 const two=csv+'\n'+csv.split('\n').slice(1).reverse().join('\n').replaceAll(',2595,',',3500,').replaceAll(',29',',12')
 const parsed=parseMockCalibrationCsv(two,{...selection,frequenciesMhz:[2595,3500]})
 assert.equal(parsed.mockInputs[1].frequency_mhz,3500);assert.equal(parsed.mockInputs[1].expected_loss_db,12)
 assert.equal(parsed.mockInputs[1].samples[0].source_before_dbm,-20)
})
test('单路显式输入及批矩阵沿已存路径构造；旧模式不附模拟字段，未知矩阵拒绝',()=>{
 const route={lab_profile_id:'lab',topology_id:'topo',operating_mode:'mimo_ota',chain_id:'route-a',ce_port:'B1.1',route_digest:'a',configuration_digest:'b',node_ids:['ce','probe'],connection_ids:['wire'],nodes:[{id:'ce',type:'ce_port',params:{ce_port:'B1.1'}},{id:'probe',type:'probe',params:{}}],connections:[{id:'wire',source:'ce',target:'probe'}],calibration_nodes:[],calibration_connections:[]}
 const scope={labId:'lab',topologyId:'topo',mode:'mimo_ota',dirty:false,graph:{nodes:route.nodes,connections:route.connections,operating_modes:[{id:'mimo_ota',active_connections:['wire']}]}}
 const fields={frequency:'2595',power:'-30',antenna:'REF V centre',cable:'',cableSource:'',samples:'2',fixed:true,safe:true}
 const input=parseMockCalibrationCsv(csv,selection).mockInputs[0]
 assert.equal('mock_input' in buildRouteAcquisitionRequest(scope as never,route as never,fields),false)
 assert.equal(buildRouteAcquisitionRequest(scope as never,route as never,fields,input).mock_input?.samples[0].received_dbm,-50)
 const refs=[{chainId:'route-a',frequency:2595,antenna:'REF V centre',cable:'',cableSource:''}]
 assert.throws(()=>buildBatchRequest(scope as never,[route] as never,['route-a'],[2595],refs,fields))
 const body=buildBatchRequest(scope as never,[route] as never,['route-a'],[2595],refs,fields,[input])
 assert.equal(body.references[0].receive_cable_loss_db,null);assert.equal(body.references[0].receive_cable_source,null)
 assert.equal(body.mock_inputs?.[0].expected_loss_db,29)
 assert.throws(()=>buildBatchRequest(scope as never,[route] as never,['route-a'],[2595],refs,fields,[{...input,chain_id:'unknown'}]))
 assert.throws(()=>buildRouteAcquisitionRequest({...scope,dirty:true} as never,route as never,fields,input))
 assert.throws(()=>buildRouteAcquisitionRequest(scope as never,route as never,fields,{samples:input.samples.slice(1)}))
})
