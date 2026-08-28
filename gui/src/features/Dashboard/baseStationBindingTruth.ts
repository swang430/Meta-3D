import type { BaseStationBindingPreviewResponse } from '../../types/api'

export type BaseStationBindingLight = 'green' | 'yellow' | 'red'

export type BaseStationBindingTruth = {
  light: BaseStationBindingLight
  valueText: string
  detail: string
}

const shortDigest = (digest: string | null): string =>
  digest ? digest.slice(0, 12) : '无 digest'

export const formatBaseStationSyncTruth = (
  binding: BaseStationBindingPreviewResponse | null | undefined,
): string => {
  if (!binding) return 'BaseStation 解析快照缺失'
  const adapter = binding.adapter_id ?? '未解析 adapter'
  const model = binding.model_name ?? '未解析型号'
  const connection = binding.instrument_connection_id ?? '未解析 connection'
  return `${adapter} / ${model} · connection ${connection} · digest ${shortDigest(binding.binding_digest)}`
}

export const projectBaseStationBindingTruth = (
  binding: BaseStationBindingPreviewResponse | null | undefined,
): BaseStationBindingTruth => {
  if (!binding) {
    return {
      light: 'red',
      valueText: '未解析',
      detail: '服务器未返回所选 LabProfile 的 BaseStation binding 真值',
    }
  }
  if (binding.status === 'invalid') {
    return {
      light: 'red',
      valueText: '配置冲突',
      detail: binding.detail,
    }
  }
  if (binding.execution_mode === 'simulated' || binding.status === 'diagnostic_unbound') {
    return {
      light: 'yellow',
      valueText: '仅诊断',
      detail: `${binding.detail} · ${formatBaseStationSyncTruth(binding)}`,
    }
  }
  return {
    light: 'green',
    valueText: `${binding.adapter_id ?? 'BaseStation'} · 已解析`,
    detail: formatBaseStationSyncTruth(binding),
  }
}
