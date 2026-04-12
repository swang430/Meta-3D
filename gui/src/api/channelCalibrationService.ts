/**
 * Channel Calibration API Service
 *
 * API client for channel calibration operations:
 * - Temporal calibration (PDP, RMS delay spread)
 * - Doppler calibration (Jakes spectrum)
 * - Spatial correlation calibration
 * - Angular spread calibration (APS fitting)
 * - Quiet zone calibration (field uniformity)
 * - EIS validation (3D sensitivity measurement)
 * - Session management
 * - Validity tracking
 */

import apiClient from './client'
import type {
  // Common
  CalibrationJobResponse,
  CalibrationProgress,
  ChannelCalibrationType,
  // Session
  StartCalibrationSessionRequest,
  CalibrationSessionResponse,
  UpdateSessionProgressRequest,
  CompleteSessionRequest,
  // Temporal
  StartTemporalCalibrationRequest,
  TemporalCalibrationResponse,
  // Doppler
  StartDopplerCalibrationRequest,
  DopplerCalibrationResponse,
  // Spatial Correlation
  StartSpatialCorrelationCalibrationRequest,
  SpatialCorrelationCalibrationResponse,
  // Angular Spread
  StartAngularSpreadCalibrationRequest,
  AngularSpreadCalibrationResponse,
  // Quiet Zone
  StartQuietZoneCalibrationRequest,
  QuietZoneCalibrationResponse,
  // EIS
  StartEISValidationRequest,
  EISValidationResponse,
  // History & Validity
  ChannelCalibrationHistoryResponse,
  ChannelCalibrationStatusSummary,
  InvalidateCalibrationRequest,
  InvalidateCalibrationResponse,
  ValidityStatus,
} from '../types/channelCalibration'

const BASE_URL = '/calibration/channel'

// ==================== Session Management APIs ====================

/**
 * Create a new calibration session
 */
export async function createCalibrationSession(
  request: StartCalibrationSessionRequest
): Promise<CalibrationSessionResponse> {
  const response = await apiClient.post<CalibrationSessionResponse>(
    `${BASE_URL}/sessions`,
    request
  )
  return response.data
}

/**
 * Get calibration session details
 */
export async function getCalibrationSession(
  sessionId: string
): Promise<CalibrationSessionResponse> {
  const response = await apiClient.get<CalibrationSessionResponse>(
    `${BASE_URL}/sessions/${sessionId}`
  )
  return response.data
}

/**
 * Update session progress
 */
export async function updateSessionProgress(
  sessionId: string,
  request: UpdateSessionProgressRequest
): Promise<CalibrationSessionResponse> {
  const response = await apiClient.patch<CalibrationSessionResponse>(
    `${BASE_URL}/sessions/${sessionId}/progress`,
    request
  )
  return response.data
}

/**
 * Complete a calibration session
 */
export async function completeSession(
  sessionId: string,
  request: CompleteSessionRequest
): Promise<CalibrationSessionResponse> {
  const response = await apiClient.post<CalibrationSessionResponse>(
    `${BASE_URL}/sessions/${sessionId}/complete`,
    request
  )
  return response.data
}

// ==================== Temporal Calibration APIs ====================

/**
 * Start temporal (time-domain) calibration
 * Validates PDP and RMS delay spread against 3GPP TR 38.901
 */
export async function startTemporalCalibration(
  request: StartTemporalCalibrationRequest
): Promise<CalibrationJobResponse> {
  const response = await apiClient.post<CalibrationJobResponse>(
    `${BASE_URL}/temporal/start`,
    request
  )
  return response.data
}

/**
 * Get temporal calibration details
 */
export async function getTemporalCalibration(
  calibrationId: string
): Promise<TemporalCalibrationResponse> {
  const response = await apiClient.get<TemporalCalibrationResponse>(
    `${BASE_URL}/temporal/${calibrationId}`
  )
  return response.data
}

/**
 * Get latest temporal calibration
 */
export async function getLatestTemporalCalibration(
  scenarioType?: string,
  scenarioCondition?: string
): Promise<TemporalCalibrationResponse> {
  const response = await apiClient.get<TemporalCalibrationResponse>(
    `${BASE_URL}/temporal/latest`,
    {
      params: {
        scenario_type: scenarioType,
        scenario_condition: scenarioCondition,
      },
    }
  )
  return response.data
}

