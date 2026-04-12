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

// Step keys for constraint mapping
export type StepKey =
  | 'environment_setup'
  | 'chamber_init'
  | 'network_config'
  | 'base_station_setup'
  | 'ota_mapper'
  | 'route_execution'
  | 'kpi_validation'
  | 'report_generation'

// Step constraint definition
export interface StepConstraint {
  required: StepKey[]    // Steps that must be enabled
  disabled: StepKey[]    // Steps that cannot be enabled
  optional: StepKey[]    // Steps that user can toggle
}

// Test mode step constraints
export const STEP_CONSTRAINTS: Record<TestMode, StepConstraint> = {
  [TestMode.DIGITAL_TWIN]: {
    required: ['environment_setup'],
    disabled: ['chamber_init', 'ota_mapper'],
    optional: ['network_config', 'base_station_setup', 'route_execution', 'kpi_validation', 'report_generation'],
  },
  [TestMode.CONDUCTED]: {
    required: ['network_config', 'base_station_setup'],
    disabled: ['chamber_init', 'ota_mapper'],
    optional: ['environment_setup', 'route_execution', 'kpi_validation', 'report_generation'],
  },
  [TestMode.OTA]: {
    required: ['chamber_init', 'ota_mapper', 'network_config', 'base_station_setup'],
    disabled: [],
    optional: ['environment_setup', 'route_execution', 'kpi_validation', 'report_generation'],
  },
}

// Step metadata for UI display
export const STEP_METADATA: Record<StepKey, { label: string; description: string }> = {
  environment_setup: {
    label: '数字孪生环境配置',
    description: '配置信道模型和仿真环境',
  },
  chamber_init: {
    label: '暗室初始化 (MPAC)',
    description: '初始化OTA暗室和转台',
  },
  network_config: {
    label: '网络配置',
    description: '配置5G/LTE网络参数',
  },
  base_station_setup: {
    label: '基站/信道配置',
    description: '配置基站参数和信道模型',
  },
  ota_mapper: {
    label: 'OTA映射器',
    description: '配置路径和OTA映射',
  },
  route_execution: {
    label: '路径执行',
    description: '执行虚拟路测',
  },
  kpi_validation: {
    label: 'KPI验证',
    description: '验证性能指标',
  },
  report_generation: {
    label: '报告生成',
    description: '生成测试报告',
  },
}

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

export interface ChannelSnapshot {
  timestamp_s: number
  duration_s: number
  channel_type: '3GPP' | 'Custom'
  standard_model?: ChannelModel
  custom_matrix_config?: Record<string, any>
}

