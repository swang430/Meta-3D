import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import MockAdapter from 'axios-mock-adapter'
import apiClient from '../src/api/client.ts'
import { syncCurrentInstrumentBinding } from '../src/api/labProfileService.ts'

test('sync sends the captured server saved digest to the captured Lab only', async () => {
  const mock = new MockAdapter(apiClient)
  const token = 'a'.repeat(64)
  mock.onPut('/lab-profiles/confirmed-lab/instrument-bindings/vna/sync-current').reply(config => {
    assert.deepEqual(JSON.parse(config.data), { expected_saved_configuration_digest: token })
    return [200, { lab_profile_id: 'confirmed-lab' }]
  })
  try {
    assert.deepEqual(await syncCurrentInstrumentBinding('confirmed-lab', 'vna', token), { lab_profile_id: 'confirmed-lab' })
  } finally { mock.restore() }
})

test('retry settlement refreshes every drawer HAL consumer on success and failure', () => {
  const source = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const retry = source.split('const activationRetryMutation = useMutation({')[1].split('type SyncConfirmation')[0]
  assert.match(retry, /onSettled:/)
  const settled = retry.split('onSettled:')[1]
  for (const key of ['catalog', 'hal', 'channelModels', 'topologyProfiles']) {
    assert.ok(settled.includes(`'${key}'`), `missing HAL consumer ${key}`)
  }
  assert.match(settled, /categoryKey/)
})