// ==================== Doppler Calibration APIs ====================

/**
 * Start Doppler calibration
 * Validates Doppler spectrum against classical Jakes spectrum
 */
export async function startDopplerCalibration(
  request: StartDopplerCalibrationRequest
): Promise<CalibrationJobResponse> {
  const response = await apiClient.post<CalibrationJobResponse>(
    `${BASE_URL}/doppler/start`,
    request
  )
  return response.data
}

/**
 * Get Doppler calibration details
 */
export async function getDopplerCalibration(
  calibrationId: string
): Promise<DopplerCalibrationResponse> {
  const response = await apiClient.get<DopplerCalibrationResponse>(
    `${BASE_URL}/doppler/${calibrationId}`
  )
  return response.data
}

// ==================== Spatial Correlation Calibration APIs ====================

/**
 * Start spatial correlation calibration
 * Validates MIMO antenna spatial correlation against 3GPP Laplacian model
 */
export async function startSpatialCorrelationCalibration(
  request: StartSpatialCorrelationCalibrationRequest
): Promise<CalibrationJobResponse> {
  const response = await apiClient.post<CalibrationJobResponse>(
    `${BASE_URL}/spatial-correlation/start`,
    request
  )
  return response.data
}

/**
 * Get spatial correlation calibration details
 */
export async function getSpatialCorrelationCalibration(
  calibrationId: string
): Promise<SpatialCorrelationCalibrationResponse> {
  const response = await apiClient.get<SpatialCorrelationCalibrationResponse>(
    `${BASE_URL}/spatial-correlation/${calibrationId}`
  )
  return response.data
}

// ==================== Angular Spread Calibration APIs ====================

/**
 * Start angular spread calibration
 * Validates APS and RMS angular spread against 3GPP models
 */
export async function startAngularSpreadCalibration(
  request: StartAngularSpreadCalibrationRequest
): Promise<CalibrationJobResponse> {
  const response = await apiClient.post<CalibrationJobResponse>(
    `${BASE_URL}/angular-spread/start`,
    request
  )
  return response.data
}

/**
 * Get angular spread calibration details
 */
export async function getAngularSpreadCalibration(
  calibrationId: string
): Promise<AngularSpreadCalibrationResponse> {
  const response = await apiClient.get<AngularSpreadCalibrationResponse>(
    `${BASE_URL}/angular-spread/${calibrationId}`
  )
  return response.data
}

// ==================== Quiet Zone Calibration APIs ====================

/**
 * Start quiet zone calibration
 * Validates field amplitude and phase uniformity in the quiet zone
 */
export async function startQuietZoneCalibration(
  request: StartQuietZoneCalibrationRequest
): Promise<CalibrationJobResponse> {
  const response = await apiClient.post<CalibrationJobResponse>(
    `${BASE_URL}/quiet-zone/start`,
    request
  )
  return response.data
}

/**
 * Get quiet zone calibration details
 */
export async function getQuietZoneCalibration(
  calibrationId: string
): Promise<QuietZoneCalibrationResponse> {
  const response = await apiClient.get<QuietZoneCalibrationResponse>(
    `${BASE_URL}/quiet-zone/${calibrationId}`
  )
  return response.data
}

// ==================== EIS Validation APIs ====================

/**
 * Start EIS (Equivalent Isotropic Sensitivity) validation
 * End-to-end performance validation with 3D spatial scan
 */
export async function startEISValidation(
  request: StartEISValidationRequest
): Promise<CalibrationJobResponse> {
  const response = await apiClient.post<CalibrationJobResponse>(
    `${BASE_URL}/eis/start`,
    request
  )
  return response.data
}

/**
 * Get EIS validation details
 */
export async function getEISValidation(
  validationId: string
): Promise<EISValidationResponse> {
  const response = await apiClient.get<EISValidationResponse>(
    `${BASE_URL}/eis/${validationId}`
  )
  return response.data
}

// ==================== History & Status APIs ====================

/**
 * Get calibration history
 */
