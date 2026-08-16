/**
 * Probe Calibration API Service
 *
 * API client for probe calibration operations:
 * - Amplitude calibration
 * - Phase calibration
 * - Polarization calibration
 * - Pattern calibration
 * - Link calibration
 * - Validity management
 */

import apiClient from './client'
import type {
  // Common
  CalibrationJobResponse,
  CalibrationProgress,
  CalibrationType,
  // Amplitude
  StartAmplitudeCalibrationRequest,
  AmplitudeCalibrationResponse,
  // Phase
  StartPhaseCalibrationRequest,
  PhaseCalibrationResponse,
  // Polarization
  StartPolarizationCalibrationRequest,
  PolarizationCalibrationResponse,
  // Pattern
  StartPatternCalibrationRequest,
  PatternCalibrationResponse,
  // Link
  StartLinkCalibrationRequest,
  LinkCalibrationResponse,
  LinkValidityStatus,
  // Validity
  ProbeCalibrationStatus,
  CalibrationValidityReport,
  InvalidateCalibrationRequest,
  InvalidateCalibrationResponse,
  ExpiringCalibrationsResponse,
  ExpiredCalibrationsResponse,
  // History
  CalibrationHistoryResponse,
  // Comprehensive
  ProbeCalibrationData,
} from '../types/probeCalibration'

const BASE_URL = '/calibration/probe'

// ==================== Amplitude Calibration APIs ====================

/**
 * Start amplitude calibration for specified probes
 */
export async function startAmplitudeCalibration(
  request: StartAmplitudeCalibrationRequest
): Promise<CalibrationJobResponse> {
  const response = await apiClient.post<CalibrationJobResponse>(
    `${BASE_URL}/amplitude/start`,
    request
  )
  return response.data
}

/**
 * Get latest amplitude calibration for a probe
 */
export async function getAmplitudeCalibration(
  chamberId: string,
  probeId: number
): Promise<AmplitudeCalibrationResponse> {
  const response = await apiClient.get<AmplitudeCalibrationResponse>(
    `${BASE_URL}/amplitude/${probeId}`,
    { params: { chamber_id: chamberId } }
  )
  return response.data
}

/**
 * Get amplitude calibration history for a probe
 */
export async function getAmplitudeCalibrationHistory(
  chamberId: string,
  probeId: number,
  limit: number = 20
): Promise<CalibrationHistoryResponse> {
  const response = await apiClient.get<CalibrationHistoryResponse>(
    `${BASE_URL}/amplitude/${probeId}/history`,
    { params: { chamber_id: chamberId, limit } }
  )
  return response.data
}

// ==================== Phase Calibration APIs ====================

/**
 * Start phase calibration for specified probes
 */
export async function startPhaseCalibration(
  request: StartPhaseCalibrationRequest
): Promise<CalibrationJobResponse> {
  const response = await apiClient.post<CalibrationJobResponse>(
    `${BASE_URL}/phase/start`,
    request
  )
  return response.data
}

/**
 * Get latest phase calibration for a probe
 */
export async function getPhaseCalibration(
  chamberId: string,
  probeId: number
): Promise<PhaseCalibrationResponse> {
  const response = await apiClient.get<PhaseCalibrationResponse>(
    `${BASE_URL}/phase/${probeId}`,
    { params: { chamber_id: chamberId } }
  )
  return response.data
}

/**
 * Get phase calibration history for a probe
 */
export async function getPhaseCalibrationHistory(
  chamberId: string,
  probeId: number,
  limit: number = 20
): Promise<CalibrationHistoryResponse> {
  const response = await apiClient.get<CalibrationHistoryResponse>(
    `${BASE_URL}/phase/${probeId}/history`,
    { params: { chamber_id: chamberId, limit } }
  )
  return response.data
}

// ==================== Polarization Calibration APIs ====================

/**
 * Start polarization calibration for specified probes
 */
export async function startPolarizationCalibration(
  request: StartPolarizationCalibrationRequest
): Promise<CalibrationJobResponse> {
  const response = await apiClient.post<CalibrationJobResponse>(
    `${BASE_URL}/polarization/start`,
    request
  )
  return response.data
}

/**
 * Get latest polarization calibration for a probe
 */
export async function getPolarizationCalibration(
  chamberId: string,
  probeId: number
): Promise<PolarizationCalibrationResponse> {
  const response = await apiClient.get<PolarizationCalibrationResponse>(
    `${BASE_URL}/polarization/${probeId}`,
    { params: { chamber_id: chamberId } }
  )
  return response.data
}

/**
 * Get polarization calibration history for a probe
 */
