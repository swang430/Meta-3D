import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {SwitchTopology} from '../src/api/switchTopologyService.ts';

import * as layout from '../src/features/TopologyEditor/topologyLayout.ts';
const fixture=():SwitchTopology=>({revision:4,name:'共享图',switch_category_id:'switch',is_active:false,is_default:false,
  nodes:[{id:'f64',label:'F64',type:'channel_emulator',params:{ports:Array.from({length:32},(_,i)=>`B${i+1}`)}}],
  connections:[],operating_modes:[{id:'m',name:'测试',active_connections:[]},{id:'calibration',name:'校准',active_connections:[]}]});
function branches(){const graph=fixture();for(let i=32;i>=1;i--){
  graph.nodes.push({id:`pa${i}`,label:`PA${i}`,type:'amplifier',position:{x:1,y:2},params:{ports:['in','out'],opaque:{keep:true}}},
    {id:`probe${i}`,label:`Probe${i}`,type:'probe',params:{ports:['in']}});
  graph.connections.push({id:`in${i}`,source:'f64',source_pin:`B${i}`,target:`pa${i}`,target_pin:'in',cable_loss_db:null},
    {id:`out${i}`,source:`pa${i}`,source_pin:'out',target:`probe${i}`,target_pin:'in',cable_loss_db:0});
}return graph;}
test('32路按实际端口自然顺序分层，仅位置改变且输入不变',()=>{
  assert.equal(typeof layout.layoutTopology,'function','缺少主动排版能力');
  const graph=branches(),before=structuredClone(graph),next=layout.layoutTopology(graph);
  assert.deepEqual(graph,before);
  assert.deepEqual({...next,nodes:next.nodes.map(({position,...node}:any)=>node)},
    {...before,nodes:before.nodes.map(({position,...node})=>node)});
  const byId=new Map(next.nodes.map((node:any)=>[node.id,node])) as Map<string,any>;
  for(let i=1;i<=32;i++){
    assert.ok(byId.get('f64').position.x<byId.get(`pa${i}`).position.x);
    assert.ok(byId.get(`pa${i}`).position.x<byId.get(`probe${i}`).position.x);
    if(i>1)assert.ok(byId.get(`pa${i}`).position.y-byId.get(`pa${i-1}`).position.y>=160);
  }
  const reversed={...graph,nodes:[...graph.nodes].reverse(),connections:[...graph.connections].reverse()};
  const positions=(value:any)=>Object.fromEntries(value.nodes.map((n:any)=>[n.id,n.position]));
  assert.deepEqual(positions(layout.layoutTopology(reversed)),positions(next));
});
test('实测尺寸、回路及孤立点都有不重叠的有限位置',()=>{
  assert.equal(typeof layout.layoutTopology,'function');
  const graph=fixture();graph.nodes.push(...['a','b','isolated'].map(id=>({id,label:id,type:'pad',params:{}})));
  graph.connections=[{id:'ab',source:'a',target:'b'},{id:'ba',source:'b',target:'a'}];
  const next=layout.layoutTopology(graph,new Map([['a',{width:800,height:900}]]));
  for(const node of next.nodes){assert.ok(Number.isFinite(node.position.x));assert.ok(Number.isFinite(node.position.y));}
  const a=next.nodes.find((n:any)=>n.id==='a'),b=next.nodes.find((n:any)=>n.id==='b');
  assert.ok(Math.abs(a.position.y-b.position.y)>=980);
});
test('其他模式同层器件不能让PA与下一层对应Probe上下错开',()=>{
  const graph=branches();
  graph.nodes.push(...['a','aa',...Array.from({length:48},(_,i)=>`v${i}`)].map(id=>({id,label:id,type:'pad',params:{},position:{x:0,y:0}})));
  graph.connections.push({id:'a-aa',source:'a',target:'aa'},...Array.from({length:48},(_,i)=>({id:`aa-v${i}`,source:'aa',target:`v${i}`})));
  const next=layout.layoutTopology(graph),get=(id:string)=>next.nodes.find(node=>node.id===id)!;
  for(let i=1;i<=32;i++)assert.ok(Math.abs(get(`pa${i}`).position.y-get(`probe${i}`).position.y)<100,'下游跟随上游行，不能独立从顶端堆叠');
});
test('撤回仅恢复原位置，保留后续属性/连线编辑及新增节点，不复活删除节点',()=>{
  assert.equal(typeof layout.captureLayoutUndo,'function');
  const graph=branches(),undo=layout.captureLayoutUndo(graph,'lab'),next=layout.layoutTopology(graph);
  next.nodes[1]={...next.nodes[1],label:'后来编辑',params:{new:42}};
  next.connections[0]={...next.connections[0],cable_loss_db:3};
  next.nodes=next.nodes.filter((n:any)=>n.id!=='pa31');
  next.nodes.push({id:'new',type:'pad',label:'新增',params:{},position:{x:777,y:888}});
  const restored=layout.restoreLayoutPositions(next,undo,'lab');
  assert.equal(restored.nodes[1].label,'后来编辑');assert.deepEqual(restored.nodes[1].params,{new:42});
  assert.deepEqual(restored.nodes[1].position,{x:1,y:2});
  assert.equal(Object.hasOwn(restored.nodes[0],'position'),false);
  assert.equal(restored.connections[0].cable_loss_db,3);
  assert.equal(restored.nodes.some((n:any)=>n.id==='pa31'),false);
  assert.deepEqual(restored.nodes.at(-1).position,{x:777,y:888});
  assert.equal(layout.restoreLayoutPositions({...next,revision:5},undo,'lab').nodes,next.nodes);
  assert.equal(layout.restoreLayoutPositions(next,undo,'other').nodes,next.nodes);
});
