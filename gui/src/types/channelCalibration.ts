/**
 * Channel Calibration Types
 *
 * TypeScript types for channel calibration API
 * Based on api-service/app/schemas/channel_calibration.py
 */

// ==================== Enums ====================

export type ScenarioType = 'UMa' | 'UMi' | 'RMa' | 'InH'

export type ScenarioCondition = 'LOS' | 'NLOS'

export type DistributionType = 'Laplacian' | 'Gaussian' | 'Uniform'

export type QuietZoneShape = 'sphere' | 'cylinder'

export type FieldProbeType = 'dipole' | 'horn' | 'eField' | 'hField'

export type DUTType = 'vehicle' | 'phone' | 'module' | 'reference'

export type ChannelCalibrationStatus = 'valid' | 'expired' | 'invalidated' | 'pending'

export type ChannelCalibrationJobStatus = 'queued' | 'running' | 'completed' | 'failed'

export type SessionStatus = 'created' | 'in_progress' | 'completed' | 'failed' | 'cancelled'

export type ChannelCalibrationType =
  | 'temporal'
  | 'doppler'
  | 'spatial_correlation'
  | 'angular_spread'
  | 'quiet_zone'
  | 'eis'

export type ValidityStatus = 'valid' | 'expiring_soon' | 'expired' | 'unknown'

// ==================== Common Types ====================

export interface CalibrationJobResponse {
  calibration_job_id: string
  status: ChannelCalibrationJobStatus
  estimated_duration_minutes?: number
  message?: string
}

export interface CalibrationProgress {
  job_id: string
  status: ChannelCalibrationJobStatus
  progress_percent: number
  current_step?: string
  error_message?: string
}

export interface ScenarioConfig {
  type: ScenarioType
  condition: ScenarioCondition
  fc_ghz: number
  distance_2d_m?: number
}

// ==================== Session Management ====================

export interface StartCalibrationSessionRequest {
  name: string
  description?: string
  workflow_id?: string
  configuration?: Record<string, unknown>
  created_by?: string
}

export interface CalibrationSessionResponse {
  id: string
  name: string
  description?: string
  workflow_id?: string
  configuration?: Record<string, unknown>
  status: SessionStatus
  progress_percent: number
  current_stage?: string
  started_at?: string
  completed_at?: string
  overall_pass?: boolean
  total_calibrations?: number
  passed_calibrations?: number
  failed_calibrations?: number
  created_by?: string
  created_at: string
  updated_at: string
}

export interface UpdateSessionProgressRequest {
  progress_percent?: number
  current_stage?: string
  status?: SessionStatus
}

export interface CompleteSessionRequest {
  overall_pass: boolean
  total_calibrations: number
  passed_calibrations: number
  failed_calibrations: number
}

// ==================== Temporal Calibration ====================

export interface StartTemporalCalibrationRequest {
  scenario: ScenarioConfig
  session_id?: string
  channel_emulator_id?: string
  calibrated_by?: string
}

export interface TemporalCalibrationResponse {
  id: string
  session_id?: string
  scenario_type: string
  scenario_condition: string
  fc_ghz: number
  // PDP data
  measured_pdp?: {
    delay_bins_ns: number[]
    power_db: number[]
  }
  // Results
  measured_rms_delay_spread_ns: number
  reference_rms_delay_spread_ns: number
  reference_rms_delay_spread_range_ns: number[]
  rms_error_percent: number
  // Clusters
  detected_cluster_delays_ns?: number[]
  detected_cluster_powers_db?: number[]
  detected_num_clusters: number
  reference_num_clusters: number
  // Validation
  validation_pass: boolean
  threshold_percent: number
  // Metadata
  channel_emulator?: string
  calibrated_at: string
  calibrated_by?: string
  valid_until: string
  status: string
}

// ==================== Doppler Calibration ====================

export interface StartDopplerCalibrationRequest {
  velocity_kmh: number
  fc_ghz: number
  session_id?: string
  channel_emulator_id?: string
  calibrated_by?: string
}

export interface DopplerCalibrationResponse {
  id: string
  session_id?: string
  velocity_kmh: number
  fc_ghz: number
  expected_doppler_hz: number
  // Spectrum data
  measured_spectrum?: {
    frequency_bins_hz: number[]
    power_db: number[]
  }
  reference_spectrum?: {
    frequency_bins_hz: number[]
    power_db: number[]
  }
  // Results
  spectral_correlation: number
  spectral_correlation_threshold: number
  // Validation
  validation_pass: boolean
  // Metadata
  channel_emulator?: string
  calibrated_at: string
  calibrated_by?: string
  valid_until: string
  status: string
}

// ==================== Spatial Correlation Calibration ====================

export interface TestDUTConfig {
  antenna_spacing_wavelengths: number
  antenna_spacing_m?: number
  antenna_type?: string
}

export interface StartSpatialCorrelationCalibrationRequest {
  scenario: ScenarioConfig
  test_dut: TestDUTConfig
  session_id?: string
  calibrated_by?: string
}

export interface SpatialCorrelationCalibrationResponse {
  id: string
  session_id?: string
  scenario_type: string
  scenario_condition: string
  fc_ghz: number
  // DUT config
  antenna_spacing_wavelengths: number
  antenna_spacing_m?: number
  antenna_type?: string
  // Results
  measured_correlation_magnitude: number
  measured_correlation_phase_deg: number
  reference_correlation_magnitude: number
  reference_correlation_phase_deg: number
  // Errors
  magnitude_error: number
  phase_error_deg: number
  // Validation
  magnitude_threshold: number
  phase_threshold_deg: number
  validation_pass: boolean
  // Metadata
  calibrated_at: string
  calibrated_by?: string
  valid_until: string
  status: string
}

