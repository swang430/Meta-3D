import { verifyClusters } from './clusterVerification.ts'

export type ProjectMode = 'conducted' | 'ota'

export function projectParameters(
  mode: ProjectMode,
  speed: string,
  rate: string,
) {
  if (mode === 'conducted') return { mode }
  const values = [speed, rate].map(Number)
  if (!values.every((value) => Number.isFinite(value) && value > 0)) return null
  return { mode, speed_m_s: values[0], rate_hz: values[1] }
}

export function readProject(
  data: {
    download_url?: unknown
    asc_count?: unknown
    results?: unknown
    evidence?: unknown
  },
  mode: ProjectMode,
  origin: string,
) {
  if (
    typeof data?.download_url !== 'string' ||
    !data.download_url.trim() ||
    typeof data.asc_count !== 'number' ||
    !Number.isSafeInteger(data.asc_count) ||
    data.asc_count < 0
  )
    throw Error('返回的工程缺少有效的下载地址或 ASC 文件数量。')
  const url = new URL(data.download_url, origin)
  if (!['http:', 'https:'].includes(url.protocol))
    throw Error('工程下载地址无效。')
  let report: ReturnType<typeof verifyClusters> | undefined
  let notice = ''
  if (mode === 'conducted') {
    if (data.results == null) notice = '未返回聚簇结果，无法核验。'
    else {
      try {
        report = verifyClusters(data.results, data.evidence)
      } catch (error) {
        notice =
          '无法核验：' +
          (error instanceof Error ? error.message : '结果格式无效')
      }
    }
  }
  return { url: url.href, count: data.asc_count, report, notice }
}
