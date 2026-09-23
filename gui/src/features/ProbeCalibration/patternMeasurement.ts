import type {
  CalibrationJobResponse,
  PolarizationType,
  StartPatternCalibrationRequest,
} from '../../types/probeCalibration'

export interface PatternMeasurementInput {
  labProfileId: string
  chamberId: string
  operatingMode: string | null
  probeCount: number
  probeIds: string
  polarizations: PolarizationType[]
  frequencyMhz: number
  azimuthStepDeg: number
  elevationStepDeg: number
  measurementDistanceM: number
  ceTxPowerDbm: number
  sghGainDbi: number
  calibratedBy: string
  mode: 'real' | 'mock' | null
}

function requireFiniteRange(value: number, label: string, minimum: number, maximum: number): number {
  if (!Number.isFinite(value) || value < minimum || value > maximum) {
    throw new Error(`${label}必须在 ${minimum} 到 ${maximum} 之间`)
  }
  return value
}

function parseProbeIds(raw: string, probeCount: number): number[] {
  const tokens = raw.split(',').map((token) => token.trim())
  if (
    !Number.isInteger(probeCount)
    || probeCount <= 0
    || tokens.length === 0
    || tokens.some((token) => !/^\d+$/.test(token))
  ) {
    throw new Error('探头编号必须是以逗号分隔的非负整数')
  }
  const probeIds = tokens.map(Number)
  if (new Set(probeIds).size !== probeIds.length) {
    throw new Error('探头编号不能重复')
  }
  if (probeIds.some((probeId) => probeId >= probeCount)) {
    throw new Error(`探头编号必须小于当前暗室探头总数 ${probeCount}`)
  }
  return probeIds
}

export function buildPatternMeasurementRequest(
  input: PatternMeasurementInput,
): StartPatternCalibrationRequest {
  const labProfileId = input.labProfileId.trim()
  if (!labProfileId) throw new Error('必须选择当前 LabProfile')
  const chamberId = input.chamberId.trim()
  if (!chamberId) throw new Error('当前 LabProfile 未绑定暗室')
  const operatingMode = input.operatingMode?.trim()
  if (!operatingMode) throw new Error('必须选择运行模式')
  if (input.mode === null) throw new Error('必须显式选择真实或 Mock 模式')
  if (input.polarizations.length === 0) throw new Error('至少选择一种极化')
  const calibratedBy = input.calibratedBy.trim()
  if (!calibratedBy) throw new Error('必须填写操作员')

  return {
    lab_profile_id: labProfileId,
    chamber_id: chamberId,
    operating_mode: operatingMode,
    probe_ids: parseProbeIds(input.probeIds, input.probeCount),
    polarizations: input.polarizations,
    frequency_mhz: requireFiniteRange(input.frequencyMhz, '频率', 0.001, 100_000),
    azimuth_step_deg: requireFiniteRange(input.azimuthStepDeg, '方位角步进', 1, 30),
    elevation_step_deg: requireFiniteRange(input.elevationStepDeg, '俯仰角步进', 1, 30),
    measurement_distance_m: requireFiniteRange(input.measurementDistanceM, '测量距离', 0.5, 10),
    ce_tx_power_dbm: requireFiniteRange(input.ceTxPowerDbm, '信道仿真器功率', -200, 100),
    sgh_gain_dbi: requireFiniteRange(input.sghGainDbi, '标准增益喇叭增益', -100, 100),
    calibrated_by: calibratedBy,
    use_mock: input.mode === 'mock',
  }
}

export function assertPatternCalibrationJobResponse(
  response: CalibrationJobResponse,
  expectedUseMock: boolean,
): CalibrationJobResponse {
  if (typeof response.use_mock !== 'boolean') {
    throw new Error('校准响应的真实/Mock 来源缺失')
  }
  if (response.use_mock !== expectedUseMock) {
    throw new Error('校准响应来源与请求不一致')
  }
  if (response.status !== 'completed') {
    throw new Error(`方向图校准未完成：${response.message ?? response.status}`)
  }
  return response
}