export interface Environment {
  type: EnvironmentType
  channel_snapshots: ChannelSnapshot[]
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

// ===== Interference and Scatterer Types =====

export interface InterferenceSource {
  id: string
  type: 'co-channel' | 'adjacent-channel' | 'out-of-band' | 'wideband'
  position: { lat: number; lon: number; alt: number }
  characteristics: {
    power_dbm: number
    frequency_mhz: number
    bandwidth_mhz: number
    modulation?: string
    duty_cycle?: number  // 0-1, for intermittent interference
  }
  temporal?: {
    start_time_s: number
    duration_s: number
    pattern: 'continuous' | 'pulsed' | 'random'
  }
}

export interface MovingScatterer {
  id: string
  type: 'vehicle' | 'pedestrian' | 'train' | 'aircraft'
  trajectory: Waypoint[]
  rcs_dbsm: number  // Radar Cross Section in dB-m²
  blockage: {
    attenuation_db: number
    shadow_region_m: number
  }
}

// ===== Application Test Types =====

export const ApplicationType = {
  FTP_DL: 'ftp_dl' as const,
  FTP_UL: 'ftp_ul' as const,
  UDP_DL: 'udp_dl' as const,
  UDP_UL: 'udp_ul' as const,
  IPERF: 'iperf' as const,
  HTTP: 'http' as const,
  VIDEO_STREAMING: 'video_streaming' as const,
  VIDEO_CALL: 'video_call' as const,
  XR_VR: 'xr_vr' as const,
  XR_AR: 'xr_ar' as const,
  XR_CLOUD: 'xr_cloud' as const,
  VOIP: 'voip' as const,
  EMAIL: 'email' as const,
  WEB_BROWSING: 'web_browsing' as const,
  PING: 'ping' as const,
}
export type ApplicationType = typeof ApplicationType[keyof typeof ApplicationType]

// Application test configuration
export interface ApplicationTestConfig {
  type: ApplicationType
  enabled: boolean
  // FTP configuration
  ftp?: {
    server_ip: string
    port: number
    file_size_mb: number
    concurrent_connections: number
    username?: string
    password?: string
  }
  // UDP/iPerf configuration
  udp?: {
    target_rate_mbps: number
    packet_size_bytes: number
    duration_s: number
    server_ip: string
    port: number
    bidirectional?: boolean
  }
  // Video streaming configuration
  video?: {
    resolution: '720p' | '1080p' | '4K' | '8K'
    codec: 'H.264' | 'H.265' | 'VP9' | 'AV1'
    bitrate_mbps: number
    frame_rate: 30 | 60 | 120
    server_url?: string
    protocol: 'HLS' | 'DASH' | 'RTSP' | 'WebRTC'
  }
  // XR configuration
  xr?: {
    application: 'gaming' | 'collaboration' | 'streaming' | 'industrial'
    target_latency_ms: number
    target_frame_rate: 72 | 90 | 120
    resolution_per_eye: '1080p' | '2K' | '4K'
    pose_update_rate_hz: number
    motion_to_photon_ms: number
  }
  // VoIP configuration
  voip?: {
    codec: 'G.711' | 'G.729' | 'AMR' | 'EVS'
    calls_count: number
    call_duration_s: number
  }
  // Email configuration
  email?: {
    attachment_size_mb: number
    emails_per_minute: number
  }
  // HTTP/Web browsing
  http?: {
    urls: string[]
    think_time_s: number
    page_load_timeout_s: number
  }
}

// ===== Enhanced Step Configuration =====

// Step 2: Network Configuration (Core Network Layer)
export interface NetworkStepConfig {
  // Authentication Configuration
  authentication: {
    method: 'open' | '5g-aka' | 'eap-tls' | 'sim'
    sim_profile?: {
      imsi: string
      ki?: string
      opc?: string
    }
    certificate?: {
      enabled: boolean
      cert_file?: string
    }
  }

  // IP Allocation Configuration
  ip_config: {
    mode: 'dhcp' | 'static' | 'pdn'
    ipv4?: {
      address?: string
      subnet?: string
      gateway?: string
      dns?: string[]
    }
    ipv6?: {
      enabled: boolean
      prefix?: string
    }
    apn?: string  // Access Point Name
  }

  // PDU Session / Bearer Configuration
  pdu_session: {
    type: 'ipv4' | 'ipv6' | 'ipv4v6' | 'ethernet'
    sst: number  // Slice/Service Type (1=eMBB, 2=URLLC, 3=MIoT)
    sd?: string  // Slice Differentiator
    dnn: string  // Data Network Name
  }

  // QoS Configuration
  qos: {
    fiveqi: number  // 5G QoS Identifier (1-255)
    priority_level?: number
    packet_delay_budget_ms?: number
    packet_error_rate?: number
    gbr?: {
      enabled: boolean
      dl_gbr_kbps?: number
      ul_gbr_kbps?: number
    }
  }

  // Application layer tests
  applications: {
    enabled: boolean
    tests: ApplicationTestConfig[]
    sequential: boolean  // Run tests sequentially or in parallel
  }