export async function getPolarizationCalibrationHistory(
  chamberId: string,
  probeId: number,
  limit: number = 20
): Promise<CalibrationHistoryResponse> {
  const response = await apiClient.get<CalibrationHistoryResponse>(
    `${BASE_URL}/polarization/${probeId}/history`,
    { params: { chamber_id: chamberId, limit } }
  )
  return response.data
}

// ==================== Pattern Calibration APIs ====================

/**
 * Start pattern calibration for specified probes
 */
export async function startPatternCalibration(
  request: StartPatternCalibrationRequest
): Promise<CalibrationJobResponse> {
  const response = await apiClient.post<CalibrationJobResponse>(
    `${BASE_URL}/pattern/start`,
    request
  )
  return response.data
}

/**
 * Get pattern calibrations for a probe
 * @param probeId - Probe ID (0-63)
 * @param frequencyMhz - Optional frequency filter
 */
export async function getPatternCalibration(
  chamberId: string,
  probeId: number,
  frequencyMhz?: number
): Promise<PatternCalibrationResponse[]> {
  const response = await apiClient.get<PatternCalibrationResponse[]>(
    `${BASE_URL}/pattern/${probeId}`,
    { params: { chamber_id: chamberId, frequency_mhz: frequencyMhz } }
  )
  return response.data
}

// ==================== Phase 2a-import: Pattern File Upload ====================

export interface ImportPatternFormParams {
  chamberId: string
  file: File
  probeId: number
  polarization: string
  frequencyMhz: number
  fileFormat?: 'ticra_cut' | 'csv' | 'json'
  probeModel?: string
  probeVendor?: string
  probeSerial?: string
  measuredBy?: string
  replaceExisting?: boolean
}

export interface ImportPatternResponse {
  success: boolean
  pattern_id?: string
  invalidated_id?: string
  peak_gain_dbi?: number
  peak_azimuth_deg?: number
  peak_elevation_deg?: number
  hpbw_azimuth_deg?: number
  hpbw_elevation_deg?: number
  front_to_back_ratio_db?: number
  num_az_points: number
  num_el_points: number
  warnings: string[]
  error?: string
}

/**
 * Upload a vendor-datasheet pattern file (.cut / .csv / .json) for a probe.
 * Calls multipart POST /api/v1/calibration/probe/pattern/import.
 */
export async function importProbePattern(
  params: ImportPatternFormParams
): Promise<ImportPatternResponse> {
  const fd = new FormData()
  fd.append('file', params.file)
  fd.append('chamber_id', params.chamberId)
  fd.append('probe_id', String(params.probeId))
  fd.append('polarization', params.polarization)
  fd.append('frequency_mhz', String(params.frequencyMhz))
  if (params.fileFormat) fd.append('file_format', params.fileFormat)
  if (params.probeModel) fd.append('probe_model', params.probeModel)
  if (params.probeVendor) fd.append('probe_vendor', params.probeVendor)
  if (params.probeSerial) fd.append('probe_serial', params.probeSerial)
  if (params.measuredBy) fd.append('measured_by', params.measuredBy)
  if (params.replaceExisting !== undefined)
    fd.append('replace_existing', params.replaceExisting ? 'true' : 'false')

  const response = await apiClient.post<ImportPatternResponse>(
    `${BASE_URL}/pattern/import`,
    fd,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  )
  return response.data
}

// ==================== Link Calibration APIs ====================

/**
 * Start link calibration
 */
export async function startLinkCalibration(
  request: StartLinkCalibrationRequest
): Promise<CalibrationJobResponse> {
  const response = await apiClient.post<CalibrationJobResponse>(
    `${BASE_URL}/link/start`,
    request
  )
  return response.data
}

/**
 * Get latest link calibration
 * @param calibrationType - Optional filter by calibration type
 */
export async function getLatestLinkCalibration(
  calibrationType?: string
): Promise<LinkCalibrationResponse> {
  const response = await apiClient.get<LinkCalibrationResponse>(
    `${BASE_URL}/link/latest`,
    { params: calibrationType ? { calibration_type: calibrationType } : undefined }
  )
  return response.data
}

/**
 * Get link calibration history
 */
export async function getLinkCalibrationHistory(
  calibrationType?: string,
  limit: number = 20
): Promise<LinkCalibrationResponse[]> {
  const response = await apiClient.get<LinkCalibrationResponse[]>(
    `${BASE_URL}/link/history`,
    { params: { calibration_type: calibrationType, limit } }
  )
  return response.data
}

/**
 * Check link calibration validity
 */
