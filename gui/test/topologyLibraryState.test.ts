import test from 'node:test';
import assert from 'node:assert/strict';
import {chooseTopology, preferenceKey, requestMatches, canLeaveTopology, loadTopologyLibrary} from '../src/features/TopologyEditor/topologyLibraryState.ts';

const items = [
  {id:'b',name:'重复名',created_at:'2026-01-02',is_default:false},
  {id:'a',name:'重复名',created_at:'2026-01-02',is_default:false},
  {id:'old',name:'旧图',created_at:'2026-01-01',is_default:false},
];
test('合法偏好按ID选择，不以重复名称识别图',()=>assert.equal(chooseTopology(items,'b'),'b'));
test('不存在偏好按创建时间及ID稳定回退，不改列表',()=>{
  assert.equal(chooseTopology(items,'missing'),'a');
  assert.equal(items[0].id,'b');
});
test('唯一历史default优先；多个历史default不取任意第一条',()=>{
  assert.equal(chooseTopology(items.map(x=>({...x,is_default:x.id==='old'})),null),'old');
  assert.equal(chooseTopology(items.map(x=>({...x,is_default:true})),null),'a');
});
test('空列表无选择，偏好按Lab/category隔离',()=>{
  assert.equal(chooseTopology([],'a'),null);
  assert.notEqual(preferenceKey('lab-a','switch'),preferenceKey('lab-b','switch'));
  assert.notEqual(preferenceKey('lab-a','switch'),preferenceKey('lab-a','other'));
});
test('dirty和busy任一为真禁止离开，只有全空闲允许',()=>{
  for(const [dirty,busy,want] of [[false,false,true],[true,false,false],[false,true,false],[true,true,false]])
    assert.equal(canLeaveTopology(dirty,busy),want);
});
test('迟到代数与跨scope均拒绝，当前令牌允许',()=>{
  assert.equal(requestMatches({scope:'a',generation:1},{scope:'a',generation:2}),false);
  assert.equal(requestMatches({scope:'a',generation:2},{scope:'b',generation:2}),false);
  assert.equal(requestMatches({scope:'a',generation:2},{scope:'a',generation:2}),true);
});
test('取完整分页后才返回库；重复页和空进展报错不循环',async()=>{
  const calls:number[]=[];
  const result=await loadTopologyLibrary(async(skip)=>{calls.push(skip);return {items:skip===0?items.slice(0,2):items.slice(2),total:3}});
  assert.deepEqual(result.map(x=>x.id),['b','a','old']);assert.deepEqual(calls,[0,2]);
  await assert.rejects(loadTopologyLibrary(async()=>({items:[],total:1})),/分页/);
  await assert.rejects(loadTopologyLibrary(async()=>({items:[items[0]],total:2})),/分页/);
});
