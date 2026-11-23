import { ScrollArea, Stack, Table, Text } from '@mantine/core'
import type { RunnerObservation } from '../../types/roadTest'
import { parseServerDateTime } from '../../utils/datetime'

const names = {
  connection_state: '连接状态', dl_throughput_mbps: '下行吞吐量',
  ul_throughput_mbps: '上行吞吐量', playback_position_s: '播放位置',
}
const origins = { server_measured: '设备实测', simulated: '模拟', unverified: '待核实' }

export function ExecutionObservations({ samples }: { samples: RunnerObservation[] }) {
  return <Stack gap="xs"><Text fw={600}>设备回读样本</Text>
    {samples.length === 0 ? <Text>暂无服务端采样记录。</Text> : <ScrollArea.Autosize mah={320}>
      <Table><Table.Thead><Table.Tr>
        {['测量项', '读数', '来源', '采样时间', '路线帧时间（秒）', '设备播放时间（秒）'].map(title =>
          <Table.Th key={title}>{title}</Table.Th>)}
      </Table.Tr></Table.Thead><Table.Tbody>
        {samples.map((s, i) => <Table.Tr key={i}>
          <Table.Td>{names[s.metric]}</Table.Td>
          <Table.Td>{s.value === null ? '缺测' : String(s.value) + ' ' + s.unit}</Table.Td>
          <Table.Td>{origins[s.provenance]} · {s.source}</Table.Td>
          <Table.Td>{parseServerDateTime(s.sampled_at).toLocaleString('zh-CN')}</Table.Td>
          <Table.Td>{s.source_frame_time_s ?? '未知'}</Table.Td>
          <Table.Td>{s.device_playback_time_s ?? '未知'}</Table.Td>
        </Table.Tr>)}
      </Table.Tbody></Table>
    </ScrollArea.Autosize>}
  </Stack>
}
