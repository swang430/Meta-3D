import calibrationClient from './calibrationClient'

// ==================== Mock 配置 ====================

/**
 * Mock 模式配置
 * - 'auto': 自动模式 - 优先使用真实 API，失败时降级到 Mock
 * - 'force': 强制 Mock - 总是使用 Mock 数据（用于离线开发/演示）
 * - 'disabled': 禁用 Mock - 只使用真实 API（用于生产环境）
 */
const MOCK_MODE: 'auto' | 'force' | 'disabled' =
  (import.meta.env.VITE_CALIBRATION_MOCK_MODE as 'auto' | 'force' | 'disabled') || 'auto';

const USE_MOCK = MOCK_MODE === 'force';
const ALLOW_FALLBACK = MOCK_MODE === 'auto';

// ==================== 类型定义 ====================

export interface ProbeSelectionConfig {
  mode: 'all' | 'ring' | 'custom' | 'polarization'
  rings?: ('upper' | 'middle' | 'lower')[]
  probe_ids?: number[]
  polarizations?: ('V' | 'H')[]
}

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
  probe_selection?: ProbeSelectionConfig
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
  probe_selection?: ProbeSelectionConfig
}

export interface RepeatabilityTestRequest {
  calibration_type: 'TRP' | 'TIS' | 'EIS'
  dut_model: string
  num_runs: number
  tested_by: string
}

export interface QuietZoneCalibrationRequest {
  validation_type: 'field_uniformity' | 'spatial_correlation' | 'probe_coupling' | 'phase_stability'
  frequency_mhz: number
  tested_by: string
  grid_points?: number
}

