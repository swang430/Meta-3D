export interface RfKpiEvidenceView {
  verified: boolean
  color: 'green' | 'yellow'
  title: string
  message: string
}


export function describeRfKpiEvidence(formalVerified: unknown): RfKpiEvidenceView {
  if (formalVerified === true) {
    return {
      verified: true,
      color: 'green',
      title: 'RF KPI 已验证',
      message: 'RSRP、SINR 与 Rank 均有逐方位真实仪表证据。',
    }
  }
  return {
    verified: false,
    color: 'yellow',
    title: 'RF KPI 未验证',
    message: '缺少完整真实仪表证据；RSRP、SINR 与 Rank 仅显示 N/A，不参与正式判定。',
  }
}


export function formatRfKpiValue(
  value: unknown,
  formalVerified: boolean,
  precision: number,
): string {
  if (
    formalVerified !== true
    || typeof value !== 'number'
    || !Number.isFinite(value)
  ) {
    return 'N/A'
  }
  return value.toFixed(precision)
}
