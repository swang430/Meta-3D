import { Stack, Table, Text } from '@mantine/core'
import type { ConductedPreparation } from '../../types/roadTest'

export function ConductedSetup({ snapshot }: { snapshot: ConductedPreparation }) {
  return <Stack gap="xs">
    <Text fw={600}>{snapshot.binding?.execution_mode === 'simulated' ? '传导测试（模拟硬件）'
      : snapshot.binding?.execution_mode === 'real' ? '传导测试（已绑定真实信道仿真器）' : '信道仿真器绑定待确认'}</Text>
    <Text>场景版本 {snapshot.scenario_version} · 实验室 {snapshot.lab_name || '尚未选择'}</Text>
    {snapshot.asset && <Text style={{ overflowWrap: 'anywhere' }}>{snapshot.asset.mock_only ? '八路模拟输入清单' : '工程'} {snapshot.asset.name} {snapshot.asset.instrument_path}<br/>文件摘要（SHA-256） {snapshot.asset.sha256}</Text>}
    {Array.isArray(snapshot.port_mapping) && snapshot.port_mapping.length > 0 && <Table><Table.Thead><Table.Tr>
      {['基站发射端口', '仿真器输入', '仿真器输出', '接收端口'].map(title => <Table.Th key={title}>{title}</Table.Th>)}
    </Table.Tr></Table.Thead><Table.Tbody>{snapshot.port_mapping.map(p => <Table.Tr key={p.tx + '-' + p.rx}>
      {[p.tx,p.input_port,p.output_port,p.rx].map((v,i) => <Table.Td key={i}>{v}</Table.Td>)}
    </Table.Tr>)}</Table.Tbody></Table>}
    {Array.isArray(snapshot.reasons) && snapshot.reasons.map(message => <Text c="red" key={message}>{message}</Text>)}
  </Stack>
}
