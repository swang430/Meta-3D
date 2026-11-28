import { Stack, Text } from '@mantine/core'
import type { ConductedPreparation, OtaPreparation } from '../../types/roadTest'

import { describeTraffic } from './roadTraffic'

export function RoadRunSummary({ snapshot, settings }: {
  snapshot: ConductedPreparation | OtaPreparation
  settings?: ConductedPreparation['test_settings']
}) {
  const playback = snapshot.playback
  const preset = snapshot.scenario_snapshot
  const traffic = settings?.traffic ?? preset?.traffic
  const targets = settings?.kpi_definitions ?? preset?.kpi_definitions
  return <Stack gap={3}>
    {snapshot.road_project && <>
      <Text style={{ overflowWrap: 'anywhere' }}>道路工程 {playback?.project_name || '名称未知'} · 工程版本 {snapshot.road_project.version}</Text>
      <Text size="sm" style={{ overflowWrap: 'anywhere' }}>工程包 SHA-256 {playback?.package_sha256 || '未知'}</Text>
      <Text>工程登记的源帧数 {playback?.source_frames == null ? '未知' : playback.source_frames + ' 帧'}</Text>
    </>}
    {preset?.network && <Text>基站协议预设 {preset.network.type} · {preset.network.band} · {preset.network.bandwidth_mhz} MHz</Text>}
    {settings?.terminal_protocol && <Text>本次登记的终端协议 {settings.terminal_protocol}</Text>}
    <Text>业务目标 {describeTraffic(traffic)}</Text>
    {targets?.map((target, index) => <Text key={index}>指标目标 {target.kpi_type} · {target.target_value} {target.unit}
      {target.percentile != null && ' · 第 ' + target.percentile + ' 百分位'}
      {target.threshold_min != null && ' · 下限 ' + target.threshold_min + ' ' + target.unit}
      {target.threshold_max != null && ' · 上限 ' + target.threshold_max + ' ' + target.unit}
    </Text>)}
  </Stack>
}
