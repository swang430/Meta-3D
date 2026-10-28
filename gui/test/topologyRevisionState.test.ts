import assert from 'node:assert/strict';
import test from 'node:test';
import {canRestore,ownsRevisionRequest,revisionFailure} from '../src/features/TopologyEditor/topologyRevisionState.ts';

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
