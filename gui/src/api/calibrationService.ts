import calibrationClient from './calibrationClient'

// ==================== 类型定义 ====================

export interface TRPCalibrationRequest {
  dut_model: string
  dut_serial: string
  reference_trp_dbm: number
  frequency_mhz: number
  theta_step_deg: number
  phi_step_deg: number
  tested_by: string
  reference_lab?: string
  ref_cert_number?: string
}

export interface TISCalibrationRequest {
  dut_model: string
  dut_serial: string
  reference_tis_dbm: number
  frequency_mhz: number
  theta_step_deg: number
  phi_step_deg: number
  tested_by: string
  reference_lab?: string
  ref_cert_number?: string
}

export interface RepeatabilityTestRequest {
  calibration_type: 'TRP' | 'TIS' | 'EIS'
  dut_model: string
  num_runs: number
  tested_by: string
}

export interface CalibrationResponse {
  id: string
  calibration_type: string
  dut_model: string
  dut_serial?: string
  frequency_mhz?: number
  measured_trp_dbm?: number
  measured_tis_dbm?: number
  reference_trp_dbm?: number
  reference_tis_dbm?: number
  error_db: number
  absolute_error_db: number
  validation_pass: boolean
  threshold_db: number
  num_probes_used: number
  tested_by: string
  tested_at: string
  reference_lab?: string
  ref_cert_number?: string
}

export interface RepeatabilityTestResponse {
  id: string
  calibration_type: string
  dut_model: string
  num_runs: number
  measurements: number[]
  mean: number
  std_dev: number
  validation_pass: boolean
  threshold: number
  tested_by: string
  tested_at: string
}

export interface CalibrationHistoryResponse {
  calibrations: CalibrationResponse[]
  total: number
}

export interface Certificate {
  id: string
  certificate_number: string
  calibration_id: string
  calibration_type: string
  system_info: {
    chamber_id: string
    probe_count: number
    frequency_range: string
  }
  lab_info: {
    name: string
    address: string
    accreditation: string
  }
  calibration_date: string
  valid_until: string
  issued_by: string
  signature: string
  created_at: string
}

export interface CertificateListResponse {
  certificates: Certificate[]
  total: number
}

// ==================== API 调用函数 ====================

/**
 * 执行 TRP 校准
 */
export async function executeTRPCalibration(request: TRPCalibrationRequest): Promise<CalibrationResponse> {
  const response = await calibrationClient.post<CalibrationResponse>('/calibration/trp', request)
  return response.data
}

/**
 * 执行 TIS 校准
 */
export async function executeTISCalibration(request: TISCalibrationRequest): Promise<CalibrationResponse> {
  const response = await calibrationClient.post<CalibrationResponse>('/calibration/tis', request)
  return response.data
}

/**
 * 执行重复性测试
 */
export async function executeRepeatabilityTest(request: RepeatabilityTestRequest): Promise<RepeatabilityTestResponse> {
  const response = await calibrationClient.post<RepeatabilityTestResponse>('/calibration/repeatability', request)
  return response.data
}

/**
 * 获取校准历史记录
 */
export async function fetchCalibrationHistory(params?: {
  limit?: number
  offset?: number
  calibration_type?: string
}): Promise<CalibrationHistoryResponse> {
  const response = await calibrationClient.get<CalibrationHistoryResponse>('/calibration/history', { params })
  return response.data
}

/**
 * 获取证书列表
 */
export async function fetchCertificates(params?: {
  limit?: number
  offset?: number
}): Promise<CertificateListResponse> {
  const response = await calibrationClient.get<CertificateListResponse>('/calibration/certificate', { params })
  return response.data
}

/**
 * 下载证书 PDF
 */
export async function downloadCertificatePDF(certificateId: string): Promise<Blob> {
  const response = await calibrationClient.get(`/calibration/certificate/${certificateId}/download`, {
    responseType: 'blob',
  })
  return response.data
}

/**
 * 获取单个证书详情
 */
export async function fetchCertificate(certificateId: string): Promise<Certificate> {
  const response = await calibrationClient.get<Certificate>(`/calibration/certificate/${certificateId}`)
  return response.data
}

/**
 * 获取系统校准统计
 */
export async function fetchCalibrationStats(): Promise<{
  total_calibrations: number
  trp_count: number
  tis_count: number
  repeatability_count: number
  valid_certificates: number
  expired_certificates: number
  average_trp_error: number
  average_tis_error: number
}> {
  const response = await calibrationClient.get('/calibration/stats')
  return response.data
}
