export function comparisonParameters(bandwidth: number, points: number, floor: number) {
  if (!Number.isFinite(bandwidth) || bandwidth <= 0 || bandwidth > 10000 ||
      !Number.isInteger(points) || points < 3 || points > 257 || points % 2 !== 1 ||
      !Number.isFinite(floor) || floor <= 0) throw Error('请填写正数带宽（不超过 10000 MHz）、3 至 257 的奇数频点数和正数幅度下限。')
  return { bandwidth_mhz: bandwidth, points, amplitude_floor: floor }
}
export function metric(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : '无有效点'
}
export function downloadLink(value: string) {
  if (typeof value !== 'string' || !/^\/api\/v1\/channel-assets\/mpdb-projects\/comparisons\/[a-zA-Z0-9-]+\/(report\.zip|points\.csv)$/.test(value)) throw Error('服务器返回的下载地址无效。')
  return value
}
export type Comparison = {
  schema: string; status: 'partial' | 'unverified'; formal_verdict: null;
  alignment_status: 'unverified'; simulated: false; hardware_verified: false;
  source_frame_count: number; unmatched_source_frames: number[];
  coverage: { phase_valid: number; phase_total: number; phase_fraction: number | null; matrix_valid: number; matrix_total: number; matrix_fraction: number | null };
  summary: Record<'Lauraycs' | 'Meta-3D', { matrix_nmse_median: number | null; matrix_nmse_p95: number | null; phase_error_p95_deg: number | null }>;
  source: Record<string, unknown>; message: string; member_row_order: unknown; polarization_basis: unknown;
  download_url: string; points_url: string;
}
export function readComparison(value: Comparison): Comparison {
  if (!value || value.schema !== 'mpdb-comparison/1' || !['partial','unverified'].includes(value.status) ||
      value.formal_verdict !== null || value.alignment_status !== 'unverified' || value.simulated !== false || value.hardware_verified !== false ||
      !Number.isInteger(value.source_frame_count) || value.source_frame_count < 1 ||
      !Array.isArray(value.unmatched_source_frames) || !value.unmatched_source_frames.every(Number.isInteger) ||
      !value.coverage || !value.summary?.Lauraycs || !value.summary?.['Meta-3D'] || !value.source || typeof value.message !== 'string')
    throw Error('服务器返回的比较结果缺少证据或状态不符合约定，无法展示。')
  downloadLink(value.download_url); downloadLink(value.points_url)
  return value
}
