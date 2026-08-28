import type {
  BaseStationSiteCertification,
  Cmw500Lte2x2Readiness,
} from '../../types/api.ts'

export type Cmw500ReadinessView = {
  status: Cmw500Lte2x2Readiness['status']
  color: 'green' | 'yellow' | 'gray'
  title: string
  message: string
  blocksDevelopment: false
}

export type FrozenCmwApproval = {
  instrument_connection_id: string
  enabled: boolean
  updated_at: string | null
}

export function describeCmw500Readiness(
  readiness: Cmw500Lte2x2Readiness | null | undefined,
  duplex: string | null | undefined,
  configMode: string | null | undefined,
  certification?: BaseStationSiteCertification | null,
): Cmw500ReadinessView {
  if (!readiness) {
    return {
      status: 'warning',
      color: 'yellow',
      title: 'CMW500 LTE 2×2 · UNKNOWN',
      message: 'UNKNOWN：尚未取得所选 LabProfile 的 CMW500 真机就绪快照；允许继续开发与诊断。',
      blocksDevelopment: false,
    }
  }
  if (readiness.status === 'not_applicable') {
    return {
      status: 'not_applicable',
      color: 'gray',
      title: '当前基站不是 CMW500',
      message: readiness.detail,
      blocksDevelopment: false,
    }
  }
  if (configMode === 'inherit' || readiness.status === 'diagnostic') {
    return {
      status: 'diagnostic',
      color: 'yellow',
      title: 'CMW500 LTE 2×2 · 诊断模式',
      message: '当前为调试继承/模拟态，仅诊断，不授予正式 KPI；允许继续开发与诊断。',
      blocksDevelopment: false,
    }
  }
  const duplexReady = duplex === 'tdd' ? readiness.tdd_ready : readiness.fdd_ready
  const certificationMatches = certification?.status === 'active'
    && certification.binding_digest === readiness.binding_digest
  if (duplexReady && certificationMatches) {
    return {
      status: 'ready',
      color: 'green',
      title: `CMW500 LTE 2×2 ${duplex === 'tdd' ? 'TDD' : 'FDD'} 已就绪`,
      message: readiness.detail,
      blocksDevelopment: false,
    }
  }
  return {
    status: 'warning',
    color: 'yellow',
    title: 'CMW500 LTE 2×2 · Warning',
    message: `${readiness.detail}；当前现场认证缺失、已撤销或与 binding 不匹配，只作 Warning，不阻止开发与诊断。`,
    blocksDevelopment: false,
  }
}

export function compareFrozenCmwApproval(
  readiness: Cmw500Lte2x2Readiness | null | undefined,
  executionConfig: unknown,
): string | null {
  if (!readiness) return null
  const approval = readFrozenCmwApproval(executionConfig)
  if (!approval) return null
  const unchanged = approval.instrument_connection_id === readiness.connection_id
    && approval.enabled === readiness.formal_enabled
    && approval.updated_at === readiness.formal_updated_at
  return unchanged
    ? null
    : '本次执行使用已冻结的 CMW500 正式能力授权；当前设置变化仅影响后续执行。'
}

export function readFrozenCmwApproval(
  executionConfig: unknown,
): FrozenCmwApproval | null {
  if (executionConfig === null || typeof executionConfig !== 'object') return null
  const freeze = (executionConfig as Record<string, unknown>)
    .base_station_adapter_profile_freeze
  if (freeze === null || typeof freeze !== 'object') return null
  const frozen = freeze as Record<string, unknown>
  const resolution = frozen.resolution
  if (
    resolution === null
    || typeof resolution !== 'object'
    || (resolution as Record<string, unknown>).adapter !== 'cmw500'
  ) return null
  const rawApproval = frozen.cmw500_lte_2x2_formal_capability
  if (rawApproval === null || typeof rawApproval !== 'object') return null
  const approval = rawApproval as Record<string, unknown>
  if (
    typeof approval.instrument_connection_id !== 'string'
    || typeof approval.enabled !== 'boolean'
    || (
      approval.updated_at !== null
      && typeof approval.updated_at !== 'string'
    )
  ) return null
  return {
    instrument_connection_id: approval.instrument_connection_id,
    enabled: approval.enabled,
    updated_at: approval.updated_at as string | null,
  }
}
