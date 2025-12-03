/**
 * Virtual Road Test TypeScript Types
 *
 * Type definitions for road test scenarios, topologies, and executions
 */

// ===== Enums =====

export const NetworkType = {
  NR_FR1: 'NR_FR1' as const,
  FR1: '5G_NR' as const,
  LTE: 'LTE' as const,
  C_V2X: 'C-V2X' as const,
}
export type NetworkType = typeof NetworkType[keyof typeof NetworkType]

export const ScenarioCategory = {
  STANDARD: 'standard' as const,
  FUNCTIONAL: 'functional' as const,
  PERFORMANCE: 'performance' as const,
  ENVIRONMENT: 'environment' as const,
  EXTREME: 'extreme' as const,
  CUSTOM: 'custom' as const,
}
export type ScenarioCategory = typeof ScenarioCategory[keyof typeof ScenarioCategory]

export const ScenarioSource = {
  STANDARD: 'standard' as const,
  CUSTOM: 'custom' as const,
}
export type ScenarioSource = typeof ScenarioSource[keyof typeof ScenarioSource]

export const ChannelModel = {
  UMa: 'UMa' as const,
  UMi: 'UMi' as const,
  RMa: 'RMa' as const,
  InH: 'InH' as const,
  CDL_A: 'CDL-A' as const,
  CDL_B: 'CDL-B' as const,
  CDL_C: 'CDL-C' as const,
  CDL_D: 'CDL-D' as const,
  CDL_E: 'CDL-E' as const,
  TDL_A: 'TDL-A' as const,
  TDL_B: 'TDL-B' as const,
  TDL_C: 'TDL-C' as const,
  CUSTOM: 'CUSTOM' as const,
  WINNER_B1: 'WINNER_B1' as const,
}
export type ChannelModel = typeof ChannelModel[keyof typeof ChannelModel]

export const EnvironmentType = {
  URBAN_CANYON: 'urban_canyon' as const,
  URBAN_STREET: 'urban_street' as const,
  HIGHWAY: 'highway' as const,
  TUNNEL: 'tunnel' as const,
  PARKING_LOT: 'parking_lot' as const,
  RURAL: 'rural' as const,
  SUBURBAN: 'suburban' as const,
  URBAN_MACRO: 'URBAN_MACRO' as const,
  URBAN_MICRO: 'URBAN_MICRO' as const,
  INDOOR: 'INDOOR' as const,
}
export type EnvironmentType = typeof EnvironmentType[keyof typeof EnvironmentType]

export const TestMode = {
  DIGITAL_TWIN: 'digital_twin' as const,
  CONDUCTED: 'conducted' as const,
  OTA: 'ota' as const,
}
export type TestMode = typeof TestMode[keyof typeof TestMode]

export type ExecutionStatus = 'idle' | 'initializing' | 'configured' | 'running' | 'paused' | 'completed' | 'failed' | 'stopped'

export const DuplexMode = {
  TDD: 'TDD' as const,
  FDD: 'FDD' as const,
}
export type DuplexMode = typeof DuplexMode[keyof typeof DuplexMode]

export const PathType = {
  URBAN_GRID: 'URBAN_GRID' as const,
  HIGHWAY: 'HIGHWAY' as const,
  CUSTOM: 'CUSTOM' as const,
  LINEAR: 'LINEAR' as const,
  CIRCULAR: 'CIRCULAR' as const,
}
export type PathType = typeof PathType[keyof typeof PathType]

export const TrafficType = {
  FTP: 'FTP' as const,
  HTTP: 'HTTP' as const,
  VIDEO: 'VIDEO' as const,
  VOIP: 'VOIP' as const,
  CUSTOM: 'CUSTOM' as const,
}
export type TrafficType = typeof TrafficType[keyof typeof TrafficType]

export const TrafficDirection = {
  DOWNLINK: 'DOWNLINK' as const,
  UPLINK: 'UPLINK' as const,
  BIDIRECTIONAL: 'BIDIRECTIONAL' as const,
}
export type TrafficDirection = typeof TrafficDirection[keyof typeof TrafficDirection]

export const KPIMetric = {
  THROUGHPUT_DL: 'THROUGHPUT_DL' as const,
  THROUGHPUT_UL: 'THROUGHPUT_UL' as const,
  LATENCY: 'LATENCY' as const,
  JITTER: 'JITTER' as const,
  PACKET_LOSS: 'PACKET_LOSS' as const,
  HANDOVER_SUCCESS_RATE: 'HANDOVER_SUCCESS_RATE' as const,
  HANDOVER_LATENCY: 'HANDOVER_LATENCY' as const,
  RSRP: 'RSRP' as const,
  COVERAGE: 'COVERAGE' as const,
  SINR: 'SINR' as const,
}
export type KPIMetric = typeof KPIMetric[keyof typeof KPIMetric]

