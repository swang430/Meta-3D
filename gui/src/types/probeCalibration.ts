/**
 * Probe Calibration Types
 *
 * TypeScript types for probe calibration API
 * Based on api-service/app/schemas/probe_calibration.py
 */

// ==================== Enums ====================

export type PolarizationType = 'V' | 'H' | 'LHCP' | 'RHCP'

export type ProbeType = 'dual_linear' | 'dual_slant' | 'circular'

export type CalibrationStatus = 'valid' | 'expired' | 'invalidated' | 'pending'

export type LinkCalibrationType = 'weekly_check' | 'pre_test' | 'post_maintenance'

export type CalibrationJobStatus = 'queued' | 'running' | 'completed' | 'failed'

export type DUTType = 'dipole' | 'horn' | 'patch'

export type CalibrationType = 'amplitude' | 'phase' | 'polarization' | 'pattern' | 'link'

export type ValidityStatus = 'valid' | 'expiring_soon' | 'expired' | 'unknown'

// ==================== Common Types ====================

export interface FrequencyRange {
  start_mhz: number
  stop_mhz: number
  step_mhz: number
}

export interface CalibrationJobResponse {
  calibration_job_id: string
  status: CalibrationJobStatus
  estimated_duration_minutes?: number
  message?: string
}

export interface CalibrationProgress {
  job_id: string
  status: CalibrationJobStatus
  progress_percent: number
  current_step?: string
  current_probe?: number
  total_probes?: number
  current_frequency_mhz?: number
  total_frequencies?: number
  error_message?: string
}

// ==================== Amplitude Calibration ====================

export interface StartAmplitudeCalibrationRequest {
  probe_ids: number[]
  polarizations?: PolarizationType[]
  frequency_range: FrequencyRange
  reference_antenna_id?: string
  power_meter_id?: string
  calibrated_by: string
}

export interface AmplitudeCalibrationResponse {
  id: string
  probe_id: number
  polarization: string
  frequency_points_mhz: number[]
  tx_gain_dbi: number[]
  rx_gain_dbi: number[]
  tx_gain_uncertainty_db: number[]
  rx_gain_uncertainty_db: number[]
  reference_antenna?: string
  reference_power_meter?: string
  temperature_celsius?: number
  humidity_percent?: number
  calibrated_at: string
  calibrated_by?: string
  valid_until: string
  status: string
}

// ==================== Phase Calibration ====================

export interface StartPhaseCalibrationRequest {
  probe_ids: number[]
  polarizations?: PolarizationType[]
  reference_probe_id?: number
  frequency_range: FrequencyRange
  vna_id?: string
  calibrated_by: string
}

export interface PhaseCalibrationResponse {
  id: string
  probe_id: number
  polarization: string
  reference_probe_id: number
  frequency_points_mhz: number[]
  phase_offset_deg: number[]
  group_delay_ns: number[]
  phase_uncertainty_deg: number[]
  vna_model?: string
  vna_serial?: string
  calibrated_at: string
  calibrated_by?: string
  valid_until: string
  status: string
}

// ==================== Polarization Calibration ====================

export interface StartPolarizationCalibrationRequest {
  probe_ids: number[]
  probe_type: ProbeType
  frequency_range: FrequencyRange
  reference_antenna_id?: string
  positioner_id?: string
  calibrated_by: string
}

export interface PolarizationCalibrationResponse {
  id: string
  probe_id: number
  probe_type: string
  // Linear polarization data
  v_to_h_isolation_db?: number
  h_to_v_isolation_db?: number
  // Circular polarization data
  polarization_hand?: 'LHCP' | 'RHCP'
  axial_ratio_db?: number
  // Frequency-dependent data
  frequency_points_mhz?: number[]
  isolation_vs_frequency_db?: number[]
  axial_ratio_vs_frequency_db?: number[]
  // Reference equipment
  reference_antenna?: string
  positioner?: string
  // Metadata
  calibrated_at: string
  calibrated_by?: string
  valid_until: string
  status: string
}

// ==================== Pattern Calibration ====================

export interface StartPatternCalibrationRequest {
  probe_ids: number[]
  polarizations?: PolarizationType[]
  frequency_mhz: number
  azimuth_step_deg?: number
  elevation_step_deg?: number
  measurement_distance_m?: number
  reference_antenna_id?: string
  turntable_id?: string
  calibrated_by: string
}

export interface PatternCalibrationResponse {
  id: string
  probe_id: number
  polarization: string
  frequency_mhz: number
  // Angle grid
  azimuth_deg: number[]
  elevation_deg: number[]
  // Pattern data
  gain_pattern_dbi: number[]
  // Main parameters
  peak_gain_dbi?: number
  peak_azimuth_deg?: number
  peak_elevation_deg?: number
  hpbw_azimuth_deg?: number
  hpbw_elevation_deg?: number
  front_to_back_ratio_db?: number
  // Measurement settings
  reference_antenna?: string
  turntable?: string
  measurement_distance_m?: number
  // Metadata
  measured_at: string
  measured_by?: string
  valid_until: string
  status: string
}

