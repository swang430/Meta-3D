type QuietZoneEvidence = {
  schema_version: 1
  status: 'unavailable' | 'diagnostic_proxy'
  source: 'missing' | 'probe_pattern_peak_spread'
  formal_verified: false
  measured_ripple_db: null
  proxy_ripple_db: number | null
  calibration_id: null
}

const EVIDENCE_KEYS = [
  'calibration_id',
  'formal_verified',
  'measured_ripple_db',
  'proxy_ripple_db',
  'schema_version',
  'source',
  'status',
].sort()

function parseQuietZoneEvidence(value: unknown): QuietZoneEvidence | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  if (Object.keys(record).sort().join('|') !== EVIDENCE_KEYS.join('|')) return null
  if (record.schema_version !== 1 || record.formal_verified !== false) return null
  if (record.measured_ripple_db !== null || record.calibration_id !== null) return null

  if (
    record.status === 'unavailable'
    && record.source === 'missing'
    && record.proxy_ripple_db === null
  ) return record as QuietZoneEvidence

  if (
    record.status === 'diagnostic_proxy'
    && record.source === 'probe_pattern_peak_spread'
    && typeof record.proxy_ripple_db === 'number'
    && Number.isFinite(record.proxy_ripple_db)
  ) return record as QuietZoneEvidence

  return null
}

export function describePrecheckOutcome(
  value: unknown,
  evidenceValue: unknown,
  operationalReady: unknown,
) {
  const formalVerified = parseQuietZoneEvidence(evidenceValue)?.formal_verified as boolean | undefined
  if (value === true && formalVerified === true) {
    return {
      color: 'green',
      title: '预检通过',
      message: '所有系统、校准与静区测量证据均满足正式测试要求。',
    }
  }
  if (value === false && operationalReady === false) {
    return {
      color: 'red',
      title: '预检失败',
      message: '系统存在异常，请检查以下信息。',
    }
  }
  return {
    color: 'yellow',
    title: '预检未判定',
    message: '运行条件已检查，但缺少正式静区测量证据。诊断流程可继续。',
  }
}

export function describePrecheckMessages(value: unknown, evidenceValue: unknown): string[] {
  const formalVerified = parseQuietZoneEvidence(evidenceValue)?.formal_verified as boolean | undefined
  if (formalVerified === true && Array.isArray(value)) {
    return value.filter((message): message is string => typeof message === 'string')
  }
  return [
    '静区结论未判定：无权威多点场扫描证据；历史提示未作为正式证据发布。',
  ]
}

export function describeQuietZoneEvidence(value: unknown) {
  const evidence = parseQuietZoneEvidence(value)
  const proxy = evidence?.status === 'diagnostic_proxy'
    ? evidence.proxy_ripple_db
    : null
  return {
    verified: false,
    formalRipple: 'N/A',
    proxyRipple: typeof proxy === 'number' ? `${proxy.toFixed(2)} dB` : null,
    label: proxy !== null
      ? 'ProbePattern 峰值离散诊断代理，非静区实测'
      : '无权威多点场扫描证据',
  }
}
