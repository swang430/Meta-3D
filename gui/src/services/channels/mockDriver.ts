import type {
  ChannelModelConfig,
  ChannelResult,
  ChannelScenario,
  ChannelStatistics,
  IChannelEmulatorDriver,
} from '../../types/channel'

const mockState: ChannelStatistics = {
  timestamp: new Date().toISOString(),
  state: 'idle',
  operatingScenario: 'N/A',
  temperatureC: 28,
  warnings: [],
}

export class MockChannelDriver implements IChannelEmulatorDriver {
  private status = { ...mockState }

  async connect(endpoint: string): Promise<ChannelResult> {
    if (!endpoint) return { ok: false, error: { code: 'mock_endpoint', message: 'endpoint required' } }
    this.status.state = 'connected'
    return { ok: true }
  }

  async disconnect(): Promise<ChannelResult> {
    this.status.state = 'disconnected'
    return { ok: true }
  }

  async loadScenario(scenario: ChannelScenario): Promise<ChannelResult> {
    this.status.operatingScenario = scenario.name
    this.status.state = 'loading'
    return { ok: true }
  }

  async configureModel(config: ChannelModelConfig): Promise<ChannelResult> {
    this.status.warnings = config.bandwidthMHz > 400 ? ['bandwidth exceeds recommended value'] : []
    return { ok: true }
  }

  async start(): Promise<ChannelResult> {
    this.status.state = 'running'
    return { ok: true }
  }

  async pause(): Promise<ChannelResult> {
    this.status.state = 'paused'
    return { ok: true }
  }

  async stop(): Promise<ChannelResult> {
    this.status.state = 'idle'
    return { ok: true }
  }

  async queryStatus(): Promise<ChannelResult<ChannelStatistics>> {
    return { ok: true, data: { ...this.status, timestamp: new Date().toISOString() } }
  }

  async uploadAsset(name: string): Promise<ChannelResult<{ assetId: string }>> {
    return { ok: true, data: { assetId: `mock-${name}` } }
  }
}
