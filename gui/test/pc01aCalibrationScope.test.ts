import assert from 'node:assert/strict'
import test from 'node:test'
import MockAdapter from 'axios-mock-adapter'
import apiClient from '../src/api/client.ts'
import { fetchCalibrationScope, compareCalibrationScope } from '../src/api/labProfileService.ts'

test('配置盘点与只读比较固定到显式实验室，快照原样发送给服务器', async () => {
  const mock = new MockAdapter(apiClient)
  const baseline = { digest: 'a'.repeat(64), payload: { lab_profile_id: 'lab-a' } } as any
  mock.onGet('/lab-profiles/lab-a/calibration-scope').reply(200, baseline)
  mock.onPost('/lab-profiles/lab-a/calibration-scope/compare').reply(config => {
    assert.deepEqual(JSON.parse(config.data), { baseline })
    return [200, { current: baseline, changed_sections: ['chains'], requires_review: true }]
  })
  try {
    assert.deepEqual(await fetchCalibrationScope('lab-a'), baseline)
    assert.deepEqual((await compareCalibrationScope('lab-a', baseline)).changed_sections, ['chains'])
  } finally { mock.restore() }
})