  // Verification
  verify_registration: boolean
  verify_pdu_session: boolean
  timeout_seconds: number
}

// Step 3: Base Station Configuration (RAN Layer)
export interface BaseStationStepConfig {
  // RF Parameters (moved from NetworkStepConfig)
  rf: {
    frequency_mhz: number
    bandwidth_mhz: number
    scs_khz: 15 | 30 | 60 | 120  // Subcarrier spacing
    duplex_mode: 'TDD' | 'FDD'
    tdd_config?: {
      pattern: string  // e.g., "DDDSU" or "DDDSUUDDDD"
      special_slot_config?: number
    }
    mimo_layers: 1 | 2 | 4 | 8
    carrier_aggregation?: {
      enabled: boolean
      num_carriers: number
      carrier_configs?: Array<{
        frequency_mhz: number
        bandwidth_mhz: number
      }>
    }
  }

  // Cell Parameters (moved from NetworkStepConfig)
  cell: {
    pci: number  // Physical Cell ID (0-1007)
    tac: number  // Tracking Area Code
    cell_id: number  // Cell Identity
    plmn: {
      mcc: string  // Mobile Country Code
      mnc: string  // Mobile Network Code
    }
    band: string  // e.g., "n78", "n41", "B1"
    earfcn_nrarfcn?: number  // E-UTRA/NR ARFCN
  }

  // Power Parameters (moved from NetworkStepConfig)
  power: {
    total_power_dbm: number  // Total BS transmit power
    ssb_power_dbm?: number  // SSB power
    pdsch_power_offset_db?: number
    pusch_power_control?: {
      p0_nominal_dbm: number
      alpha: number  // 0, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1
    }
  }

  // Deployment Configuration
  deployment: {
    num_base_stations: number
    topology: 'single' | 'linear' | 'hexagonal' | 'custom'
    inter_site_distance_m?: number
    positions?: Array<{
      bs_id: string
      lat: number
      lon: number
      alt: number
    }>
  }

  // Antenna Configuration
  antenna: {
    type: 'omni' | 'sector' | 'massive_mimo' | 'aat'  // AAT = Active Antenna Technology
    mimo_config: '2x2' | '4x4' | '8x8' | '16x16' | '32x32' | '64x64'
    antenna_height_m: number
    antenna_elements?: {
      horizontal: number
      vertical: number
    }
    polarization: 'single' | 'dual' | 'cross'
    gain_dbi: number
    azimuth_deg: number  // 0-360
    mechanical_tilt_deg: number  // 0-15
    electrical_tilt_deg?: number  // 0-15
  }

  // Beam Configuration (for 5G NR)
  beamforming?: {
    enabled: boolean
    mode: 'static' | 'dynamic' | 'codebook' | 'eigenvalue'
    num_ssb_beams: number  // 4, 8, 16, 32, 64
    beam_sweep_period_ms?: number
    beam_tracking?: {
      enabled: boolean
      update_period_ms: number
    }
  }

  // Handover Configuration
  handover?: {
    enabled: boolean
    a3_offset_db: number  // Event A3 offset
    hysteresis_db: number
    time_to_trigger_ms: number
    measurement_gap_config?: string
  }

