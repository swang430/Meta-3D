import type { MultiFrequencyPathLossRequest } from '../../api/calibrationService'


export interface MultiFrequencyPathLossInput {
  chamberId: string
  probeIds: string
  polarization: 'V' | 'H'
  frequencyStartMhz: number
  frequencyStopMhz: number
  frequencyStepMhz: number
  sghModel: string
  sghGainDbi: number
  vnaId?: string
  calibratedBy: string
  mode: 'real' | 'mock' | null
}


export function buildMultiFrequencyPathLossRequest(
  input: MultiFrequencyPathLossInput,
): MultiFrequencyPathLossRequest {
  const chamberId = input.chamberId.trim()
  if (!chamberId) {
    throw new Error('当前 LabProfile 未绑定暗室 —— 请先选择绑定暗室的 LabProfile')
  }
  if (input.mode === null) {
    throw new Error('请选择真实仪表或模拟诊断模式')
  }

  const tokens = input.probeIds.split(',').map(value => value.trim())
  if (tokens.length === 0 || tokens.some(value => !/^\d+$/.test(value))) {
    throw new Error('探头 ID 必须是以逗号分隔的非负整数')
  }
  const probeIds = tokens.map(value => Number(value))
  if (new Set(probeIds).size !== probeIds.length) {
    throw new Error('探头 ID 不得重复')
  }

  if (
    !Number.isFinite(input.frequencyStartMhz)
    || !Number.isFinite(input.frequencyStopMhz)
    || input.frequencyStartMhz < 100
    || input.frequencyStopMhz > 100000
    || input.frequencyStopMhz <= input.frequencyStartMhz
  ) {
    throw new Error('终止频率必须大于起始频率，且范围须在 100–100000 MHz')
  }
  if (
    !Number.isFinite(input.frequencyStepMhz)
    || input.frequencyStepMhz < 1
    || input.frequencyStepMhz > 1000
  ) {
    throw new Error('频率步进必须在 1–1000 MHz')
  }

  const sghModel = input.sghModel.trim()
  const calibratedBy = input.calibratedBy.trim()
  if (!sghModel || !calibratedBy || !Number.isFinite(input.sghGainDbi)) {
    throw new Error('请完整填写标准增益喇叭与校准人员信息')
  }

  return {
    chamber_id: chamberId,
    probe_ids: probeIds,
    polarization: input.polarization,
    freq_start_mhz: input.frequencyStartMhz,
    freq_stop_mhz: input.frequencyStopMhz,
    freq_step_mhz: input.frequencyStepMhz,
    sgh_model: sghModel,
    sgh_gain_dbi: input.sghGainDbi,
    ...(input.vnaId?.trim() ? { vna_id: input.vnaId.trim() } : {}),
    calibrated_by: calibratedBy,
    use_mock: input.mode === 'mock',
  }
}
