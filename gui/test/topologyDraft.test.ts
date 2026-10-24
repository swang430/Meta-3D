import { test } from 'node:test';
import assert from 'node:assert/strict';
import { addDraftNode, addDraftConnection, removeDraftNodes, removeDraftConnections, updateDraftNode } from '../src/features/TopologyEditor/topologyDraft.ts';
import type { SwitchTopology } from '../src/api/switchTopologyService.ts';
import { getNodePorts } from '../src/features/TopologyEditor/nodePortHelpers.ts';

const fixture = (): SwitchTopology => ({ name: '图', switch_category_id: 's', is_active: true, is_default: false,
  nodes: ['a','b','c'].map(id => ({id, type:'pad',label:id,position:{x:12,y:34},params:{ports:['in','out'],unknown:{keep:1}}})),
  connections: [{id:'ab',source:'a',target:'b',source_pin:'out',target_pin:'in'}, {id:'bc',source:'b',target:'c',source_pin:'out',target_pin:'in'}],
  operating_modes: [{id:'mimo_ota',name:'测试',active_connections:['ab','bc']},{id:'calibration',name:'校准',active_connections:['ab']}],
});
test('新增未连线节点在当前模式可见且保留其他草稿位置及扩展参数',()=>{
  const draft=addDraftNode(fixture(),{id:'d',type:'pad',label:'线缆',position:{x:8,y:9},params:{ports:['in','out']}},'calibration');
  assert.deepEqual(draft.nodes[3].params.visible_modes,['calibration']);
  assert.deepEqual(draft.nodes[0].position,{x:12,y:34});
  assert.deepEqual(draft.nodes[0].params.unknown,{keep:1});
});
test('校准连线仅加入当前校准模式',()=>{
  const draft=addDraftConnection(fixture(),{id:'ac',source:'a',target:'c',source_pin:'out',target_pin:'in'},'calibration');
  assert.equal(draft.connections.length,3);
  assert.deepEqual(draft.operating_modes[0].active_connections,['ab','bc']);
  assert.deepEqual(draft.operating_modes[1].active_connections,['ab','ac']);
});
test('删除节点清理关联连接及所有模式引用，无关连接保留',()=>{
  const draft=removeDraftNodes(fixture(),['a']);
  assert.deepEqual(draft.nodes.map(n=>n.id),['b','c']);
  assert.deepEqual(draft.connections.map(c=>c.id),['bc']);
  assert.deepEqual(draft.operating_modes.map(m=>m.active_connections),[['bc'],[]]);
});
test('删除连线清理所有模式引用',()=>{
  const draft=removeDraftConnections(fixture(),['ab']);
  assert.deepEqual(draft.connections.map(c=>c.id),['bc']);
  assert.deepEqual(draft.operating_modes.map(m=>m.active_connections),[['bc'],[]]);
});
test('端口删除会拒绝有连线的修改，不丢未知参数',()=>{
  assert.throws(()=>updateDraftNode(fixture(),{...fixture().nodes[0],params:{ports:['in']}}),/端口/);
  const draft=updateDraftNode(fixture(),{...fixture().nodes[0],label:'新标签',params:{...fixture().nodes[0].params,ports:['in','out','extra']}});
  assert.deepEqual(draft.nodes[0].params.unknown,{keep:1});
  assert.equal(draft.nodes[0].label,'新标签');
});
test('原节点的端口选择与原画布端点一致',()=>{
  const node=fixture().nodes[0];
  assert.deepEqual(getNodePorts({...node,type:'signal_analyzer',params:{}}),['rf_in']);
  assert.deepEqual(getNodePorts({...node,type:'probe',params:{}}),['in']);
  assert.deepEqual(getNodePorts({...node,type:'emcenter',params:{}}),['switch_in','pa_out','sw_out','pa_in']);
});
test('明确尚未声明端口时不借用默认端点冒充能力',()=>{
  assert.deepEqual(getNodePorts({...fixture().nodes[0],params:{ports:[]}}),[]);
});
test('校准器件不能连入正常测试模式',()=>{
  const draft=fixture();
  draft.nodes[0].params.connection_scope='calibration';
  assert.throws(()=>addDraftConnection(draft,{id:'ac',source:'a',target:'c',source_pin:'out',target_pin:'in'},'mimo_ota'),/校准/);
});
test('历史连接省略端口时只改标签不应被空串拦住',()=>{
  const draft=fixture();
  delete draft.connections[0].source_pin;
  const changed=updateDraftNode(draft,{...draft.nodes[0],label:'只改标签'});
  assert.equal(changed.nodes[0].label,'只改标签');
  assert.equal(changed.connections[0].source_pin,undefined);
});
test('历史端口命名不一致时只改标签不重写其端口声明',()=>{
  const draft=fixture();
  draft.nodes[1]={...draft.nodes[1],type:'probe',params:{}};
  draft.connections[0].target_pin='V';
  const changed=updateDraftNode(draft,{...draft.nodes[1],label:'历史探头新标签'},['in']);
  assert.equal(changed.nodes[1].label,'历史探头新标签');
  assert.equal(changed.nodes[1].params.ports,undefined);
  assert.equal(changed.connections[0].target_pin,'V');
});
test('明确改端口仍须检查历史全部关联连接，省略端口按既有schema默认解释',()=>{
  const draft=fixture();
  delete draft.connections[0].source_pin;
  const changed=updateDraftNode(draft,{...draft.nodes[0],label:'明确端口'},['out','extra']);
  assert.deepEqual(changed.nodes[0].params.ports,['out','extra']);
  assert.throws(()=>updateDraftNode(draft,draft.nodes[0],['in','extra']),/端口/);
});
