import {test} from 'node:test';
import assert from 'node:assert/strict';
import MockAdapter from 'axios-mock-adapter';
import apiClient from '../src/api/client.ts';
import {switchTopologyService as service} from '../src/api/switchTopologyService.ts';

test('历史分页与恢复传输当前Lab、目标修订和独立CAS令牌；不归一化raw', async () => {
  const adapter = new MockAdapter(apiClient);
  const snapshot = {connections:[{id:'a',cable_loss_db:'2',opaque:[true,1,null]}]};
  adapter.onGet('/switch-topologies/t/revisions').reply(config => {
    assert.deepEqual(config.params,{lab_profile_id:'lab',skip:50,limit:25});
    return [200,{total:76,items:[{revision:25}]}];
  });
  adapter.onGet('/switch-topologies/t/revisions/0').reply(config => {
    assert.deepEqual(config.params,{lab_profile_id:'lab'});
    return [200,{revision:0,snapshot}];
  });
  adapter.onPost('/switch-topologies/t/restore-preview').reply(config => {
    assert.deepEqual(config.params,{lab_profile_id:'lab'});
    assert.deepEqual(JSON.parse(config.data),{revision:0,expected_revision:9});
    return [200,{current_revision:9,target_revision:0,snapshot,candidate:snapshot,differences:[],warnings:[]}];
  });
  adapter.onPost('/switch-topologies/t/restore').reply(config => {
    assert.deepEqual(config.params,{lab_profile_id:'lab'});
    assert.deepEqual(JSON.parse(config.data),{revision:0,expected_revision:9});
    return [200,{id:'t',revision:10}];
  });
  try {
    assert.equal((await service.listRevisions('t','lab',50,25)).total,76);
    assert.deepEqual((await service.getRevision('t','lab',0)).snapshot,snapshot);
    assert.deepEqual((await service.previewRestore('t','lab',0,9)).candidate,snapshot);
    assert.equal((await service.restoreTopology('t','lab',0,9)).revision,10);
  } finally { adapter.restore(); }
});
