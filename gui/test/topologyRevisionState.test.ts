import assert from 'node:assert/strict';
import test from 'node:test';
import {canRestore,ownsRevisionRequest,ownsLibraryInspection,ownsSavedInspection,revisionFailure} from '../src/features/TopologyEditor/topologyRevisionState.ts';

test('恢复与dirty、全部写、采集未知互斥',()=>{
  const ready={dirty:false,writing:false,collectionBusy:false,unknownWrite:false};
  assert.equal(canRestore(ready),true);
  for(const key of Object.keys(ready)) assert.equal(canRestore({...ready,[key]:true}),false);
});
test('scope图ID代数有一项变化就丢弃迟到响应',()=>{
  const current={scope:'lab/category',topologyId:'t',generation:2};
  assert.equal(ownsRevisionRequest(current,{...current}),true);
  assert.equal(ownsRevisionRequest(current,{...current,generation:1}),false);
  assert.equal(ownsRevisionRequest(current,{...current,topologyId:'other'}),false);
  assert.equal(ownsRevisionRequest(current,{...current,scope:'lab2/category'}),false);
});
test('409和超时均不自动重试',()=>{
  assert.equal(revisionFailure(409).kind,'conflict');
  assert.equal(revisionFailure(undefined).kind,'unknown');
  assert.equal(revisionFailure(503).kind,'unknown');
  assert.equal(revisionFailure(422).kind,'rejected');
});
test('库核查在Flow写开始及A→B→A后，迟到读取与已展示结果均不可采用',()=>{
  const captured={scope:'lab/category',topologyId:'A',generation:2,inspectionGeneration:5};
  assert.equal(ownsLibraryInspection({...captured},captured),true);
  // Flow保存/恢复开始推进已有库核查代数；scope、图ID与库请求代数都仍相同。
  const afterWrite={...captured,inspectionGeneration:6};
  assert.equal(ownsLibraryInspection(afterWrite,captured),false,'迟到读取应丢弃');
  assert.equal(ownsLibraryInspection(afterWrite,captured),false,'已展示结果最终采用也应拒绝');
  // 即便最终回到A，期间选图两次也不能让旧A核查重新拥有上下文。
  const returnedToA={...captured,inspectionGeneration:7};
  assert.equal(ownsLibraryInspection(returnedToA,captured),false);
});
test('Flow核查在同图库写开始或保存基线改变后，迟到读取和最终采用均拒绝旧身份',()=>{
  const captured={scope:'lab/category',topologyId:'A',generation:2,inspectionGeneration:5,savedRevision:3};
  assert.equal(ownsSavedInspection(captured,{...captured}),true);
  assert.equal(ownsSavedInspection({...captured,inspectionGeneration:6},captured),false,'库写开始即失效');
  assert.equal(ownsSavedInspection({...captured,savedRevision:4},captured),false,'同图新修订不能采用旧核查');
});
