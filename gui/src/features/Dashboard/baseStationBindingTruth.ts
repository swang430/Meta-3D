import type {
  BaseStationBindingPreviewResponse,
  BaseStationCompatibilityPreviewResponse,
} from '../../types/api'

export type BaseStationBindingLight = 'green' | 'yellow' | 'red'

export type ReadinessLight = BaseStationBindingLight | 'gray'

export type ReadinessVerdictCell = {
  key: string
  title: string
  light: ReadinessLight
  valueText: string
}

export type ReadinessVerdict = {
  light: BaseStationBindingLight
  text: string
}

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

export const projectBaseStationCompatibilityTruth = (
  compatibility: BaseStationCompatibilityPreviewResponse | null | undefined,
): BaseStationBindingTruth => {
  if (!compatibility) {
    return {
      light: 'red',
      valueText: '未评估',
      detail: '服务器未返回已保存 TestCase 与 BaseStation 的兼容性结论',
    }
  }
  if (compatibility.status === 'incompatible') {
    return {
      light: 'red',
      valueText: '不兼容',
      detail: compatibility.reasons.join('；') || compatibility.detail,
    }
  }
  if (compatibility.status === 'invalid' || compatibility.status === 'not_evaluated') {
    return {
      light: 'red',
      valueText: compatibility.status === 'invalid' ? '上下文无效' : '未评估',
      detail: compatibility.reasons.join('；') || compatibility.detail,
    }
  }
  if (
    compatibility.status === 'no_adapter'
    || compatibility.execution_mode === 'simulated'
  ) {
    return {
      light: 'yellow',
      valueText: '仅诊断',
      detail: compatibility.detail,
    }
  }
  if (
    compatibility.status === 'compatible'
    && compatibility.compatible === true
    && compatibility.execution_mode === 'real'
  ) {
    return {
      light: 'green',
      valueText: `${compatibility.requirements?.requested_rat.toUpperCase() ?? 'TestCase'} · 兼容`,
      detail: `${compatibility.detail} · binding ${shortDigest(compatibility.binding_digest)}`,
    }
  }
  return {
    light: 'red',
    valueText: '结论无效',
    detail: compatibility.detail,
  }
}

export const projectReadinessVerdict = (
  cells: ReadinessVerdictCell[],
  available: boolean,
): ReadinessVerdict => {
  if (!available) {
    return { light: 'red', text: '🔴 不可开测：HAL 未就绪' }
  }
  const blockers = cells.filter((cell) => cell.light === 'red')
  if (blockers.length > 0) {
    const reason = blockers
      .map((cell) => `${cell.title}（${cell.valueText}）`)
      .join('、')
    return { light: 'red', text: `🔴 不可开测：${reason}` }
  }
  const diagnosticCell = cells.find((cell) => cell.light === 'yellow')
  if (diagnosticCell) {
    return {
      light: 'yellow',
      text: `🟡 仅可诊断：${diagnosticCell.title}（${diagnosticCell.valueText}）`,
    }
  }
  return { light: 'green', text: '✅ 可开测' }
}
