import { readBundle } from './imtBundle.ts'
import { verifyClusters } from './clusterVerification.ts'

export type ProjectMode = 'conducted' | 'ota'
export type TimingMode = '' | 'constant' | 'segments' | 'original'

export function durations(text: string) {
  return text.trim().split(/[\s,，;；]+/).map(Number)
}

export function projectParameters(
  mode: ProjectMode,
  speed: string,
  rate: string,
  timing: TimingMode = 'constant',
  segmentText = '',
  count = 0,
) {
  if (mode === 'conducted') return { mode }
  const positive = (value: number) => Number.isFinite(value) && value > 0
  if (rate !== "standard" && rate !== "dense") return null
  const rate_quality = rate
  if (timing === 'original') return {mode, rate_quality}
  if (timing === 'segments') {
    const values = durations(segmentText)
    return count > 0 && values.length === count && values.every(positive)
      ? {mode, rate_quality, segment_durations_s:values} : null
  }
  return timing === 'constant' && positive(Number(speed)) ? {mode, rate_quality, speed_m_s:Number(speed)} : null
}

export function readProject(
  data: {
    download_url?: unknown
    asc_count?: unknown
    manifests?: Record<string, unknown>
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
  const summaries = (mode === 'ota' ? ['baseline', 'dynamic'] : ['conducted']).map((role) => {
    const label = role === 'dynamic' ? '动态工程' : role === 'baseline' ? '源帧工程' : '传导工程'
    try {
      const manifest = data.manifests?.[role]
      if (!manifest) throw Error('缺少本次生成清单')
      const bundle = readBundle(manifest, mode)
      if ((role === 'dynamic') !== Boolean(bundle.phaseSummary))
        throw Error('清单与工程类型不符')
      if (role !== 'baseline' && bundle.links.length !== data.asc_count)
        throw Error('清单与生成的文件数量不符')
      const summary = label + '清单：' + bundle.links.length + ' 个 ASC 文件，' +
        bundle.frames + ' 帧，每帧 ' + bundle.taps + ' 个抽头，文件头更新率 ' + bundle.rate + ' Hz。更新率依据：'+bundle.rateSource+'。'
      if (role === 'baseline') {
        const usable = bundle.metrics.filter(m => m.field_nmse !== null && m.power_ratio !== null)
        const maximum = usable.reduce((max, row) => Math.max(max, row.field_nmse!), 0)
        const probeCount = bundle.links.length / (2 * new Set(bundle.links.map(link => link.tx)).size)
        return summary + '探头布局含 '+probeCount+' 个双极化探头。' + (usable.length ? '场误差和功率比均有记录的 ' + usable.length +
          ' 项中，最大归一化场均方误差为 ' + maximum.toExponential(2) + '。' : '') +
          (usable.length < bundle.metrics.length ? '缺少完整对照数值的 ' +
            (bundle.metrics.length - usable.length) + ' 项未核验。' : '')
      }
      if (role === 'conducted') {
        const basis = (manifest as {power_basis?: {tx_power_dbm?: Record<string,number>; tx_psd_dbm_per_hz?: Record<string,number>}}).power_basis
        return summary + (basis?.tx_power_dbm ? '已登记发射参考。各路载频预测见 carrier-power.json，依据缺失的链路留空。' :
          basis?.tx_psd_dbm_per_hz ? '已登记发射功率谱；缺少单音发射功率，载频预测留空。' : '缺发射参考，只能使用相对系数。')
      }
      return summary + bundle.phaseSummary
    } catch (error) {
      return label + '未核验：' + (error instanceof Error ? error.message : '清单格式无效')
    }
  })
  return { summaries, url: url.href, count: data.asc_count, report, notice }
}
