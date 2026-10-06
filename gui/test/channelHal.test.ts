import assert from 'node:assert/strict'
import test from 'node:test'
import { ChannelEmulatorHAL } from '../src/services/channels/ChannelEmulatorHAL.ts'
import { MockChannelDriver } from '../src/services/channels/mockDriver.ts'
import type { Transport } from '../src/services/channels/transport.ts'

test('MockChannelDriver connects, loads scenario, starts and queries simulated status', async () => {
  const driver = new MockChannelDriver()
  assert.deepEqual(await driver.connect('mock://localhost'), { ok: true })
  assert.deepEqual(await driver.loadScenario({ id: 'ctia-0140', name: 'CTIA 01.40', source: 'preset', description: 'CTIA OTA' }), { ok: true })
  assert.deepEqual(await driver.configureModel({ standard: '3gpp', profile: 'CDL-D', bandwidthMHz: 100, centerFrequencyMHz: 3500 }), { ok: true })
  assert.deepEqual(await driver.start(), { ok: true })
  const status = await driver.queryStatus()
  assert.equal(status.ok, true)
  assert.equal(status.data?.state, 'running')
  assert.deepEqual(await driver.stop(), { ok: true })
  assert.deepEqual(await driver.disconnect(), { ok: true })
})

test('ChannelEmulatorHAL sends exact lifecycle payloads and preserves transport failure', async () => {
  const calls: unknown[][] = []
  const transport: Transport = {
    async connect(endpoint, options) { calls.push(['connect', endpoint, options]) },
    async disconnect() { calls.push(['disconnect']) },
    async send(command, payload) {
      calls.push([command, payload])
      return command === 'status' ? { state: 'running', operatingScenario: 'CTIA 01.40', warnings: [] } : undefined
    },
  }
  const scenario = { id: 'ctia-0140', name: 'CTIA 01.40', source: 'preset' as const, description: 'CTIA OTA' }
  const config = { standard: '3gpp' as const, profile: 'CDL-D', bandwidthMHz: 100, centerFrequencyMHz: 3500 }
  const hal = new ChannelEmulatorHAL(transport)
  assert.deepEqual(await hal.connect('test://transport', { timeout: 50 }), { ok: true })
  assert.deepEqual(await hal.loadScenario(scenario), { ok: true })
  assert.deepEqual(await hal.configureModel(config), { ok: true })
  assert.deepEqual(await hal.start(), { ok: true })
  const status = await hal.queryStatus()
  assert.equal(status.ok, true)
  assert.equal(status.data?.state, 'running')
  assert.equal(status.data?.operatingScenario, 'CTIA 01.40')
  assert.deepEqual(await hal.stop(), { ok: true })
  assert.deepEqual(await hal.disconnect(), { ok: true })
  assert.deepEqual(calls, [
    ['connect', 'test://transport', { timeout: 50 }], ['loadScenario', scenario],
    ['configureModel', config], ['start', undefined], ['status', undefined],
    ['stop', undefined], ['disconnect'],
  ])
  transport.send = async () => { throw new Error('transport refused') }
  assert.deepEqual(await hal.start(), {
    ok: false, error: { code: 'start_failed', message: 'transport refused' },
  })
})
