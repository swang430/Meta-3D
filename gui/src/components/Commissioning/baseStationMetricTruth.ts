type MetricView = {
  text: string
  color: 'yellow' | undefined
  note: string | null
}

type LegacyUxmThroughput = {
  verified: unknown
  value: unknown
}

const finiteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)

const projectionRow = (projection: unknown, azimuthDeg: unknown) => {
  if (!Array.isArray(projection) || !finiteNumber(azimuthDeg)) return undefined
  return projection.find((candidate) => {
    if (candidate === null || typeof candidate !== 'object') return false
    const position = (candidate as Record<string, unknown>).position
    return position !== null
      && typeof position === 'object'
      && finiteNumber((position as Record<string, unknown>).azimuth_deg)
      && (position as Record<string, unknown>).azimuth_deg === azimuthDeg
  }) as Record<string, unknown> | undefined
}

const metricFromRow = (row: Record<string, unknown> | undefined, metricName: string) => {
  const metrics = row?.metrics
  if (metrics !== null && typeof metrics === 'object') {
    const metric = (metrics as Record<string, unknown>)[metricName]
    if (metric !== undefined) return metric
  }
  return row?.[metricName]
}

export function describeBaseStationMetric(
  projection: unknown,
  azimuthDeg: unknown,
  metricName: string,
  legacyUxmThroughput?: LegacyUxmThroughput,
): MetricView {
  if (!Array.isArray(projection) || !finiteNumber(azimuthDeg)) {
    if (
      projection === undefined
      && metricName === 'dl_throughput_mbps'
      && legacyUxmThroughput?.verified === true
      && finiteNumber(legacyUxmThroughput.value)
    ) {
      return {
        text: legacyUxmThroughput.value.toFixed(1),
        color: undefined,
        note: null,
      }
    }
    return { text: 'N/A', color: 'yellow', note: null }
  }
  const row = projectionRow(projection, azimuthDeg)
  const metric = metricFromRow(row, metricName)
  if (metric === null || typeof metric !== 'object') {
    return { text: 'N/A', color: 'yellow', note: null }
  }
  const trust = metric as Record<string, unknown>
  if (trust.status === 'trusted' && finiteNumber(trust.formal_value)) {
    return { text: trust.formal_value.toFixed(1), color: undefined, note: null }
  }
  if (trust.status === 'diagnostic' && finiteNumber(trust.diagnostic_value)) {
    return {
      text: trust.diagnostic_value.toFixed(1),
      color: 'yellow',
      note: '诊断值，非正式实测',
    }
  }
  return { text: 'N/A', color: 'yellow', note: null }
}

type RegisteredMetricView = MetricView & {
  key: string
  unitLabel: string
}

const unitView = (unit: unknown) => {
  switch (unit) {
    case 'mbps': return { digits: 1, label: 'Mbps' }
    case 'percent': return { digits: 1, label: '%' }
    case 'ratio': return { digits: 4, label: 'ratio' }
    case 'index': return { digits: 2, label: 'index' }
    case 'raw': return { digits: 4, label: 'raw' }
    default: return { digits: 4, label: 'N/A' }
  }
}

export function describeRegisteredBaseStationMetrics(
  projection: unknown,
  azimuthDeg: unknown,
): RegisteredMetricView[] {
  const row = projectionRow(projection, azimuthDeg)
  const metrics = row?.metrics
  if (metrics === null || typeof metrics !== 'object') return []
  return Object.keys(metrics as Record<string, unknown>).sort().map((key) => {
    const raw = (metrics as Record<string, unknown>)[key]
    const trust = raw !== null && typeof raw === 'object'
      ? raw as Record<string, unknown>
      : {}
    const unit = unitView(trust.unit)
    const formalValue = finiteNumber(trust.formal_value)
      ? trust.formal_value
      : null
    const diagnosticValue = finiteNumber(trust.diagnostic_value)
      ? trust.diagnostic_value
      : null
    const formal = trust.status === 'trusted' && formalValue !== null
    const diagnostic = trust.status === 'diagnostic'
      && diagnosticValue !== null
    return {
      key,
      text: formal
        ? formalValue.toFixed(unit.digits)
        : diagnostic
          ? diagnosticValue.toFixed(unit.digits)
          : 'N/A',
      color: diagnostic || !formal ? 'yellow' : undefined,
      note: diagnostic ? '诊断值，非正式实测' : null,
      unitLabel: unit.label,
    }
  })
}