export interface QuietZoneCalibrationResponse {
  id: string
  validation_type: string
  frequency_mhz: number
  validation_pass: boolean
  field_uniformity_db?: number
  field_mean_dbm?: number
  tested_at: string
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

export interface MultiFrequencyCalibrationRequest {
  calibration_type: 'TRP' | 'TIS'
  frequency_list_mhz: number[]
  dut_model: string
  dut_serial: string
  reference_trp_dbm?: number
  reference_tis_dbm?: number
  tested_by: string
}

export interface FrequencyResult {
  frequency_mhz: number
  measured_value_dbm: number
  error_db: number
  validation_pass: boolean
}

export interface MultiFrequencyCalibrationResponse {
  id: string
  calibration_type: string
  results: FrequencyResult[]
  overall_pass: boolean
  tested_at: string
  tested_by: string
}

// ==================== API 调用函数 ====================

/**
 * 执行 TRP 校准
 */
export async function executeTRPCalibration(request: TRPCalibrationRequest): Promise<CalibrationResponse> {
  // 强制 Mock 模式
  if (USE_MOCK) {
    console.log('[Mock] executeTRPCalibration - using mock data');
    await new Promise(resolve => setTimeout(resolve, 1500)); // 模拟网络延迟
    return generateMockTRPResult(request);
  }

  // 尝试真实 API，失败时降级到 Mock
  try {
    const response = await calibrationClient.post<CalibrationResponse>('/calibration/trp', request);
    return response.data;
  } catch (error) {
    if (ALLOW_FALLBACK) {
      console.warn('[Mock Fallback] executeTRPCalibration - API Service unavailable, using mock data:', error);
      return generateMockTRPResult(request);
    }
    throw error;
  }
}

/**
 * 执行 TIS 校准
 */
export async function executeTISCalibration(request: TISCalibrationRequest): Promise<CalibrationResponse> {
  if (USE_MOCK) {
    console.log('[Mock] executeTISCalibration - using mock data');
    await new Promise(resolve => setTimeout(resolve, 1500));
    return generateMockTISResult(request);
  }

  try {
    const response = await calibrationClient.post<CalibrationResponse>('/calibration/tis', request);
    return response.data;
  } catch (error) {
    if (ALLOW_FALLBACK) {
      console.warn('[Mock Fallback] executeTISCalibration - API Service unavailable, using mock data:', error);
      return generateMockTISResult(request);
    }
    throw error;
  }
}

/**
 * 执行重复性测试
 */
export async function executeRepeatabilityTest(request: RepeatabilityTestRequest): Promise<RepeatabilityTestResponse> {
  if (USE_MOCK) {
    console.log('[Mock] executeRepeatabilityTest - using mock data');
    await new Promise(resolve => setTimeout(resolve, 2000)); // 稍长，模拟多次测量
    return generateMockRepeatabilityResult(request);
  }

  try {
    const response = await calibrationClient.post<RepeatabilityTestResponse>('/calibration/repeatability', request);
    return response.data;
  } catch (error) {
    if (ALLOW_FALLBACK) {
      console.warn('[Mock Fallback] executeRepeatabilityTest - API Service unavailable, using mock data:', error);
      return generateMockRepeatabilityResult(request);
    }
    throw error;
  }
}

/**
 * 执行静区质量验证
 */
export async function executeQuietZoneCalibration(request: QuietZoneCalibrationRequest): Promise<QuietZoneCalibrationResponse> {
  if (USE_MOCK) {
    console.log('[Mock] executeQuietZoneCalibration - using mock data');
    await new Promise(resolve => setTimeout(resolve, 2000));
    return generateMockQuietZoneResult(request);
  }

  try {
    const response = await calibrationClient.post<QuietZoneCalibrationResponse>('/calibration/quiet-zone', request);
    return response.data;
  } catch (error) {
    if (ALLOW_FALLBACK) {
      console.warn('[Mock Fallback] executeQuietZoneCalibration - using mock data:', error);
      return generateMockQuietZoneResult(request);
    }
    throw error;
  }
}

/**
 * 获取校准历史记录
 */
export async function fetchCalibrationHistory(params?: {
  limit?: number
  offset?: number
  calibration_type?: string
}): Promise<CalibrationHistoryResponse> {
  if (USE_MOCK) {
    console.log('[Mock] fetchCalibrationHistory - using mock data');
    await new Promise(resolve => setTimeout(resolve, 300));
    return generateMockCalibrationHistory(params);
  }

  try {
    const response = await calibrationClient.get<CalibrationHistoryResponse>('/calibration/history', { params });
    return response.data;
  } catch (error) {
    if (ALLOW_FALLBACK) {
      console.warn('[Mock Fallback] fetchCalibrationHistory - API Service unavailable, using mock data:', error);
      return generateMockCalibrationHistory(params);
    }
    throw error;
  }
}

/**
 * 获取证书列表
 */
export async function fetchCertificates(params?: {
  limit?: number
  offset?: number
}): Promise<CertificateListResponse> {
  if (USE_MOCK) {
    console.log('[Mock] fetchCertificates - using mock data');
    await new Promise(resolve => setTimeout(resolve, 300));
    return generateMockCertificates(params);
  }

  try {
    const response = await calibrationClient.get<CertificateListResponse>('/calibration/certificate', { params });
    return response.data;
  } catch (error) {
    if (ALLOW_FALLBACK) {
      console.warn('[Mock Fallback] fetchCertificates - API Service unavailable, using mock data:', error);
      return generateMockCertificates(params);
    }
    throw error;
  }
}

/**
 * 下载证书 PDF
 */
export async function downloadCertificatePDF(certificateId: string): Promise<Blob> {
  if (USE_MOCK) {
    console.log('[Mock] downloadCertificatePDF - generating mock PDF');
    await new Promise(resolve => setTimeout(resolve, 500));
    // 生成一个简单的 Mock PDF (空白 PDF)
    const mockPDF = new Blob(['%PDF-1.4\nMock Certificate PDF'], { type: 'application/pdf' });
    return mockPDF;
  }

  try {
    const response = await calibrationClient.get(`/calibration/certificate/${certificateId}/download`, {
      responseType: 'blob',
    });
    return response.data;
  } catch (error) {
    if (ALLOW_FALLBACK) {
      console.warn('[Mock Fallback] downloadCertificatePDF - API Service unavailable, using mock PDF:', error);
      const mockPDF = new Blob(['%PDF-1.4\nMock Certificate PDF'], { type: 'application/pdf' });
      return mockPDF;
    }
    throw error;
  }
}

/**
 * 获取单个证书详情
 */
export async function fetchCertificate(certificateId: string): Promise<Certificate> {
  if (USE_MOCK) {
    console.log('[Mock] fetchCertificate - using mock data');
    await new Promise(resolve => setTimeout(resolve, 200));
    const mockCerts = generateMockCertificates();
    return mockCerts.certificates[0]; // 返回第一个 Mock 证书
  }

  try {
    const response = await calibrationClient.get<Certificate>(`/calibration/certificate/${certificateId}`);
    return response.data;
  } catch (error) {
    if (ALLOW_FALLBACK) {
      console.warn('[Mock Fallback] fetchCertificate - API Service unavailable, using mock data:', error);
      const mockCerts = generateMockCertificates();
      return mockCerts.certificates[0];
    }
    throw error;
  }
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
  if (USE_MOCK) {
    console.log('[Mock] fetchCalibrationStats - using mock data');
    await new Promise(resolve => setTimeout(resolve, 200));
    return generateMockStats();
  }

  try {
    const response = await calibrationClient.get('/calibration/stats');
    return response.data;
  } catch (error) {
    if (ALLOW_FALLBACK) {
      console.warn('[Mock Fallback] fetchCalibrationStats - API Service unavailable, using mock data:', error);
      return generateMockStats();
    }
    throw error;
  }
}

/**
 * 执行多频点校准
 */
export async function executeMultiFrequencyCalibration(
  request: MultiFrequencyCalibrationRequest
): Promise<MultiFrequencyCalibrationResponse> {
  if (USE_MOCK) {
    console.log('[Mock] executeMultiFrequencyCalibration');
    await new Promise(r => setTimeout(r, 2500));
    return generateMockMultiFrequencyResult(request);
  }

  try {
    const response = await calibrationClient.post<MultiFrequencyCalibrationResponse>(
      '/calibration/multi-frequency',
      request
    );
    return response.data;
  } catch (error) {
    if (ALLOW_FALLBACK) {
      console.warn('[Mock Fallback] executeMultiFrequencyCalibration:', error);
      return generateMockMultiFrequencyResult(request);
    }
    throw error;
  }
}

// ==================== Mock 数据生成函数 ====================

/**
 * 生成 Mock TRP 校准结果
 */
function generateMockTRPResult(request: TRPCalibrationRequest): CalibrationResponse {
  // 模拟测量误差 (高斯分布, σ=0.15 dB)
  const error_db = (Math.random() - 0.5) * 0.3 + (Math.random() - 0.5) * 0.1;
  const measured_trp_dbm = request.reference_trp_dbm + error_db;
  const absolute_error_db = Math.abs(error_db);
  const threshold_db = 0.5;

  return {
    id: crypto.randomUUID(),
    calibration_type: 'TRP',
    dut_model: request.dut_model,
    dut_serial: request.dut_serial,
    frequency_mhz: request.frequency_mhz,
    measured_trp_dbm,
    reference_trp_dbm: request.reference_trp_dbm,
    error_db,
    absolute_error_db,
    validation_pass: absolute_error_db < threshold_db,
    threshold_db,
    num_probes_used: Math.floor(360 / request.phi_step_deg) * Math.floor(180 / request.theta_step_deg),
    tested_by: request.tested_by,
    tested_at: new Date().toISOString(),
    reference_lab: request.reference_lab,
    ref_cert_number: request.ref_cert_number,
  };
}

/**
 * 生成 Mock TIS 校准结果
 */
function generateMockTISResult(request: TISCalibrationRequest): CalibrationResponse {
  // TIS 误差稍大 (σ=0.25 dB)
  const error_db = (Math.random() - 0.5) * 0.5 + (Math.random() - 0.5) * 0.2;
  const measured_tis_dbm = request.reference_tis_dbm + error_db;
  const absolute_error_db = Math.abs(error_db);
  const threshold_db = 1.0;

  return {
    id: crypto.randomUUID(),
    calibration_type: 'TIS',
    dut_model: request.dut_model,
    dut_serial: request.dut_serial,
    frequency_mhz: request.frequency_mhz,
    measured_tis_dbm,
    reference_tis_dbm: request.reference_tis_dbm,
    error_db,
    absolute_error_db,
    validation_pass: absolute_error_db < threshold_db,
    threshold_db,
    num_probes_used: Math.floor(360 / request.phi_step_deg) * Math.floor(180 / request.theta_step_deg),
    tested_by: request.tested_by,
    tested_at: new Date().toISOString(),
    reference_lab: request.reference_lab,
    ref_cert_number: request.ref_cert_number,
  };
}

/**
 * 生成 Mock 重复性测试结果
 */
function generateMockRepeatabilityResult(request: RepeatabilityTestRequest): RepeatabilityTestResponse {
  // 生成多次测量值 (标准差 0.1-0.2 dB)
  const base_value = request.calibration_type === 'TRP' ? 10.0 : -90.0;
  const std_dev = 0.1 + Math.random() * 0.1; // 0.1 ~ 0.2 dB

  const measurements = Array.from({ length: request.num_runs }, () => {
    const gaussian = (Math.random() + Math.random() + Math.random() + Math.random() - 2) / 2; // Box-Muller近似
    return base_value + gaussian * std_dev;
  });

  const mean = measurements.reduce((a, b) => a + b, 0) / measurements.length;
  const threshold = request.calibration_type === 'TRP' ? 0.3 : 0.5;

  return {
    id: crypto.randomUUID(),
    calibration_type: request.calibration_type,
    dut_model: request.dut_model,
    num_runs: request.num_runs,
    measurements,
    mean,
    std_dev,
    validation_pass: std_dev < threshold,
    threshold,
    tested_by: request.tested_by,
    tested_at: new Date().toISOString(),
  };
}

/**
 * 生成 Mock 校准历史记录
 */
function generateMockCalibrationHistory(params?: {
  limit?: number;
  offset?: number;
  calibration_type?: string;
}): CalibrationHistoryResponse {
  const limit = params?.limit || 10;
  const offset = params?.offset || 0;

  // 生成 Mock 历史记录
  const mockCalibrations: CalibrationResponse[] = [
    {
      id: crypto.randomUUID(),
      calibration_type: 'TRP',
      dut_model: 'Standard Dipole λ/2',
      dut_serial: 'DIP-2024-001',
      frequency_mhz: 3500,
      measured_trp_dbm: 10.48,
      reference_trp_dbm: 10.5,
      error_db: -0.02,
      absolute_error_db: 0.02,
      validation_pass: true,
      threshold_db: 0.5,
      num_probes_used: 336,
      tested_by: 'Test Engineer',
      tested_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: crypto.randomUUID(),
      calibration_type: 'TIS',
      dut_model: 'Standard Dipole λ/2',
      dut_serial: 'DIP-2024-001',
      frequency_mhz: 2600,
      measured_tis_dbm: -90.35,
      reference_tis_dbm: -90.2,
      error_db: -0.15,
      absolute_error_db: 0.15,
      validation_pass: true,
      threshold_db: 1.0,
      num_probes_used: 336,
      tested_by: 'Test Engineer',
      tested_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    },
  ];

  // 过滤和分页
  let filtered = mockCalibrations;
  if (params?.calibration_type) {
    filtered = filtered.filter(c => c.calibration_type === params.calibration_type);
  }

  return {
    calibrations: filtered.slice(offset, offset + limit),
    total: filtered.length,
  };
}

/**
 * 生成 Mock 证书列表
 */
function generateMockCertificates(params?: {
  limit?: number;
  offset?: number;
}): CertificateListResponse {
  const limit = params?.limit || 10;
  const offset = params?.offset || 0;

  const mockCertificates: Certificate[] = [
    {
      id: crypto.randomUUID(),
      certificate_number: 'MPAC-CAL-2025-001',
      calibration_id: crypto.randomUUID(),
      calibration_type: 'TRP',
      system_info: {
        chamber_id: 'MPAC-Chamber-01',
        probe_count: 32,
        frequency_range: '600-7250 MHz',
      },
      lab_info: {
        name: 'Meta-3D OTA Laboratory',
        address: 'China',
        accreditation: 'CNAS L12345',
      },
      calibration_date: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
      valid_until: new Date(Date.now() + 335 * 24 * 60 * 60 * 1000).toISOString(),
      issued_by: 'Chief Engineer',
      signature: 'SHA256:' + crypto.randomUUID().replace(/-/g, ''),
      created_at: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    },
  ];

  return {
    certificates: mockCertificates.slice(offset, offset + limit),
    total: mockCertificates.length,
  };
}

/**
 * 生成 Mock 统计数据
 */
function generateMockStats() {
  return {
    total_calibrations: 156,
    trp_count: 78,
    tis_count: 65,
    repeatability_count: 13,
    valid_certificates: 12,
    expired_certificates: 1,
    average_trp_error: 0.12,
    average_tis_error: 0.28,
  };
}

/**
 * 生成 Mock 静区质量验证结果
 */
function generateMockQuietZoneResult(request: QuietZoneCalibrationRequest): QuietZoneCalibrationResponse {
  const uniformity_db = 0.5 + Math.random() * 0.6; // 0.5-1.1 dB

  return {
    id: crypto.randomUUID(),
    validation_type: request.validation_type,
    frequency_mhz: request.frequency_mhz,
    validation_pass: uniformity_db < 1.0,
    field_uniformity_db: uniformity_db,
    field_mean_dbm: -30 + (Math.random() - 0.5) * 2,
    tested_at: new Date().toISOString(),
    tested_by: request.tested_by,
  };
}

/**
 * 生成 Mock 多频点校准结果
 */
function generateMockMultiFrequencyResult(
  request: MultiFrequencyCalibrationRequest
): MultiFrequencyCalibrationResponse {
  const results = request.frequency_list_mhz.map(freq => {
    const freq_factor = 1.0 - Math.abs(freq - 3500) / 10000;
    const error = (Math.random() - 0.5) * 0.4 * (2 - freq_factor);
    const ref_value = request.calibration_type === 'TRP'
      ? (request.reference_trp_dbm || 10.0)
      : (request.reference_tis_dbm || -90.0);

    return {
      frequency_mhz: freq,
      measured_value_dbm: ref_value + error,
      error_db: error,
      validation_pass: Math.abs(error) < (request.calibration_type === 'TRP' ? 0.5 : 1.0),
    };
  });

  return {
    id: crypto.randomUUID(),
    calibration_type: request.calibration_type,
    results,
    overall_pass: results.every(r => r.validation_pass),
    tested_at: new Date().toISOString(),
    tested_by: request.tested_by,
  };
}
