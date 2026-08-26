type MetricName = 'dl_throughput_mbps' | 'dl_bler_percent'

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

export function describeBaseStationMetric(
  projection: unknown,
  azimuthDeg: unknown,
  metricName: MetricName,
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
  const row = projection.find((candidate) => {
    if (candidate === null || typeof candidate !== 'object') return false
    const position = (candidate as Record<string, unknown>).position
    return position !== null
      && typeof position === 'object'
      && finiteNumber((position as Record<string, unknown>).azimuth_deg)
      && (position as Record<string, unknown>).azimuth_deg === azimuthDeg
  }) as Record<string, unknown> | undefined
  const metric = row?.[metricName]
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
