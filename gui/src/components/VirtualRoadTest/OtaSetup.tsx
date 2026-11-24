import { Alert, Stack, Table, Text } from '@mantine/core'
import type { OtaPreparation } from '../../types/roadTest'

export function OtaSetup({ snapshot }: { snapshot: OtaPreparation }) {
  const calibration = snapshot.calibration
  return <Stack gap="xs">
    <Text fw={600}>辐射测试（模拟硬件） · {snapshot.ready ? '准备检查已通过' : '准备检查尚未通过'}</Text>
    <Alert color="orange">模拟测量不计入正式测试结论。传导校准不能代替 OTA 校准，真实暗室仍待现场验收。</Alert>
    <Text>场景版本 {snapshot.scenario_version} · 实验室 {snapshot.lab_name || '尚未选择'} · 暗室 {snapshot.chamber?.name || '尚未选择'}</Text>
    <Text size="sm" style={{ overflowWrap: 'anywhere' }}>场景内容摘要（SHA-256） {snapshot.scenario_sha256}</Text>
    {snapshot.asset && <Stack gap={4}>
      <Text style={{ overflowWrap: 'anywhere' }}>OTA 模拟工程 {snapshot.asset.name} · 摘要（SHA-256） {snapshot.asset.sha256}</Text>
      {snapshot.asset.links.map(link => <Text key={link.file} size="xs" style={{ overflowWrap: 'anywhere' }}>{link.file} · {link.sha256}</Text>)}
    </Stack>}
    {snapshot.probe_mapping.length > 0 && <Table><Table.Thead><Table.Tr>
      {['探头编号', '仿真器输出端口', '极化', '方位角 / 仰角 / 半径'].map(label => <Table.Th key={label}>{label}</Table.Th>)}
    </Table.Tr></Table.Thead><Table.Tbody>{snapshot.probe_mapping.map(probe => <Table.Tr key={probe.probe_id}>
      <Table.Td style={{ overflowWrap: 'anywhere' }}>{probe.probe_id}</Table.Td><Table.Td>{probe.output_port}</Table.Td>
      <Table.Td>{probe.polarization}</Table.Td><Table.Td>{probe.position.azimuth}° / {probe.position.elevation}° / {probe.position.radius} m</Table.Td>
    </Table.Tr>)}</Table.Tbody></Table>}
    {calibration && <Text>校准范围（{calibration.mock_only ? '仅模拟' : '资格待核验'}）：{calibration.frequency_min_mhz}–{calibration.frequency_max_mhz} MHz，
      带宽 {calibration.bandwidth_mhz} MHz，测试区域直径 {calibration.quiet_zone_diameter_m} m；有效至 {calibration.valid_until}</Text>}
    {snapshot.reasons.map((reason, index) => <Text c="red" key={index}>{reason}</Text>)}
  </Stack>
}
