/**
 * Unified Report Types
 *
 * Type definitions for the unified report system
 */

// ===== Report Content Data Types =====

export interface ReportScenarioInfo {
  id: string
  name: string
  category: string
  description?: string
  tags: string[]
}

export interface ReportNetworkInfo {
  type: string
  band: string
  bandwidth_mhz: number
  duplex_mode: string
  scs_khz?: number
}

export interface ReportEnvironmentInfo {
  type: string
  channel_model: string
  weather: string
  traffic_density: string
}

export interface ReportRouteInfo {
  duration_s: number
  distance_m: number
  waypoint_count: number
  avg_speed_kmh?: number
}

export interface ReportBaseStationInfo {
  bs_id: string
  name: string
  tx_power_dbm: number
  antenna_config: string
  antenna_height_m: number
}

export interface ReportStepConfig {
  step_name: string
  enabled: boolean
  parameters: Record<string, any>
}

export interface ReportPhaseResult {
  name: string
  status: 'completed' | 'failed' | 'skipped'
  duration_s: number
  start_time: string
  end_time: string
  notes?: string
}

export interface ReportKPISummary {
  name: string
  unit: string
  mean: number
  min: number
  max: number
  std?: number
  target?: number
  passed?: boolean
}

export interface ReportEvent {
  time: string
  type: string
  description: string
}

export interface ReportLog {
  timestamp: string
  level: string
  message: string
  source: string
}

// ===== Time Series and Trajectory Types =====

export interface TimeSeriesPoint {
  time_s: number
  position?: { lat: number; lon: number; alt?: number }
  rsrp_dbm?: number
  rsrq_db?: number
  sinr_db?: number
  dl_throughput_mbps?: number
  ul_throughput_mbps?: number
  latency_ms?: number
  event?: string
}

export interface TrajectoryPoint {
  lat: number
  lon: number
  alt?: number
  time_s?: number
}

// ===== Detailed Configuration Types =====

export interface NetworkConfigDetail {
  authentication?: {
    method: string
    sim_profile?: Record<string, unknown>
  }
  qos?: {
    fiveqi: number
    gbr_enabled: boolean
    max_dl_bitrate?: string
    max_ul_bitrate?: string
  }
  pdu_session?: {
    type: string
    sst: number
    dnn: string
  }
  applications?: string[]
}

export interface BaseStationConfigDetail {
  rf?: {
    frequency_mhz: number
    mimo_layers: number
    carrier_aggregation?: boolean
  }
  antenna?: {
    type: string
    mimo_config: string
    gain_dbi: number
    tilt_deg?: number
  }
  beamforming?: {
    enabled: boolean
    mode: string
    num_ssb_beams: number
    tracking_mode?: string
  }
  handover?: {
    a3_offset_db?: number
    hysteresis_db?: number
    time_to_trigger_ms?: number
  }
}

export interface DigitalTwinConfig {
  channel_model?: {
    type: string
    scenario?: string
  }
  ray_tracing?: {
    enabled: boolean
    max_reflections?: number
    diffraction?: boolean
  }
  weather?: {
    condition: string
    rain_rate_mm_h?: number
    temperature_c?: number
  }
  interference?: {
    enabled: boolean
    model?: string
  }
}

export interface CustomConfigHighlight {
  category: string
  label: string
  value: unknown
  description?: string
}

/**
 * Unified report content data structure
 * Used by both test plans and virtual road tests
 */
export interface ReportContentData {
  // Source identification
  source: 'test_plan' | 'road_test'
  execution_id: string
  title: string
  description?: string

  // Execution info
  execution: {
    mode?: string
    status: string
    start_time?: string
    end_time?: string
    duration_s?: number
    notes?: string
  }

  // Scenario (virtual road test specific)
  scenario?: ReportScenarioInfo

  // Configuration
  network?: ReportNetworkInfo
  environment?: ReportEnvironmentInfo
  route?: ReportRouteInfo
  base_stations?: ReportBaseStationInfo[]
  step_configs?: ReportStepConfig[]

  // Results
  phases: ReportPhaseResult[]
  kpi_summary: ReportKPISummary[]
  overall_result: 'passed' | 'failed' | 'incomplete'
  pass_rate: number
  events: ReportEvent[]
  logs?: ReportLog[]

  // Time series data for charts
  time_series?: TimeSeriesPoint[]

  // Trajectory for map (road_test only)
  trajectory?: TrajectoryPoint[]

  // Detailed configurations
  network_config_detail?: NetworkConfigDetail
  base_station_config_detail?: BaseStationConfigDetail
  digital_twin_config?: DigitalTwinConfig

  // Custom config highlights (for special/custom scenarios)
  custom_config_highlights?: CustomConfigHighlight[]
}

// ===== Report Response Types =====

export type ReportType = 'single_execution' | 'road_test' | 'comparison' | 'summary' | 'compliance' | 'custom'
export type ReportFormat = 'pdf' | 'html' | 'excel' | 'json'
export type ReportStatus = 'pending' | 'generating' | 'completed' | 'failed' | 'cancelled'

export interface Report {
  id: string
  title: string
  description?: string
  report_type: ReportType
  format: ReportFormat

  // Associated data
  test_plan_id?: string
  test_execution_ids?: string[]
  comparison_plan_ids?: string[]
  road_test_execution_id?: string

  // Status
  status: ReportStatus
  progress_percent: number

  // Content
  content_data?: ReportContentData

  // File info
  file_path?: string
  file_size_bytes?: number

  // Timing
  generation_started_at?: string
  generation_completed_at?: string

  // Metadata
  generated_by: string
  generated_at: string
  tags?: string[]
  category?: string
  notes?: string
}

export interface ReportSummary {
  id: string
  title: string
  report_type: ReportType
  format: ReportFormat
  status: ReportStatus
  progress_percent: number
  file_size_bytes?: number
  generated_by: string
  generated_at: string
}

export interface ReportListResponse {
  reports: ReportSummary[]
  total: number
  page: number
  page_size: number
}

export interface CreateReportRequest {
  title: string
  description?: string
  report_type: ReportType
  format?: ReportFormat
  generated_by: string
  test_plan_id?: string
  test_execution_ids?: string[]
  road_test_execution_id?: string
  content_data?: ReportContentData
  tags?: string[]
  category?: string
  notes?: string
}