export async function checkLinkValidity(): Promise<LinkValidityStatus> {
  const response = await apiClient.get<LinkValidityStatus>(
    `${BASE_URL}/link/validity`
  )
  return response.data
}

// ==================== Validity Management APIs ====================

/**
 * Get calibration validity report for specified probes
 * @param probeIds - Comma-separated probe IDs, or undefined for default (0-31)
 */
export async function getValidityReport(
  chamberId: string,
  probeIds?: string
): Promise<CalibrationValidityReport> {
  const response = await apiClient.get<CalibrationValidityReport>(
    `${BASE_URL}/validity/report`,
    { params: { chamber_id: chamberId, probe_ids: probeIds } }
  )
  return response.data
}

/**
 * Get expiring calibrations
 * @param days - Days threshold (default 7)
 * @param calibrationType - Optional filter by calibration type
 */
export async function getExpiringCalibrations(
  chamberId: string,
  days: number = 7,
  calibrationType?: CalibrationType
): Promise<ExpiringCalibrationsResponse> {
  const response = await apiClient.get<ExpiringCalibrationsResponse>(
    `${BASE_URL}/validity/expiring`,
    { params: { chamber_id: chamberId, days, calibration_type: calibrationType } }
  )
  return response.data
}

/**
 * Get expired calibrations
 * @param calibrationType - Optional filter by calibration type
 */
export async function getExpiredCalibrations(
  chamberId: string,
  calibrationType?: CalibrationType
): Promise<ExpiredCalibrationsResponse> {
  const response = await apiClient.get<ExpiredCalibrationsResponse>(
    `${BASE_URL}/validity/expired`,
    { params: { chamber_id: chamberId, calibration_type: calibrationType } }
  )
  return response.data
}

/**
 * Get validity status for a single probe
 */
export async function getProbeValidity(
  chamberId: string,
  probeId: number
): Promise<ProbeCalibrationStatus> {
  const response = await apiClient.get<ProbeCalibrationStatus>(
    `${BASE_URL}/validity/${probeId}`,
    { params: { chamber_id: chamberId } }
  )
  return response.data
}

/**
 * Invalidate a calibration record
 */
export async function invalidateCalibration(
  calibrationType: CalibrationType,
  calibrationId: string,
  request: InvalidateCalibrationRequest
): Promise<InvalidateCalibrationResponse> {
  const response = await apiClient.post<InvalidateCalibrationResponse>(
    `${BASE_URL}/invalidate/${calibrationType}/${calibrationId}`,
    request
  )
  return response.data
}

// ==================== Comprehensive Data Query APIs ====================

/**
 * Get comprehensive calibration data for a probe
 */
export async function getProbeCalibrationData(
  chamberId: string,
  probeId: number
): Promise<ProbeCalibrationData> {
  const response = await apiClient.get<ProbeCalibrationData>(
    `${BASE_URL}/${probeId}/data`,
    { params: { chamber_id: chamberId } }
  )
  return response.data
}

// ==================== Calibration Progress API ====================

/**
 * Get calibration job progress (for long-running calibrations)
 * Note: This API may not be implemented in the current backend
 */
export async function getCalibrationProgress(
  jobId: string
): Promise<CalibrationProgress> {
  const response = await apiClient.get<CalibrationProgress>(
    `${BASE_URL}/jobs/${jobId}/progress`
  )
  return response.data
}

// ==================== Utility Functions ====================

/**
 * Check if a probe has valid calibration for all types
 */
export function isProbeFullyCalibrated(status: ProbeCalibrationStatus): boolean {
  return status.overall_status === 'valid'
}

/**
 * Get the most critical calibration issue for a probe
 */
export function getMostCriticalIssue(
  status: ProbeCalibrationStatus
): { type: CalibrationType; issue: string } | null {
  const types: CalibrationType[] = ['amplitude', 'phase', 'polarization', 'pattern', 'link']

  for (const type of types) {
    const cal = status[type]
    if (cal?.status === 'expired') {
      return { type, issue: `${type} calibration expired ${cal.days_overdue} days ago` }
    }
  }

  for (const type of types) {
    const cal = status[type]
    if (cal?.status === 'expiring_soon') {
      return { type, issue: `${type} calibration expires in ${cal.days_remaining} days` }
    }
  }

  return null
}

/**
 * Format calibration validity for display
 */
export function formatValidityStatus(status: string): {
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
 * Calculate days until expiration
 */
export function daysUntilExpiration(validUntil: string): number {
  const expirationDate = new Date(validUntil)
  const now = new Date()
  const diffMs = expirationDate.getTime() - now.getTime()
  return Math.ceil(diffMs / (1000 * 60 * 60 * 24))
}
