/**
 * P2-58 ②：就绪带消费 ① 的 channelEmulator binding 真值。
 *
 * 逐行镜像 `baseStationBindingTruth.ts` 的 `projectBaseStationBindingTruth`（:46-66）：
 * `invalid` → 红（判不出 = 吵的一侧，不许沦为灰）、`simulated` / `diagnostic_unbound` → 黄（仅诊断）、
 * 真驱动 `configured` → 绿。CE 没有现场认证层，所以绿不再被认证二次降级。
 */
import type { ChannelEmulatorBindingPreviewResponse } from '../../types/api'
import type { BaseStationBindingLight } from './baseStationBindingTruth'

export type ChannelEmulatorBindingTruth = {
  light: BaseStationBindingLight
  valueText: string
  detail: string
}

const shortDigest = (digest: string | null): string =>
  digest ? digest.slice(0, 12) : '无 digest'

export const formatChannelEmulatorSyncTruth = (
  binding: ChannelEmulatorBindingPreviewResponse | null | undefined,
): string => {
  if (!binding) return '信道仿真器解析快照缺失'
  const adapter = binding.adapter_id ?? '未解析 adapter'
  const model = binding.model_name ?? '未解析型号'
  const connection = binding.instrument_connection_id ?? '未解析 connection'
  const asset = binding.selected_asset_id ? ` · 资产 ${binding.selected_asset_id}` : ''
  return `${adapter} / ${model} · connection ${connection} · digest ${shortDigest(binding.binding_digest)}${asset}`
}

export const projectChannelEmulatorBindingTruth = (
  binding: ChannelEmulatorBindingPreviewResponse | null | undefined,
): ChannelEmulatorBindingTruth => {
  if (!binding) {
    return {
      light: 'red',
      valueText: '未解析',
      detail: '服务器未返回所选 LabProfile 的信道仿真器 binding 真值',
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
      detail: `${binding.detail} · ${formatChannelEmulatorSyncTruth(binding)}`,
    }
  }
  return {
    light: 'green',
    valueText: `${binding.adapter_id ?? '信道仿真器'} · 已解析`,
    detail: formatChannelEmulatorSyncTruth(binding),
  }
}
