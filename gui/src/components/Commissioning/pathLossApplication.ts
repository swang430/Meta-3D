export type PathLossApplicationStatus = 'applied' | 'not_applied' | 'unknown'
export type PathLossApplicationProvenance = 'real' | 'simulated' | 'unknown' | 'missing'
export type PathLossApplicationReason =
  | 'selected'
  | 'rejected_untrusted'
  | 'missing'
  | 'expired'
  | 'frequency_mismatch'
  | 'operating_mode_mismatch'
  | 'legacy_unclassified'

export interface PathLossApplication {
  schema_version: 1
  status: PathLossApplicationStatus
  provenance: PathLossApplicationProvenance
  reason: PathLossApplicationReason
  gate_mode: 'strict' | 'operator_bypass' | 'mock_not_applicable'
  certificate_id: string | null
  value_disclosure: 'verified' | 'hidden_unverified' | 'none'
}

export interface PathLossApplicationView {
  title: string
  message: string
  color: 'green' | 'yellow'
  certificateId: string | null
  sourceLabel: string
  showCompensationValue: boolean
}

const fields = [
  'certificate_id',
  'gate_mode',
  'provenance',
  'reason',
  'schema_version',
  'status',
  'value_disclosure',
]

const legacyUnknown = (): PathLossApplication => ({
  schema_version: 1,
  status: 'unknown',
  provenance: 'unknown',
  reason: 'legacy_unclassified',
  gate_mode: 'strict',
  certificate_id: null,
  value_disclosure: 'none',
})

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
)

export function parsePathLossApplication(value: unknown): PathLossApplication {
  if (!isRecord(value) || Object.keys(value).sort().join('|') !== fields.join('|')) {
    return legacyUnknown()
  }
  if (
    value.schema_version !== 1
    || !['strict', 'operator_bypass', 'mock_not_applicable'].includes(String(value.gate_mode))
  ) {
    return legacyUnknown()
  }

  const certificateId = value.certificate_id
  const hasCertificateId = typeof certificateId === 'string' && certificateId.length > 0
  if (value.status === 'applied') {
    if (
      !['real', 'simulated', 'unknown'].includes(String(value.provenance))
      || value.reason !== 'selected'
      || !hasCertificateId
    ) {
      return legacyUnknown()
    }
    const expectedDisclosure = value.provenance === 'real' ? 'verified' : 'hidden_unverified'
    if (value.value_disclosure !== expectedDisclosure) return legacyUnknown()
    return value as unknown as PathLossApplication
  }

  if (value.status === 'not_applied' && value.reason === 'rejected_untrusted') {
    if (
      !['simulated', 'unknown'].includes(String(value.provenance))
      || !hasCertificateId
      || value.value_disclosure !== 'none'
    ) {
      return legacyUnknown()
    }
    return value as unknown as PathLossApplication
  }

  if (
    value.status === 'not_applied'
    && ['missing', 'expired', 'frequency_mismatch', 'operating_mode_mismatch'].includes(String(value.reason))
    && value.provenance === 'missing'
    && value.certificate_id === null
    && value.value_disclosure === 'none'
  ) {
    return value as unknown as PathLossApplication
  }

  return legacyUnknown()
}

export function describePathLossApplication(value: unknown): PathLossApplicationView {
  const application = parsePathLossApplication(value)
  const showCompensationValue = (
    application.status === 'applied'
    && application.provenance === 'real'
    && application.value_disclosure === 'verified'
  )
  const sourceLabels: Record<PathLossApplicationProvenance, string> = {
    real: '真实来源',
    simulated: '模拟来源',
    unknown: '来源未知',
    missing: '无匹配证书',
  }
  let title = '路损应用状态未知'
  let message = '历史记录无法证明是否应用路损补偿；补偿数值不展示。'

  if (showCompensationValue) {
    title = '路损补偿已验证'
    message = '已应用经验证的路损补偿。'
  } else if (application.status === 'applied' && application.provenance === 'simulated') {
    title = '已应用模拟路损证书'
    message = '已应用模拟路损证书用于流程演练；数值不进入正式结果。'
  } else if (application.status === 'applied' && application.provenance === 'unknown') {
    title = '路损补偿已应用，但来源未知'
    message = '已应用路损补偿；证书来源未知，补偿数值不展示，结果不参与正式判定。'
  } else if (application.reason === 'rejected_untrusted') {
    title = '路损证书未应用'
    message = '检测到路损证书，但因来源未验证未应用；本次结果未补偿。'
  } else if (application.reason === 'expired') {
    title = '路损证书已过期'
    message = '匹配的路损证书已过期；本次结果未补偿。'
  } else if (application.reason === 'frequency_mismatch') {
    title = '路损证书频率不匹配'
    message = '现有证书与本次频率不匹配；本次结果未补偿。'
  } else if (application.reason === 'operating_mode_mismatch') {
    title = '路损证书 RF 模式不匹配'
    message = '现有证书与本次 RF operating mode 不匹配；本次结果未补偿。'
  } else if (application.reason === 'missing') {
    title = '未找到路损证书'
    message = '未找到匹配的路损证书；本次结果未补偿。'
  }

  return {
    title,
    message,
    color: showCompensationValue ? 'green' : 'yellow',
    certificateId: application.certificate_id,
    sourceLabel: sourceLabels[application.provenance],
    showCompensationValue,
  }
}

export function describePathLossSelection(reason: unknown, valid: boolean): string {
  if (valid && reason === 'selected') return '有效（已选中）'
  const labels: Record<string, string> = {
    missing: '未找到匹配证书',
    expired: '匹配证书已过期',
    frequency_mismatch: '证书频率不匹配',
    operating_mode_mismatch: '证书 RF 模式不匹配',
    selected: '已选中但未通过来源门',
  }
  return labels[String(reason)] ?? '状态未知'
}
