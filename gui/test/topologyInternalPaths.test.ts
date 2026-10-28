import assert from 'node:assert/strict';
import {test} from 'node:test';
import type {SwitchTopology,TopologyNode} from '../src/api/switchTopologyService';
import {validateNodeInternalPaths,validateDraftInternalPaths} from '../src/features/TopologyEditor/internalPathHelpers';
import {updateDraftNode,addDraftConnection} from '../src/features/TopologyEditor/topologyDraft';
import {routeGraphMatchesSaved} from '../src/features/TopologyEditor/routeCalibrationState';
import React from 'react';
import {InternalPathFields} from '../src/features/TopologyEditor/InternalPathFields';
(globalThis as any).React=React;

const node=(params:Record<string,any>={},type='amplifier'):TopologyNode=>({id:'pa',type,label:'PA',position:{x:0,y:0},params:{ports:['IN','OUT'],port_directions:{IN:'input',OUT:'output'},...params}});
const graph=():SwitchTopology=>({revision:0,id:'graph',switch_category_id:'switch',name:'图',is_active:true,is_default:true,nodes:[
  {id:'ce',type:'ce_port',label:'B1.1',position:{x:0,y:0},params:{ports:['OUT']}},
  node({internal_paths:[{from_port:'IN',to_port:'OUT'}]}),
  {id:'probe',type:'probe',label:'探头',position:{x:0,y:0},params:{ports:['IN'],rf_path_selection:{connection_ids:['a','b'],switch_mappings:[]}}}],
  connections:[{id:'a',source:'ce',source_pin:'OUT',target:'pa',target_pin:'IN'},{id:'b',source:'pa',source_pin:'OUT',target:'probe',target_pin:'IN'}],
  operating_modes:[{id:'normal',name:'正常',active_connections:[]},{id:'hidden',name:'隐藏模式',active_connections:['a','b']}]});

