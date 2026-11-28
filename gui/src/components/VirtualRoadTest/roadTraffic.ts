import type { ConductedTestSettings } from '../../types/roadTest'

export const trafficOptions = [
  { value: 'ftp', label: '文件传输' },
  { value: 'video', label: '视频' },
  { value: 'voip', label: '语音' },
  { value: 'web', label: '网页' },
  { value: 'gaming', label: '游戏' },
]

export function describeTraffic(traffic?: ConductedTestSettings['traffic']) {
  if (!traffic) return '未记录'
  const name = trafficOptions.find(option => option.value === traffic.type)?.label ?? traffic.type
  const direction = { DL: '下行', UL: '上行', BOTH: '双向' }[traffic.direction]
  const rate = traffic.data_rate_mbps == null ? '' : traffic.data_rate_mbps + ' Mbps'
  return [name, direction || traffic.direction, rate].filter(Boolean).join(' · ')
}
