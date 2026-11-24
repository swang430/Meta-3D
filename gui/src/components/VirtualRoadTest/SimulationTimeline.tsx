import { ScrollArea, Stack, Table, Text } from '@mantine/core'
import Plot from 'react-plotly.js'
import type { TwinInput, TwinTimeline } from '../../types/roadTest'

export function ModelInput({ input }: { input?: TwinInput | null }) {
  if (!input) return <Text>这条记录缺少已保存的仿真输入，无法核验。</Text>
  return <details><summary>查看仿真输入</summary>
    <Text>模型版本 {input.model_version} · 随机种子 {input.model_parameters.seed} · 回放倍率 {input.acceleration_factor}</Text>
    <Text size="sm" style={{ overflowWrap: 'anywhere' }}>场景内容摘要 {input.scenario_sha256}</Text>
    <pre style={{ overflow: 'auto' }}>{JSON.stringify(input.scenario_snapshot, null, 2)}</pre>
  </details>
}

export function ThroughputPlot({ title, axis, x, y }: { title: string; axis: string; x: number[] | string[]; y: (number | null)[] }) {
  return <Plot data={[{ type: 'scatter', mode: 'lines+markers', x, y, name: title }]}
    layout={{ title: { text: title }, height: 260, margin: { t: 42, b: 46, l: 68, r: 14 },
      xaxis: { title: { text: axis } }, yaxis: { title: { text: '下行吞吐率（Mbps）' } } }}
    useResizeHandler style={{ width: '100%' }} config={{ displayModeBar: false, responsive: true }} />
}

export function SimulationTimeline({ timeline }: { timeline: TwinTimeline }) {
  if (timeline.provenance !== 'simulated' || timeline.formal_kpi !== false || !timeline.points.length)
    return <Text>暂无可核验的模拟样本。</Text>
  const points = timeline.points
  return <Stack gap="xs"><Text fw={600}>模拟时间轴</Text>
    <ThroughputPlot title="数字孪生模拟" axis="场景时间（秒）" x={points.map(p => p.source_frame_time_s)}
      y={points.map(p => p.provenance === 'simulated' ? p.dl_throughput_mbps : null)} />
    <ScrollArea.Autosize mah={220}><Table>
      <Table.Thead><Table.Tr><Table.Th>场景时间（秒）</Table.Th><Table.Th>模拟下行吞吐率（Mbps）</Table.Th></Table.Tr></Table.Thead>
      <Table.Tbody>{points.map((p, i) => <Table.Tr key={i}><Table.Td>{p.source_frame_time_s}</Table.Td>
        <Table.Td>{p.provenance === 'simulated' ? p.dl_throughput_mbps : '未核验'}</Table.Td></Table.Tr>)}</Table.Tbody>
    </Table></ScrollArea.Autosize>
  </Stack>
}
