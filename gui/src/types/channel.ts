export type ChannelScenario = {
  id: string
  name: string
  description?: string
  source: 'preset' | 'file' | 'custom'
}

export type ChannelModelConfig = {
  standard: '3gpp' | 'ctia' | 'custom'
  profile: string
  bandwidthMHz: number
  centerFrequencyMHz: number
  doppler?: number
  additionalParams?: Record<string, unknown>
}

export type ChannelStatus =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'idle'
  | 'loading'
  | 'running'
  | 'paused'
  | 'error'

export type ChannelStatistics = {
  timestamp: string
  state: ChannelStatus
  operatingScenario?: string
  temperatureC?: number
  warnings?: string[]
}

export type ChannelResult<T = unknown> = {
  ok: boolean
  data?: T
  error?: { code: string; message: string }
}

export interface IChannelEmulatorDriver {
  connect(endpoint: string, options?: Record<string, unknown>): Promise<ChannelResult>
  disconnect(): Promise<ChannelResult>
  loadScenario(scenario: ChannelScenario): Promise<ChannelResult>
  configureModel(config: ChannelModelConfig): Promise<ChannelResult>
  start(): Promise<ChannelResult>
  pause(): Promise<ChannelResult>
  stop(): Promise<ChannelResult>
  queryStatus(): Promise<ChannelResult<ChannelStatistics>>
  uploadAsset(name: string, payload: ArrayBuffer | string): Promise<ChannelResult<{ assetId: string }>>
}