export const TriggerType = {
  HANDOVER: 'HANDOVER' as const,
  MEASUREMENT: 'MEASUREMENT' as const,
  TIMER: 'TIMER' as const,
}
export type TriggerType = typeof TriggerType[keyof typeof TriggerType]

// ===== Scenario Types =====

export interface NetworkConfig {
  type: NetworkType
  band: string
  bandwidth_mhz: number
  duplex_mode: 'TDD' | 'FDD'
  scs_khz?: number
}

export interface BaseStationConfig {
  bs_id: string
  name: string
  position: {
    lat: number
    lon: number
    alt: number
  }
  tx_power_dbm: number
  antenna_height_m: number
  antenna_config: string
  azimuth_deg: number
  tilt_deg: number
}

export interface Waypoint {
  time_s: number
  position: {
    lat: number
    lon: number
    alt: number
  }
  velocity: {
    speed_kmh: number
    heading_deg: number
  }
}

export interface Route {
  type: 'predefined' | 'recorded' | 'generated'
  waypoints: Waypoint[]
  duration_s: number
  total_distance_m: number
  description?: string
}

export interface Environment {
  type: EnvironmentType
  channel_model: ChannelModel
  weather: 'clear' | 'rain' | 'fog' | 'snow'
  traffic_density: 'low' | 'medium' | 'high'
  obstructions?: any[]
}

export interface KPIDefinition {
  kpi_type: string
  target_value: number
  unit: string
  percentile?: number
  threshold_min?: number
  threshold_max?: number
}

export interface RoadTestScenario {
  id: string
  name: string
  category: ScenarioCategory
  source?: ScenarioSource
  tags?: string[]
  description?: string
  network?: NetworkConfig
  base_stations?: BaseStationConfig[]
  route?: Route
  environment?: Environment
  traffic?: any
  events?: any[]
  kpi_definitions?: KPIDefinition[]
  created_at?: string
  createdAt?: string
  updated_at?: string
  updatedAt?: string
  author?: string
  version?: string
  taxonomy?: any
  isComplete?: boolean
  isValidated?: boolean
  canExecute?: {
    ota?: boolean
    conducted?: boolean
    digitalTwin?: boolean
  }
  summary?: {
    networkType?: NetworkType
    environmentType?: EnvironmentType
    duration?: number
    avgSpeed?: number
    numBaseStations?: number
    kpiCount?: number
  }
}

export interface ScenarioSummary {
  id: string
  name: string
  category: ScenarioCategory
  source: ScenarioSource
  tags: string[]
  description?: string
  duration_s: number
  distance_m: number
  created_at?: string
  author?: string
}

// ===== Execution Types =====

export interface TestExecution {
  execution_id: string
  mode: TestMode
  status: ExecutionStatus
  scenario_id: string
  topology_id?: string
  config: Record<string, any>
  start_time?: string
  end_time?: string
  duration_s?: number
  created_by?: string
  notes?: string
}

export interface ExecutionSummary {
  execution_id: string
  mode: TestMode
  status: ExecutionStatus
  scenario_name: string
  start_time?: string
  duration_s?: number
  progress_percent: number
  created_by?: string
}

export interface TestStatus {
  execution_id: string
  status: ExecutionStatus
  progress_percent: number
  elapsed_time_s: number
  remaining_time_s?: number
  current_waypoint_index?: number
  current_time_s?: number
  current_position?: { lat: number; lon: number; alt: number }
  last_error?: string
  warnings: string[]
}

// ===== Detailed Scenario Types =====

export interface RoadTestScenarioDetail {
  id: string
  name: string
  description?: string
  category: ScenarioCategory
  taxonomy?: any
  origin?: any
  metadata?: {
    version?: string
    createdAt?: string
    updatedAt?: string
    author?: string
    organization?: string
  }
  networkConfig?: any
  trajectory?: any
  environment?: any
  traffic?: any
  triggers?: any[]
  kpiTargets?: any[]
  rayTracingOutput?: any
  integrity?: {
    dataCompleteness?: Record<string, boolean>
    validation?: {
      isValidated?: boolean
      validatedBy?: string
      validatedAt?: string
      validationNotes?: string
    }
    executability?: {
      canExecuteOTA?: boolean
      canExecuteConducted?: boolean
      canExecuteDigitalTwin?: boolean
      blockers?: string[]
    }
  }
  notes?: string
  references?: Array<{
    title?: string
    document?: string
    url?: string
  }>
}

// ===== API Response Types =====

export interface ScenariosListResponse {
  scenarios: ScenarioSummary[]
  total: number
}

export interface ExecutionsListResponse {
  executions: ExecutionSummary[]
  total: number
}