// ==================== Angular Spread Calibration ====================

export interface StartAngularSpreadCalibrationRequest {
  scenario: ScenarioConfig
  azimuth_step_deg?: number
  session_id?: string
  positioner?: string
  calibrated_by?: string
}

export interface AngularSpreadCalibrationResponse {
  id: string
  session_id?: string
  scenario_type: string
  scenario_condition: string
  fc_ghz: number
  // APS data
  measured_aps?: {
    azimuth_deg: number[]
    power_db: number[]
  }
  // Fitted results
  fitted_mean_azimuth_deg: number
  fitted_rms_angular_spread_deg: number
  fitted_distribution_type: string
  fitted_r_squared: number
  // Reference
  reference_rms_angular_spread_deg: number
  reference_rms_angular_spread_range_deg: number[]
  // Validation
  rms_error_deg: number
  threshold_deg: number
  validation_pass: boolean
  // Metadata
  positioner?: string
  calibrated_at: string
  calibrated_by?: string
  valid_until: string
  status: string
}

// ==================== Quiet Zone Calibration ====================

export interface QuietZoneConfig {
  shape: QuietZoneShape
  diameter_m: number
  height_m?: number
}

export interface FieldProbeConfig {
  type: FieldProbeType
  size_mm: number
}

export interface StartQuietZoneCalibrationRequest {
  quiet_zone: QuietZoneConfig
  field_probe?: FieldProbeConfig
  fc_ghz: number
  num_points?: number
  session_id?: string
  calibrated_by?: string
}

export interface QuietZoneCalibrationResponse {
  id: string
  session_id?: string
  quiet_zone_shape: string
  quiet_zone_diameter_m: number
  quiet_zone_height_m?: number
  field_probe_type: string
  field_probe_size_mm: number
  // Measurement data
  measurement_grid?: {
    points: Array<{
      x_m: number
      y_m: number
      z_m: number
      amplitude_v_per_m: number
      phase_deg: number
    }>
  }
  num_points: number
  // Statistics
  amplitude_mean_db: number
  amplitude_std_db: number
  amplitude_range_db: number[]
  phase_mean_deg: number
  phase_std_deg: number
  phase_range_deg: number[]
  // Validation
  amplitude_uniformity_pass: boolean
  phase_uniformity_pass: boolean
  validation_pass: boolean
  amplitude_threshold_db: number
  phase_threshold_deg: number
  // Metadata
  fc_ghz: number
  calibrated_at: string
  calibrated_by?: string
  valid_until: string
  status: string
}

// ==================== EIS Validation ====================

export interface EISTestConfig {
  fc_ghz: number
  scenario?: string
  bandwidth_mhz?: number
  modulation?: string
  target_throughput_percent?: number
  min_eis_dbm?: number
}

export interface EISDUTConfig {
  model: string
  type?: DUTType
  num_rx_antennas?: number
}

export interface StartEISValidationRequest {
  test_config: EISTestConfig
  dut: EISDUTConfig
  session_id?: string
  measured_by?: string
}

export interface EISValidationResponse {
  id: string
  session_id?: string
  scenario?: string
  fc_ghz: number
  bandwidth_mhz?: number
  modulation?: string
  target_throughput_percent: number
  // DUT
  dut_type: string
  dut_model: string
  num_rx_antennas?: number
  // EIS data
  eis_map?: {
    azimuth_deg: number[]
    elevation_deg: number[]
    eis_dbm: number[][]
  }
  // Results
  peak_eis_dbm: number
  peak_azimuth_deg: number
  peak_elevation_deg: number
  median_eis_dbm: number
  eis_spread_db: number
  // Validation
  min_eis_dbm: number
  validation_pass: boolean
  // Metadata
  measured_at: string
  measured_by?: string
  valid_until: string
  status: string
}

// ==================== History & Validity ====================

export interface ChannelCalibrationHistoryItem {
  calibration_id: string
  calibration_type: ChannelCalibrationType
  calibrated_at: string
  calibrated_by?: string
  status: string
  validation_pass: boolean
  summary: Record<string, unknown>
}

export interface ChannelCalibrationHistoryResponse {
  total: number
  items: ChannelCalibrationHistoryItem[]
}

export interface ChannelCalibrationStatusSummary {
  temporal_status: ValidityStatus
  temporal_last_calibrated?: string
  temporal_next_due?: string

  doppler_status: ValidityStatus
  doppler_last_calibrated?: string
  doppler_next_due?: string

  spatial_correlation_status: ValidityStatus
  spatial_correlation_last_calibrated?: string
  spatial_correlation_next_due?: string

  angular_spread_status: ValidityStatus
  angular_spread_last_calibrated?: string
  angular_spread_next_due?: string

  quiet_zone_status: ValidityStatus
  quiet_zone_last_calibrated?: string
  quiet_zone_next_due?: string

  eis_status: ValidityStatus
  eis_last_calibrated?: string
  eis_next_due?: string

  overall_status: ValidityStatus
  recent_calibrations: ChannelCalibrationHistoryItem[]
}

export interface InvalidateCalibrationRequest {
  reason: string
  invalidated_by?: string
}

export interface InvalidateCalibrationResponse {
  calibration_id: string
  calibration_type: string
  invalidated_at: string
  reason: string
  previous_status: string
}
