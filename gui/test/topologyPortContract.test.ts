import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {MantineProvider} from '@mantine/core';
import {ReactFlow} from '@xyflow/react';
import * as ports from '../src/features/TopologyEditor/nodePortHelpers.ts';
import {customNodeTypes} from '../src/features/TopologyEditor/CustomNodes.tsx';
import {addDraftConnection, updateDraftConnection, updateDraftNode} from '../src/features/TopologyEditor/topologyDraft.ts';
import type {SwitchTopology, TopologyNode} from '../src/api/switchTopologyService.ts';
import {routeGraphMatchesSaved} from '../src/features/TopologyEditor/routeCalibrationState.ts';
import {PortDeclarationFields} from '../src/features/TopologyEditor/PortDeclarationFields.tsx';
import * as edgeRendering from '../src/features/TopologyEditor/CustomEdges.tsx';
(globalThis as any).React=React;

const node=(id:string,direction?:string,type='pad'):TopologyNode=>({id,type,label:id,position:{x:0,y:0},params:{ports:['RF5'],...(direction?{port_directions:{RF5:direction}}:{})}});
const graph=():SwitchTopology=>({name:'图',switch_category_id:'s',is_active:true,is_default:false,
  nodes:[node('a','output'),node('b','input')],connections:[],operating_modes:[{id:'mimo_ota',name:'正常',active_connections:[]},{id:'calibration',name:'参考',active_connections:[]}]});
