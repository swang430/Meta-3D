import {strict as assert} from 'node:assert';
import {test} from 'node:test';
import {buildConversionRequest,conversionContextKey,clearConversionSession} from '../src/features/TopologyEditor/legacyConversionState';
test('未提交键不补null，显式清损耗保留null和0',()=>{
  const request=buildConversionRequest([],[{connection_id:'wire',cable_loss_db:null,source_pin:undefined}]);
  assert.deepEqual(request.connections,[{connection_id:'wire',cable_loss_db:null}]);
  assert.equal('source_pin' in request.connections![0],false);
  assert.deepEqual(buildConversionRequest([],[{connection_id:'wire',source_pin:'OUT',loss_owner_connection_id:undefined}]).connections,
    [{connection_id:'wire',source_pin:'OUT'}]);
  assert.deepEqual(buildConversionRequest([],[{connection_id:'zero',cable_loss_db:0}]).connections,[{connection_id:'zero',cable_loss_db:0}]);
});
test('上下文含Lab和图，取消不改原草稿',()=>{
  assert.notEqual(conversionContextKey('a','g'),conversionContextKey('b','g'));
  assert.notEqual(conversionContextKey('a','g'),conversionContextKey('a','h'));
  const draft={nodes:[{id:'old',params:{opaque:1}}]};const before=structuredClone(draft);
  const cleared=clearConversionSession(draft);assert.equal(cleared.draft,draft);assert.deepEqual(draft,before);assert.equal(cleared.preview,null);
});
test('owner显式撤销要求确认，非法null拒绝',()=>{
  assert.throws(()=>buildConversionRequest([],[{connection_id:'alias',loss_owner_connection_id:null}]));
  assert.deepEqual(buildConversionRequest([],[{connection_id:'alias',loss_owner_connection_id:null,same_physical_cable_confirmed:true}]).connections,
    [{connection_id:'alias',loss_owner_connection_id:null,same_physical_cable_confirmed:true}]);
  assert.throws(()=>buildConversionRequest([{node_id:'n',ports:null as any}],[]));
});
