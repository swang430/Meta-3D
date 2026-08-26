import type {
  BaseStationAdapterProfile,
  Cmw500Lte2x2InternalRoute,
} from './api'

export type Cmw500RouteDraft = Cmw500Lte2x2InternalRoute

export const CMW500_ROUTE_FIELDS = [
  'pcc_bb_board',
  'rx_connector',
  'rx_converter',
  'tx1_connector',
  'tx1_converter',
  'tx2_connector',
  'tx2_converter',
] as const

export function emptyCmw500Route(): Cmw500RouteDraft {
  return {
    pcc_bb_board: '',
    rx_connector: '',
    rx_converter: '',
    tx1_connector: '',
    tx1_converter: '',
    tx2_connector: '',
    tx2_converter: '',
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasExactKeys(value: Record<string, unknown>): boolean {
  const expected = [...CMW500_ROUTE_FIELDS].sort()
  return Object.keys(value).sort().join('\0') === expected.join('\0')
}

export function readCmw500Route(value: unknown): Cmw500RouteDraft {
  if (!isRecord(value) || value.schema_version !== 1 || value.adapter !== 'cmw500') {
    return emptyCmw500Route()
  }
  const route = value.lte_2x2_internal_route
  if (!isRecord(route) || !hasExactKeys(route)) return emptyCmw500Route()
  const parsed = emptyCmw500Route()
  for (const key of CMW500_ROUTE_FIELDS) {
    const field = route[key]
    if (typeof field !== 'string' || !field.trim()) return emptyCmw500Route()
    parsed[key] = field.trim()
  }
  if (
    parsed.tx1_connector === parsed.tx2_connector
    || parsed.tx1_converter === parsed.tx2_converter
  ) {
    return emptyCmw500Route()
  }
  return parsed
}

export function buildCmw500AdapterProfile(
  draft: Cmw500RouteDraft,
): BaseStationAdapterProfile | null {
  const route = emptyCmw500Route()
  for (const key of CMW500_ROUTE_FIELDS) route[key] = draft[key].trim()
  const present = CMW500_ROUTE_FIELDS.filter((key) => route[key] !== '')
  if (present.length === 0) return null
  if (present.length !== CMW500_ROUTE_FIELDS.length) {
    throw new Error('CMW500 内部 2×2 route 必须完整填写七个字段')
  }
  if (route.tx1_connector === route.tx2_connector) {
    throw new Error('CMW500 TX1/TX2 connector 不得复用')
  }
  if (route.tx1_converter === route.tx2_converter) {
    throw new Error('CMW500 TX1/TX2 converter 不得复用')
  }
  return {
    schema_version: 1,
    adapter: 'cmw500',
    lte_2x2_internal_route: route,
  }
}