const connection={id:'ab',source:'a',source_pin:'RF5',target:'b',target_pin:'RF5'};
test('方向解析只读合法ports与显式角色，不按名字/数量字段推导',()=>{
  assert.equal(typeof ports.resolveNodePorts,'function');
  const parsed=ports.resolveNodePorts({...node('a'),params:{ports:['RF5','DL1'],inputs:32,outputs:64,port_directions:{RF5:'output'}}});
  assert.deepEqual(parsed.ports,['RF5','DL1']);assert.equal(parsed.declared,true);
  assert.deepEqual(parsed.effectiveDirections,{RF5:'output',DL1:'unknown'});
  assert.deepEqual(parsed.directionSources,{RF5:'explicit',DL1:'unknown'});
  for(const value of [undefined,null,[''],[' A'],['A','A'],[3]]) {
    const result=ports.resolveNodePorts({...node('a'),params:{ports:value,inputs:32,outputs:32}});
    assert.equal(result.declared,false);assert.deepEqual(result.ports,[]);
  }
  const bse=ports.resolveNodePorts({...node('a',undefined,'communication_tester'),params:{ports:['RF5','DL1'],port_roles:{RF5:'dl'},port_directions:{RF5:'unknown'}}});
  assert.deepEqual(bse.effectiveDirections,{RF5:'output',DL1:'unknown'});
  assert.equal(bse.directionSources.RF5,'BSE');
  assert.equal(ports.resolveNodePorts({...node('a'),params:{ports:['RF5'],port_roles:{RF5:'dl'}}}).effectiveDirections.RF5,'unknown');
});
test('端口原ID即使与JS对象原型键同名也必须保持，不改写或丢失角色',()=>{
  const parsed=ports.resolveNodePorts({...node('a'),params:{ports:['__proto__','RF1','rf1'],port_directions:JSON.parse('{"__proto__":"output","RF1":"input","rf1":"unknown"}')}});
  assert.deepEqual(parsed.effectiveDirections,JSON.parse('{"__proto__":"output","RF1":"input","rf1":"unknown"}'));
  assert.equal(parsed.directionSources.__proto__,'explicit');
});
test('全部16种方向组合在拖线与抽屉重接遵循同一规则，UL不反转端点',()=>{
  const directions=['input','output','bidirectional','unknown'];
  for(const source of directions)for(const target of directions){
    const draft=graph();draft.nodes=[node('a',source),node('b',target)];
    const edge={...connection,direction:'UL' as const};
    const allowed=source!=='input'&&target!=='output';
    if(allowed)assert.equal(addDraftConnection(draft,edge,'mimo_ota').connections.length,1);
    else assert.throws(()=>addDraftConnection(draft,edge,'mimo_ota'),/ab|RF5|方向/);
    draft.connections=[{...edge,source_pin:'old'}];
    if(allowed)assert.equal(updateDraftConnection(draft,edge).connections[0].source_pin,'RF5');
    else assert.throws(()=>updateDraftConnection(draft,edge),/ab|RF5|方向/);
  }
});
test('新连接不把旧默认端点当声明；unknown可存草稿而非双向能力',()=>{
  const draft=graph();draft.nodes[0].params={};
  assert.throws(()=>addDraftConnection(draft,{...connection,source_pin:'out'},'mimo_ota'),/声明/);
  draft.nodes[0]=node('a','unknown');assert.equal(addDraftConnection(draft,connection,'mimo_ota').connections.length,1);
});
test('显式同显示值应用写入ports；只改名称不创建声明',()=>{
  const draft=graph();draft.nodes[0]={id:'a',type:'pad',label:'a',position:{x:0,y:0},params:{unknown:{keep:1}}};
  assert.equal(updateDraftNode(draft,{...draft.nodes[0],label:'改名'}).nodes[0].params.ports,undefined);
  assert.deepEqual(updateDraftNode(draft,draft.nodes[0],['in','out']).nodes[0].params.ports,['in','out']);
  assert.deepEqual(draft.nodes[0].params,{unknown:{keep:1}});
});
test('角色变化检查全模式边与引用端口，拒绝不变更原图；返回原角色仍可应用',()=>{
  const draft=graph();draft.connections=[connection];draft.operating_modes[1].active_connections=['ab'];
  const before=structuredClone(draft);
  assert.throws(()=>updateDraftNode(draft,node('a','input')),/ab|RF5|方向/);
  assert.throws(()=>updateDraftNode(draft,{...draft.nodes[0],params:{ports:['NEW']}}),/端口/);
  assert.deepEqual(draft,before);
  assert.equal(updateDraftNode(draft,node('a','output')).nodes[0].params.port_directions.RF5,'output');
});
test('删除或改名端口一次列出全部跨模式引用边，拒绝时原草稿不变',()=>{
  const draft=graph();draft.nodes[0].params={ports:['IN','OUT']};
  draft.connections=[{id:'normal-in',source:'b',source_pin:'RF5',target:'a',target_pin:'IN'},
    {id:'reference-out',source:'a',source_pin:'OUT',target:'b',target_pin:'RF5'}];
  draft.operating_modes[0].active_connections=['normal-in'];draft.operating_modes[1].active_connections=['reference-out'];
  const before=structuredClone(draft);
  assert.throws(()=>updateDraftNode(draft,{...draft.nodes[0],params:{ports:['NEW']}}),error=>
    error instanceof Error&&error.message.includes('normal-in')&&error.message.includes('reference-out'));
  assert.deepEqual(draft,before);
});
test('BSE dl/ul与通用方向冲突拒绝，清空通用map不撤销BSE来源',()=>{
  const draft=graph();draft.nodes[0]={...node('a',undefined,'communication_tester'),params:{ports:['RF5'],port_roles:{RF5:'dl'}}};
  assert.throws(()=>updateDraftNode(draft,{...draft.nodes[0],params:{...draft.nodes[0].params,port_directions:{RF5:'bidirectional'}}}),/冲突|RF5/);
  const cleared=updateDraftNode(draft,{...draft.nodes[0],params:{...draft.nodes[0].params,port_directions:{}}});
  assert.equal(cleared.nodes[0].params.port_roles.RF5,'dl');
});
test('同ID双handle计数一次；input/output单向，unknown灰色问号非双向，BSE/空气数量不混用',()=>{
  for(const [direction,count] of [['input',1],['output',1],['bidirectional',2],['unknown',2]] as const){
    const markup=renderToStaticMarkup(React.createElement(MantineProvider,{},React.createElement(ReactFlow,{
      width:800,height:600,nodeTypes:customNodeTypes,nodes:[{id:'a',type:'pad',width:180,height:80,position:{x:100,y:100},data:{label:'a',params:node('a',direction).params}}]})));
    assert.equal([...markup.matchAll(/data-handleid="RF5"/g)].length,count);
    assert.match(markup,/已声明端口 1（未核验硬件）/);
    if(direction==='unknown')assert.match(markup,/方向未声明，非双向能力/);
    if(direction==='bidirectional')assert.match(markup,/双向声明/);
  }
  assert.equal(typeof ports.portCountLabel,'function');
  assert.equal(ports.portCountLabel(node('a','unknown','air_path')),'已声明虚拟参考端点 1');
  assert.equal(ports.portCountLabel(node('a','output','communication_tester')),'已声明逻辑端口 1；物理连接器见运行映射');
});
test('边箭头只来自明确合法端点；双向箭头还须Bi-Di；unknown或旧非法边只提示',()=>{
  assert.equal(typeof ports.edgePortPresentation,'function');
  const draft=graph();
  assert.deepEqual(ports.edgePortPresentation(draft.nodes,connection),{arrowEnd:true,arrowStart:false,warning:null});
  draft.nodes=[node('a','bidirectional'),node('b','bidirectional')];
  assert.equal(ports.edgePortPresentation(draft.nodes,{...connection,direction:'UL'}).arrowStart,false);
  assert.equal(ports.edgePortPresentation(draft.nodes,{...connection,direction:'Bi-Di'}).arrowStart,true);
  draft.nodes[0]=node('a','unknown');assert.equal(ports.edgePortPresentation(draft.nodes,connection).arrowEnd,false);
  assert.match(ports.edgePortPresentation(draft.nodes,connection).warning!,/方向未声明/);
  draft.nodes[0]=node('a','input');assert.equal(ports.edgePortPresentation(draft.nodes,connection).arrowEnd,false);
  assert.match(ports.edgePortPresentation(draft.nodes,connection).warning!,/不合法/);
});
test('普通及参考节点完整声明须匹配服务器快照，不只检查当前所连pin',()=>{
  const draft=graph();draft.nodes[0].type='ce_port';draft.nodes[0].label='B1.1';draft.connections=[connection];draft.operating_modes[0].active_connections=['ab'];
  draft.nodes.push({...node('ref'),params:{ports:['RF5'],connection_scope:'calibration'}});
  const route={node_ids:['a','b'],nodes:structuredClone(draft.nodes.slice(0,2)),calibration_nodes:structuredClone(draft.nodes.slice(2)),connections:structuredClone(draft.connections),calibration_connections:[],connection_ids:['ab'],operating_mode:'mimo_ota',ce_port:'B1.1'} as any;
  assert.equal(routeGraphMatchesSaved(draft,route),true);
  for(const id of ['a','ref'])for(const delta of [{port_directions:{}},{port_directions:{RF5:'unknown'}},{ports:['RF5','NEW']},{port_roles:{NEW:'dl'}}]){
    const changed=structuredClone(draft),target=changed.nodes.find(n=>n.id===id)!;target.params={...target.params,...delta};
    assert.equal(routeGraphMatchesSaved(changed,route),false,`${id}: ${JSON.stringify(delta)}`);
  }
  assert.equal(routeGraphMatchesSaved(draft,route),true);
});
test('BSE两角色与四通用方向组合保持唯一权威且拒绝反向和双向冲突',()=>{
  for(const role of ['dl','ul'])for(const direction of ['input','output','bidirectional','unknown']){
    const draft=graph(),base={...node('a',direction,'communication_tester'),params:{ports:['RF5'],port_roles:{RF5:role},port_directions:{RF5:direction}}};
    const valid=direction==='unknown'||direction===(role==='dl'?'output':'input');
    if(valid){assert.doesNotThrow(()=>updateDraftNode(draft,base));assert.equal(ports.resolveNodePorts(base).effectiveDirections.RF5,role==='dl'?'output':'input')}
    else assert.throws(()=>updateDraftNode(draft,base),/冲突/);
  }
});
test('端口表单新输入和每个按钮全部消费既有冻结状态，物理映射只读',()=>{
  for(const disabled of [true,false]){
    const markup=renderToStaticMarkup(React.createElement(MantineProvider,{},React.createElement(PortDeclarationFields,{
      node:{...node('a',undefined,'communication_tester'),params:{ports:['RF5'],port_roles:{RF5:'dl'},physical_port_display:{RF5:'RF3OUT'}}},
      text:'RF5',disabled,onTextChange:()=>{},onChange:()=>{},onRestore:()=>{},
    })));
    const interactive=[...markup.matchAll(/<(?:input|button)\b[^>]*>/g)].map(match=>match[0]);
    assert.ok(interactive.length>=7);
    for(const element of interactive)assert.equal(/\bdisabled=/.test(element),disabled,element);
    assert.match(markup,/RF3OUT/);assert.doesNotMatch(markup,/<input[^>]*value="RF3OUT"/);
  }
});
test('旧方向冲突边只读几何读取已有反端handle，不新增能力或改pin',()=>{
  assert.equal(typeof ports.edgeNeedsReadOnlyGeometry,'function');
  assert.equal(typeof edgeRendering.readOnlyHandlePosition,'function');
  for(const [source,target] of [['input','input'],['output','output']]){
    const draft=graph();draft.nodes=[node('a',source),node('b',target)];
    assert.equal(ports.edgeNeedsReadOnlyGeometry(draft.nodes,connection),true);
    assert.throws(()=>addDraftConnection(draft,connection,'mimo_ota'),/方向/);
  }
  assert.equal(ports.edgeNeedsReadOnlyGeometry(graph().nodes,connection),false);
  assert.equal(ports.edgeNeedsReadOnlyGeometry([],connection),false);
  assert.equal(ports.edgeNeedsReadOnlyGeometry([node('a','input'),node('b','input')],{...connection,source_pin:undefined}),false);
  const internal=(type:'source'|'target')=>({id:'a',internals:{positionAbsolute:{x:100,y:200},handleBounds:{[type]:[
    {id:'RF5',type,position:type==='source'?'right':'left',x:type==='source'?177:-3,y:37,width:6,height:6}]}}}) as any;
  assert.deepEqual(edgeRendering.readOnlyHandlePosition(internal('target'),'RF5','source'),{x:97,y:240,position:'left'});
  assert.deepEqual(edgeRendering.readOnlyHandlePosition(internal('source'),'RF5','target'),{x:283,y:240,position:'right'});
  assert.equal(edgeRendering.readOnlyHandlePosition(internal('source'),'missing','target'),null);
});