export async function getCalibrationHistory(params?: {
  calibration_type?: ChannelCalibrationType
  validation_pass?: boolean
  start_date?: string
  end_date?: string
  limit?: number
  offset?: number
}): Promise<ChannelCalibrationHistoryResponse> {
  const response = await apiClient.get<ChannelCalibrationHistoryResponse>(
    `${BASE_URL}/history`,
    { params }
  )
  return response.data
}

/**
 * Get channel calibration status summary
 * Returns status for all calibration types
 */
export async function getCalibrationStatus(): Promise<ChannelCalibrationStatusSummary> {
  const response = await apiClient.get<ChannelCalibrationStatusSummary>(
    `${BASE_URL}/status`
  )
  return response.data
}

/**
 * Invalidate a calibration record
 */
export async function invalidateCalibration(
  calibrationType: ChannelCalibrationType,
  calibrationId: string,
  request: InvalidateCalibrationRequest
): Promise<InvalidateCalibrationResponse> {
  const response = await apiClient.post<InvalidateCalibrationResponse>(
    `${BASE_URL}/${calibrationType}/${calibrationId}/invalidate`,
    request
  )
  return response.data
}

// ==================== Utility Functions ====================

/**
 * Check if all channel calibrations are valid
 */
export function isChannelCalibrationValid(
  status: ChannelCalibrationStatusSummary
): boolean {
  return status.overall_status === 'valid'
}

/**
 * Get calibration types that need attention (expired or expiring)
 */
export function getCalibrationAlerts(
  status: ChannelCalibrationStatusSummary
): Array<{ type: ChannelCalibrationType; status: ValidityStatus; nextDue?: string }> {
  const alerts: Array<{ type: ChannelCalibrationType; status: ValidityStatus; nextDue?: string }> = []

  const checkType = (
    type: ChannelCalibrationType,
    typeStatus: ValidityStatus,
    nextDue?: string
  ) => {
    if (typeStatus === 'expired' || typeStatus === 'expiring_soon') {
      alerts.push({ type, status: typeStatus, nextDue })
    }
  }

  checkType('temporal', status.temporal_status, status.temporal_next_due)
  checkType('doppler', status.doppler_status, status.doppler_next_due)
  checkType('spatial_correlation', status.spatial_correlation_status, status.spatial_correlation_next_due)
  checkType('angular_spread', status.angular_spread_status, status.angular_spread_next_due)
  checkType('quiet_zone', status.quiet_zone_status, status.quiet_zone_next_due)
  checkType('eis', status.eis_status, status.eis_next_due)

  return alerts
}

/**
 * Format validity status for display
 */
export function formatValidityStatus(status: ValidityStatus): {
  label: string
  color: 'green' | 'yellow' | 'red' | 'gray'
} {
  switch (status) {
    case 'valid':
      return { label: 'Valid', color: 'green' }
    case 'expiring_soon':
      return { label: 'Expiring Soon', color: 'yellow' }
    case 'expired':
      return { label: 'Expired', color: 'red' }
    case 'unknown':
    default:
      return { label: 'Unknown', color: 'gray' }
  }
}

/**
 * Get human-readable calibration type name
 */
export function getCalibrationTypeName(type: ChannelCalibrationType): string {
  const names: Record<ChannelCalibrationType, string> = {
    temporal: 'Temporal (PDP)',
    doppler: 'Doppler',
    spatial_correlation: 'Spatial Correlation',
    angular_spread: 'Angular Spread',
    quiet_zone: 'Quiet Zone',
    eis: 'EIS Validation',
  }
  return names[type] || type
}

/**
 * Get scenario display name
 */
export function getScenarioDisplayName(
  scenarioType: string,
  scenarioCondition: string
): string {
  const typeNames: Record<string, string> = {
    UMa: 'Urban Macro',
    UMi: 'Urban Micro',
    RMa: 'Rural Macro',
    InH: 'Indoor Hotspot',
  }

  const typeName = typeNames[scenarioType] || scenarioType
  return `${typeName} (${scenarioCondition})`
}

/**
 * Calculate days until expiration
 */
export function daysUntilExpiration(validUntil: string): number {
  const expirationDate = new Date(validUntil)
  const now = new Date()
  const diffMs = expirationDate.getTime() - now.getTime()
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24))
}

/**
 * Format calibration date for display
 */
export function formatCalibrationDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