test('删除内部通路使用的端口会失败且不改输入',()=>{
  const value=node({ports:['OUT'],internal_paths:[{from_port:'IN',to_port:'OUT'}]}),before=structuredClone(value);
  assert.throws(()=>validateNodeInternalPaths(value),/pa.*IN/);assert.deepEqual(value,before);
});
test('只声明IN→OUT不会产生反向，缺键与空列表保留不同意图',()=>{
  const old=node(),empty=node({internal_paths:[]}),declared=node({internal_paths:[{from_port:'IN',to_port:'OUT'}]});
  for(const value of [old,empty,declared])validateNodeInternalPaths(value);
  assert.equal(Object.hasOwn(old.params,'internal_paths'),false);assert.deepEqual(empty.params.internal_paths,[]);
  assert.deepEqual(declared.params.internal_paths,[{from_port:'IN',to_port:'OUT'}]);
  assert.throws(()=>validateNodeInternalPaths(node({internal_paths:[{from_port:'OUT',to_port:'IN'}]})),/方向/);
});
test('unknown可保存草稿，BSE原port_roles优先且冲突拒绝',()=>{
  validateNodeInternalPaths(node({port_directions:{},internal_paths:[{from_port:'IN',to_port:'OUT'}]}));
  assert.throws(()=>validateNodeInternalPaths(node({ports:['RF','UL'],port_roles:{RF:'dl',UL:'ul'},port_directions:{},internal_paths:[{from_port:'RF',to_port:'UL'}]},'bse_port')),/类型|方向/);
});
test('非法形态、PA反向并存、负载中转被拒绝，不猜合路器pair',()=>{
  for(const internal_paths of [null,[{from_port:'IN',to_port:'IN'}],[{from_port:'IN',to_port:'OUT',relay:1}],[{from_port:'IN',to_port:'OUT'},{from_port:'IN',to_port:'OUT'}]])
    assert.throws(()=>validateNodeInternalPaths(node({internal_paths})));
  assert.throws(()=>validateNodeInternalPaths(node({port_directions:{},internal_paths:[{from_port:'IN',to_port:'OUT'},{from_port:'OUT',to_port:'IN'}]})));
  assert.throws(()=>validateNodeInternalPaths(node({internal_paths:[{from_port:'IN',to_port:'OUT'}]},'termination')));
  const combiner=node({ports:['A','B','C'],port_directions:{},internal_paths:[{from_port:'A',to_port:'C'}]},'combiner');
  validateNodeInternalPaths(combiner);assert.deepEqual(combiner.params.internal_paths,[{from_port:'A',to_port:'C'}]);
});
test('清空所选pair列出隐藏模式探头与连线引用且原图不变',()=>{
  const old=graph(),before=structuredClone(old),changed=node({internal_paths:[]});
  assert.throws(()=>updateDraftNode(old,changed),/probe.*a\/b.*pa.*IN.*OUT/);
  assert.deepEqual(old,before);
});
test('无关编辑不物化缺键，删除声明不能恢复旧推断',()=>{
  const old=graph();delete old.nodes[1].params.internal_paths;
  const renamed={...old.nodes[1],label:'改名'};
  const next=updateDraftNode(old,renamed);assert.equal(Object.hasOwn(next.nodes[1].params,'internal_paths'),false);
  const declared=graph(),removed=structuredClone(declared);delete removed.nodes[1].params.internal_paths;
  assert.throws(()=>validateDraftInternalPaths(removed,declared),/probe.*pa/);
});
test('未成完整路径草稿不被当作运行路径，接线仍共享内部声明校验',()=>{
  const old=graph();old.nodes[2].params={ports:['IN']};old.connections=[];
  const next=addDraftConnection(old,{id:'a',source:'ce',source_pin:'OUT',target:'pa',target_pin:'IN'},'normal');
  assert.equal(next.connections.length,1);
  const bad=structuredClone(next);bad.nodes[1].params.internal_paths=[];
  validateDraftInternalPaths(bad,next);
});
test('不相关模式新边不要求旧链补声明，模式让所选路径生效仍核对pair',()=>{
  const old=graph();delete old.nodes[1].params.internal_paths;
  old.connections=old.connections.map(edge=>({...edge,modes:['hidden']}));
  old.nodes.push({id:'x',type:'pad',label:'x',position:{x:0,y:0},params:{ports:['A','B']}});
  const next=addDraftConnection(old,{id:'unrelated',source:'x',source_pin:'A',target:'x',target_pin:'B'},'hidden');
  assert.equal(Object.hasOwn(next.nodes[1].params,'internal_paths'),false);
  const changed=structuredClone(old);changed.operating_modes[0].active_connections=['a','b'];
  assert.throws(()=>validateDraftInternalPaths(changed,old),/probe.*pa/);
  const removed=structuredClone(old);removed.operating_modes=removed.operating_modes.filter(mode=>mode.id!=='hidden');
  assert.throws(()=>validateDraftInternalPaths(removed,old),/probe.*pa/);
});
for(const segment of ['nodes','calibration_nodes'] as const)test(`服务器选择${segment}差一个pair失效，不重算摘要`,()=>{
  const current=graph(),selected:any={nodes:[],calibration_nodes:[],connections:[],calibration_connections:[],node_ids:['ce','pa','probe'],connection_ids:[],operating_mode:'normal',ce_port:'B1.1'};
  selected[segment]=structuredClone(current.nodes);
  assert.equal(routeGraphMatchesSaved(current,selected),true);
  current.nodes[1].params.internal_paths=[];
  assert.equal(routeGraphMatchesSaved(current,selected),false);
});
test('内部表单冻结时即使直接触发回调也不输出修改，恢复后仍可逐行编辑',()=>{
  const value=node({ports:['IN','ALT','OUT'],port_directions:{IN:'input',ALT:'input',OUT:'output'},internal_paths:[{from_port:'IN',to_port:'OUT'}]},'combiner');
  const changes:any[]=[],restores:string[]=[];
  const elements=(disabled:boolean)=>{
    const result:any[]=[];
    const visit=(item:any)=>{if(!React.isValidElement(item))return;const p:any=item.props;if(p.onChange||p.onClick)result.push(p);React.Children.forEach(p.children,visit)};
    visit(InternalPathFields({node:value,disabled,onChange:paths=>changes.push(paths),onRestore:()=>restores.push('restore')}));return result;
  };
  const frozen=elements(true);assert.equal(frozen.length,6);
  for(const item of frozen){assert.equal(item.disabled,true);item.onClick?.();item.onChange?.('ALT')}
  assert.deepEqual(changes,[]);assert.deepEqual(restores,[]);
  const enabled=elements(false);enabled.find(item=>item.label==='内部输入口 1').onChange('ALT');
  assert.deepEqual(changes,[[{from_port:'ALT',to_port:'OUT'}]]);
  enabled.find(item=>item.children==='恢复原内部声明').onClick();assert.deepEqual(restores,['restore']);
  assert.deepEqual(value.params.internal_paths,[{from_port:'IN',to_port:'OUT'}]);
});
