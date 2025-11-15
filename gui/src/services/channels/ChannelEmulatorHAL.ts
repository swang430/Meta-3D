import type {
  ChannelModelConfig,
  ChannelResult,
  ChannelScenario,
  ChannelStatistics,
  IChannelEmulatorDriver,
} from '../../types/channel'
import type { Transport } from './transport'

export class ChannelEmulatorHAL implements IChannelEmulatorDriver {
  private readonly transport: Transport

  constructor(transport: Transport) {
    this.transport = transport
  }

  async connect(endpoint: string, options?: Record<string, unknown>): Promise<ChannelResult> {
    try {
      await this.transport.connect(endpoint, options)
      return { ok: true }
    } catch (error) {
      return this.handleError(error, 'connect_failed')
    }
  }

  async disconnect(): Promise<ChannelResult> {
    try {
      await this.transport.disconnect()
      return { ok: true }
    } catch (error) {
      return this.handleError(error, 'disconnect_failed')
    }
  }

  async loadScenario(scenario: ChannelScenario): Promise<ChannelResult> {
    try {
      await this.transport.send('loadScenario', scenario)
      return { ok: true }
    } catch (error) {
      return this.handleError(error, 'scenario_failed')
    }
  }

  async configureModel(config: ChannelModelConfig): Promise<ChannelResult> {
    try {
      await this.transport.send('configureModel', config)
      return { ok: true }
    } catch (error) {
      return this.handleError(error, 'config_failed')
    }
  }

  async start(): Promise<ChannelResult> {
    try {
      await this.transport.send('start')
      return { ok: true }
    } catch (error) {
      return this.handleError(error, 'start_failed')
    }
  }

  async pause(): Promise<ChannelResult> {
    try {
      await this.transport.send('pause')
      return { ok: true }
    } catch (error) {
      return this.handleError(error, 'pause_failed')
    }
  }

  async stop(): Promise<ChannelResult> {
    try {
      await this.transport.send('stop')
      return { ok: true }
    } catch (error) {
      return this.handleError(error, 'stop_failed')
    }
  }

  async queryStatus(): Promise<ChannelResult<ChannelStatistics>> {
    try {
      const raw = (await this.transport.send('status')) as Partial<ChannelStatistics> | undefined
      return {
        ok: true,
        data: {
          timestamp: new Date().toISOString(),
          state: raw?.state ?? 'connected',
          operatingScenario: raw?.operatingScenario,
          temperatureC: raw?.temperatureC,
          warnings: raw?.warnings ?? [],
        },
      }
    } catch (error) {
      return this.handleError<ChannelStatistics>(error, 'status_failed')
    }
  }

  async uploadAsset(name: string, payload: ArrayBuffer | string): Promise<ChannelResult<{ assetId: string }>> {
    try {
      const result = await this.transport.send('uploadAsset', { name, payload })
      const assetId = (result as Record<string, unknown>)?.assetId
      return { ok: true, data: { assetId: typeof assetId === 'string' ? assetId : `placeholder-${name}` } }
    } catch (error) {
      return this.handleError<{ assetId: string }>(error, 'upload_failed')
    }
  }

  private handleError<T>(error: unknown, code: string): ChannelResult<T> {
    return {
      ok: false,
      error: {
        code,
        message: error instanceof Error ? error.message : String(error),
      },
    }
  }
}
