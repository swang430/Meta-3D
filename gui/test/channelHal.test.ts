import { ChannelEmulatorHAL } from '../src/services/channels/ChannelEmulatorHAL'
import { MockChannelDriver } from '../src/services/channels/mockDriver'
import type { IChannelEmulatorDriver } from '../src/types/channel'

describe('ChannelEmulatorHAL with MockChannelDriver', () => {
  let driver: IChannelEmulatorDriver

  beforeEach(() => {
    driver = new MockChannelDriver()
  })

  it('connects, loads scenario, starts and queries status', async () => {
    await expect(driver.connect('mock://localhost')).resolves.toEqual({ ok: true })
    await expect(
      driver.loadScenario({ id: 'ctia-0140', name: 'CTIA 01.40', source: 'preset', description: 'CTIA OTA' }),
    ).resolves.toEqual({ ok: true })
    await expect(
      driver.configureModel({ standard: '3gpp', profile: 'CDL-D', bandwidthMHz: 100, centerFrequencyMHz: 3500 }),
    ).resolves.toEqual({ ok: true })
    await expect(driver.start()).resolves.toEqual({ ok: true })
    const status = await driver.queryStatus()
    expect(status.ok).toBe(true)
    expect(status.data?.state).toBe('running')
    await driver.stop()
    await driver.disconnect()
  })
})