// ==================== Link Calibration ====================

export interface StandardDUT {
  dut_type: DUTType
  model: string
  serial: string
  known_gain_dbi: number
}

export interface StartLinkCalibrationRequest {
  calibration_type: LinkCalibrationType
  standard_dut: StandardDUT
  frequency_mhz: number
  probe_ids?: number[]
  threshold_db?: number
  calibrated_by: string
}

export interface ProbeLinkCalibration {
  probe_id: number
  link_loss_db: number
  phase_offset_deg: number
}

export interface LinkCalibrationResponse {
  id: string
  calibration_type: string
  // Standard DUT
  standard_dut_type?: string
  standard_dut_model?: string
  standard_dut_serial?: string
  known_gain_dbi?: number
  frequency_mhz?: number
  // Measurement results
  measured_gain_dbi?: number
  deviation_db?: number
  // Probe link calibrations
  probe_link_calibrations?: ProbeLinkCalibration[]
  // Validation
  validation_pass?: boolean
  threshold_db: number
  // Metadata
  calibrated_at: string
  calibrated_by?: string
}

export interface LinkValidityStatus {
  status: 'valid' | 'expiring_soon' | 'expired' | 'unknown'
  calibration_id?: string
  calibrated_at?: string
  valid_until?: string
  days_remaining?: number
  days_overdue?: number
  validation_pass?: boolean
  deviation_db?: number
  message?: string
}

// ==================== Validity Management ====================

export interface CalibrationTypeStatus {
  status: ValidityStatus
  calibration_id?: string
  calibrated_at?: string
  valid_until?: string
  days_remaining?: number
  days_overdue?: number
}

export interface ProbeCalibrationStatus {
  probe_id: number
  amplitude?: CalibrationTypeStatus
  phase?: CalibrationTypeStatus
  polarization?: CalibrationTypeStatus
  pattern?: CalibrationTypeStatus
  link?: CalibrationTypeStatus
  overall_status: ValidityStatus
}

export interface CalibrationRecommendation {
  probe_id: number
  calibration_type: CalibrationType
  action: string
  priority: 'critical' | 'high' | 'medium' | 'low'
  reason: string
}

export interface ExpiredCalibrationInfo {
  probe_id: number
  calibration_type: CalibrationType
  calibration_id: string
  expired_at: string
  days_overdue: number
}

export interface ExpiringCalibrationInfo {
  probe_id: number
  calibration_type: CalibrationType
  calibration_id: string
  valid_until: string
  days_remaining: number
}

export interface CalibrationValidityReport {
  total_probes: number
  valid_probes: number
  expired_probes: number
  expiring_soon_probes: number
  expired_calibrations: ExpiredCalibrationInfo[]
  expiring_soon_calibrations: ExpiringCalibrationInfo[]
  recommendations: CalibrationRecommendation[]
}

export interface InvalidateCalibrationRequest {
  reason: string
}

export interface InvalidateCalibrationResponse {
  success: boolean
  message: string
  calibration_id?: string
  calibration_type?: string
}

// ==================== Calibration History ====================

export interface CalibrationHistorySummary {
  [key: string]: unknown
}

export interface CalibrationHistoryItem {
  calibration_id: string
  calibration_type: CalibrationType
  calibrated_at: string
  calibrated_by?: string
  status: string
  summary: CalibrationHistorySummary
}

export interface CalibrationTrends {
  amplitude_drift_db_per_month?: number
  phase_drift_deg_per_month?: number
  stability_rating?: 'excellent' | 'good' | 'marginal' | 'poor'
}

export interface CalibrationHistoryResponse {
  probe_id: number
  history: CalibrationHistoryItem[]
  trends?: CalibrationTrends
}

// ==================== Comprehensive Data Query ====================

export interface ProbeCalibrationData {
  probe_id: number
  amplitude_calibration?: AmplitudeCalibrationResponse
  phase_calibration?: PhaseCalibrationResponse
  polarization_calibration?: PolarizationCalibrationResponse
  pattern_calibrations?: PatternCalibrationResponse[]
  link_calibration?: LinkCalibrationResponse
  validity_status: ProbeCalibrationStatus
}

// ==================== Expiring/Expired Calibrations Response ====================

export interface ExpiringCalibrationsResponse {
  days_threshold: number
  count: number
  calibrations: ExpiringCalibrationInfo[]
}

export interface ExpiredCalibrationsResponse {
  count: number
  calibrations: ExpiredCalibrationInfo[]
}