  // Verification
  verify_coverage: boolean
  verify_neighbor_relations: boolean
  verify_signal: boolean
  timeout_seconds: number
}

// Step 8: Digital Twin Environment (Deterministic Channel)
export interface DigitalTwinStepConfig {
  // Channel Model Selection
  channel_model: {
    type: 'statistical' | 'ray-tracing' | 'measured' | 'hybrid'
    // Use scenario-level statistical model as fallback
    use_scenario_default: boolean
  }
  // Ray Tracing Configuration (deterministic)
  ray_tracing?: {
    enabled: boolean
    // 3D Environment
    environment: {
      model_file?: string  // e.g., ".obj", ".gltf", ".osm"
      model_type: 'simplified' | 'detailed' | 'point_cloud'
      buildings?: {
        source: 'osm' | 'custom' | 'lidar'
        material_db?: string
      }
      terrain?: {
        enabled: boolean
        dem_file?: string  // Digital Elevation Model
        resolution_m: number
      }
    }
    // Ray Tracing Parameters
    parameters: {
      max_reflections: number  // 0-10
      max_diffractions: number  // 0-3
      max_scattering: number  // 0-5
      ray_spacing_deg?: number
      frequency_dependent_materials: boolean
    }
    // Material Properties
    materials?: Array<{
      name: string
      permittivity: number
      conductivity: number
      roughness_m?: number
    }>
    // Acceleration
    acceleration: {
      method: 'sbr' | 'image' | 'hybrid'  // SBR = Shooting and Bouncing Rays
      gpu_enabled: boolean
      precompute: boolean
    }
  }
  // Measured Channel (CIR playback)
  measured_channel?: {
    enabled: boolean
    cir_file: string  // Channel Impulse Response file
    format: 'matlab' | 'csv' | 'hdf5' | 'sigmf'
    time_alignment: 'gps' | 'route_distance' | 'manual'
    interpolation: 'linear' | 'spline' | 'nearest'
    loop: boolean  // Loop when reaching end
  }
  // Hybrid Model (ray-tracing + statistical)
  hybrid?: {
    enabled: boolean
    ray_tracing_for_los: boolean
    statistical_for_nlos: boolean
    cluster_generation: 'rt_based' | '3gpp' | 'hybrid'
  }
  // Dynamic Environment
  interference?: {
    enabled: boolean
    sources: Array<{
      id: string
      type: 'co-channel' | 'adjacent-channel' | 'wideband' | 'pulsed'
      position: { lat: number; lon: number; alt: number }
      power_dbm: number
      frequency_mhz: number
      bandwidth_mhz: number
      temporal?: {
        start_time_s: number
        duration_s: number
        duty_cycle?: number
      }
    }>
  }
  scatterers?: {
    enabled: boolean
    sources: Array<{
      id: string
      type: 'vehicle' | 'pedestrian' | 'train' | 'uav'
      trajectory_file?: string
      rcs_dbsm: number  // Radar Cross Section
      velocity_kmh: number
      blockage_attenuation_db: number
    }>
  }
  // Weather Effects
  weather?: {
    enabled: boolean
    condition: 'clear' | 'rain' | 'snow' | 'fog'
    rain_rate_mmh?: number  // For rain attenuation
    visibility_m?: number  // For fog
  }
  // Doppler & Time Variance
  doppler?: {
    enabled: boolean
    max_doppler_hz?: number
    time_variance_model: 'jakes' | 'cluster_based' | 'measured'
  }
  // Validation & Output
  validate_environment: boolean
  export_channel_data: boolean
  export_format?: 'matlab' | 'hdf5' | 'csv'
  timeout_seconds: number
}

// Step configuration for test plan generation
export interface StepConfiguration {
  chamber_init?: {
    chamber_id?: string
    timeout_seconds?: number
    verify_connections?: boolean
    calibrate_position_table?: boolean
  }
  // Step 2: Enhanced network configuration
  network_config?: NetworkStepConfig
  // Step 3: Enhanced base station configuration
  base_station_setup?: BaseStationStepConfig
  ota_mapper?: {
    route_file?: string
    route_type?: string
    update_rate_hz?: number
    enable_handover?: boolean
    position_tolerance_m?: number
    timeout_seconds?: number
  }
  route_execution?: {
    route_duration_s?: number
    total_distance_m?: number
    environment_type?: string
    monitor_kpis?: boolean
    log_interval_s?: number
    auto_screenshot?: boolean
    timeout_seconds?: number
  }
  kpi_validation?: {
    kpi_thresholds?: {
      min_throughput_mbps?: number
      max_latency_ms?: number
      min_rsrp_dbm?: number
      max_packet_loss_percent?: number
    }
    generate_plots?: boolean
    timeout_seconds?: number
  }
  report_generation?: {
    report_format?: string
    include_raw_data?: boolean
    include_screenshots?: boolean
    include_recommendations?: boolean
    timeout_seconds?: number
  }
  // Step 8: Digital Twin Environment (Deterministic Channel)
  environment_setup?: DigitalTwinStepConfig
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
  step_configuration?: StepConfiguration  // NEW: Pre-configured test steps
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
  step_configuration?: StepConfiguration  // Pre-configured test steps
  created_at?: string
  author?: string
  // Extended fields for editing
  network_type?: string
  band?: string
  bandwidth_mhz?: number
  channel_model?: string
  avg_speed_kmh?: number
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

// ===== Report Types =====

export interface PhaseResult {
  name: string
  status: 'completed' | 'failed' | 'skipped'
  duration_s: number
  start_time: string
  end_time: string
  notes?: string
}

export interface KPISummary {
  name: string
  unit: string
  mean: number
  min: number
  max: number
  std?: number
  target?: number
  passed?: boolean
}

export interface ScenarioInfo {
  id: string
  name: string
  category: string
  description?: string
  tags: string[]
}

export interface NetworkInfo {
  type: string
  band: string
  bandwidth_mhz: number
  duplex_mode: string
  scs_khz?: number
}

export interface EnvironmentInfo {
  type: string
  channel_model: string
  weather: string
  traffic_density: string
}

export interface RouteInfo {
  duration_s: number
  distance_m: number
  waypoint_count: number
  avg_speed_kmh?: number
}

export interface BaseStationInfo {
  bs_id: string
  name: string
  tx_power_dbm: number
  antenna_config: string
  antenna_height_m: number
}

export interface StepConfigInfo {
  step_name: string
  enabled: boolean
  parameters: Record<string, any>
}

// Time series point for charts
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

// Trajectory point for map
export interface TrajectoryPoint {
  lat: number
  lon: number
  alt?: number
  time_s?: number
}

// Detailed configuration types
export interface NetworkConfigDetail {
  authentication?: Record<string, unknown>
  qos?: Record<string, unknown>
  pdu_session?: Record<string, unknown>
  applications?: string[]
}

export interface BaseStationConfigDetail {
  rf?: Record<string, unknown>
  antenna?: Record<string, unknown>
  beamforming?: Record<string, unknown>
  handover?: Record<string, unknown>
}

export interface DigitalTwinConfig {
  channel_model?: Record<string, unknown>
  ray_tracing?: Record<string, unknown>
  weather?: Record<string, unknown>
  interference?: Record<string, unknown>
}

export interface CustomConfigHighlight {
  category: string
  label: string
  value: unknown
  description?: string
}

export interface ExecutionReport {
  execution_id: string
  scenario_name: string
  mode: TestMode
  status: ExecutionStatus
  // Scenario details
  scenario?: ScenarioInfo
  network?: NetworkInfo
  environment?: EnvironmentInfo
  route?: RouteInfo
  base_stations: BaseStationInfo[]
  step_configs: StepConfigInfo[]
  // Timing
  start_time?: string
  end_time?: string
  duration_s?: number
  // Results
  phases: PhaseResult[]
  kpi_summary: KPISummary[]
  overall_result: 'passed' | 'failed' | 'incomplete'
  pass_rate: number
  events: Array<{
    time: string
    type: string
    description: string
  }>
  // Time series data for charts
  time_series?: TimeSeriesPoint[]
  // Trajectory for map
  trajectory?: TrajectoryPoint[]
  // Detailed configurations
  network_config_detail?: NetworkConfigDetail
  base_station_config_detail?: BaseStationConfigDetail
  digital_twin_config?: DigitalTwinConfig
  // Custom config highlights
  custom_config_highlights?: CustomConfigHighlight[]
  generated_at: string
  notes?: string
}
