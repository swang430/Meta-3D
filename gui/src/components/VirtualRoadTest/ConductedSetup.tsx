import { RoadRunSummary } from './RoadRunSummary'
import { Stack, Table, Text } from '@mantine/core'
import { CalibrationDetails } from './ConductedCalibration'
import type { ConductedPreparation } from '../../types/roadTest'

export function ConductedSetup({ snapshot }: { snapshot: ConductedPreparation }) {
  const check = snapshot.binding?.real_preflight?.calibration
  return <Stack gap="xs">
    <Text fw={600}>{snapshot.binding?.execution_mode === 'simulated' ? '传导测试（模拟硬件）'
      : snapshot.binding?.execution_mode === 'real' ? '传导测试（已绑定真实信道仿真器）' : '信道仿真器绑定待确认'}</Text>
    <Text>{snapshot.ready ? '准备检查已通过' : '准备检查尚未通过'}</Text>
    {snapshot.binding?.execution_mode === 'simulated' && snapshot.asset?.mock_only && <Text>八路输入来自模拟清单，执行要求基站和信道仿真器均使用模拟驱动。模拟测量不计入正式测试结论。</Text>}
    <Text>场景版本 {snapshot.scenario_version || '未知'} · 实验室 {snapshot.lab_name || '尚未选择'}</Text>
    {snapshot.playback && <Text>源轨迹时长 {snapshot.playback.source_duration_s == null ? '未核验' : snapshot.playback.source_duration_s+' 秒'} · 本次播放从起点开始，共 {snapshot.playback.duration_s} 秒（整段依据为{snapshot.playback.duration_source}）。</Text>}
    <RoadRunSummary snapshot={snapshot} settings={snapshot.test_settings} />
    {snapshot.scenario_sha256 && <Text size="sm" style={{ overflowWrap: 'anywhere' }}>场景内容摘要（SHA-256） {snapshot.scenario_sha256}</Text>}
    {snapshot.asset && <Text style={{ overflowWrap: 'anywhere' }}>{snapshot.asset.mock_only ? '八路模拟输入清单' : '工程'} {snapshot.asset.name} {snapshot.asset.instrument_path}<br/>文件摘要（SHA-256） {snapshot.asset.sha256}</Text>}
    {Array.isArray(snapshot.port_mapping) && snapshot.port_mapping.length > 0 && <Table><Table.Thead><Table.Tr>
      {['基站发射端口', '仿真器输入', '仿真器输出', '接收端口'].map(title => <Table.Th key={title}>{title}</Table.Th>)}
    </Table.Tr></Table.Thead><Table.Tbody>{snapshot.port_mapping.map(p => <Table.Tr key={p.tx + '-' + p.rx}>
      {[p.tx,p.input_port,p.output_port,p.rx].map((v,i) => <Table.Td key={i}>{v}</Table.Td>)}
    </Table.Tr>)}</Table.Tbody></Table>}
    {snapshot.binding?.receiver_power_plan && <Stack gap={2}>
      <Text>接收插口功率预测，所有端口和帧使用同一偏移 {snapshot.binding.receiver_power_plan.common_offset_db.toFixed(2)} dB。</Text>
      {snapshot.binding.receiver_power_plan.predictions.filter(row=>row.frame===snapshot.binding!.receiver_power_plan!.reference_frame).map(row=>
        <Text key={row.rx}>源帧 {row.frame}，源端口 {row.rx} → 实物插口 {row.physical_rx}：参考目标（实测依据见校准） {row.target_dut_dbm?.toFixed(2) ?? '未核验'} dBm，
          仿真器输出口 {row.output_port ?? "未核验"} 目标 {row.f64_connector_target_dbm?.toFixed(2) ?? '未核验'} dBm。设定回读与本次插口实测待取得。</Text>)}
    </Stack>}
    {!check?.id && <Text>本次执行未记录现场逐端口校准。</Text>}
    {check && <CalibrationDetails check={check} />}
    {Array.isArray(snapshot.reasons) && snapshot.reasons.filter(message => !check?.reasons.includes(message)).map(message => <Text c="red" key={message}>{message}</Text>)}
  </Stack>
}
