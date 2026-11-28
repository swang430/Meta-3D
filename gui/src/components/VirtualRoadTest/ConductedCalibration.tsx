import { useState } from 'react'
import { Alert, Button, TextInput, Select, Stack, Table, Text } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { fetchConductedCalibration, fetchConductedCalibrations, registerConductedCalibration } from '../../api/roadTestService'
import type { ConductedCalibrationCheck } from '../../types/roadTest'

export function ConductedCalibration({ value, onSelect, disabled }: {
  value: string | null
  onSelect: (id: string | null) => void
  disabled: boolean
}) {
  const cache = useQueryClient()
  const records = useQuery({ queryKey: ['vrt-calibrations'], queryFn: fetchConductedCalibrations })
  const detailQuery = useQuery({
    queryKey: ['vrt-calibration', value],
    queryFn: () => fetchConductedCalibration(value!),
    enabled: !!value,
  })
  const selected = detailQuery.data
  const [file, setFile] = useState('')
  const validName = /^[^/\\]+\.json$/.test(file.trim())
  const register = useMutation({
    mutationFn: (name: string) => registerConductedCalibration({ report_file: name.trim() }),
    onSuccess: async record => {
      await cache.invalidateQueries({ queryKey: ['vrt-calibrations'] })
      await cache.invalidateQueries({ queryKey: ['vrt-prepare'] })
      onSelect(record.id)
      setFile('')
    },
  })
  const error = register.error || detailQuery.error || records.error
  const detail = isAxiosError(error) && error.response?.data?.detail
  return <Stack gap="xs">
    <Select label="逐端口校准记录" placeholder="请选择校准记录" value={value} clearable searchable
      disabled={disabled || register.isPending} onChange={onSelect}
      data={(records.data || []).map(row => ({ value: row.id, label: [row.revoked_at ? '已撤销' : '', row.report_number, row.issuer, row.id].filter(Boolean).join(' · ') }))} />
    {selected && <Stack gap={2}>
      <Text>校准签发方 {selected.issuer}</Text>
      <Text style={{ overflowWrap: 'anywhere' }}>测量原文摘要（SHA-256） {selected.evidence_sha256}</Text>
      {selected.revoked_at && <Alert color="red">该记录已撤销：{selected.revocation_reason}</Alert>}
      <Text component="a" href={`data:application/json;base64,${selected.evidence_b64}`}
        download={selected.report_file}>下载逐端口测量原文</Text>
      <Text component="a" href={`data:text/csv;base64,${selected.readings_b64}`}
        download={'仪器原始读数-' + selected.id + '.csv'}>下载仪器原始读数</Text>
    </Stack>}
    <TextInput label="实验室已审核目录中的报告文件名" placeholder="报告编号.json" value={file}
      onChange={event => setFile(event.currentTarget.value)} disabled={disabled || register.isPending} />
    <Button variant="light" disabled={!validName || disabled} loading={register.isPending}
      onClick={() => file && register.mutate(file)}>登记逐端口校准</Button>
    {error && <Alert color="red">{typeof detail === 'string' ? detail : error.message}</Alert>}
  </Stack>
}

export function CalibrationDetails({ check }: { check: ConductedCalibrationCheck }) {
  return <Stack gap="xs">
    <Text fw={600}>逐端口校准{check.applicable === true ? '适用于本次执行' : check.applicable === false ? '尚未通过核验' : '结果未知'}</Text>
    {check.report_number && <Text>报告编号 {check.report_number} · 签发方 {check.issuer} · 有效期至 {check.valid_until}</Text>}
    {check.scope && <>
      <Text>本次校准核对的中心频率 {check.scope.center_frequency_hz ?? '未知'} Hz，带宽 {check.scope.bandwidth_mhz ?? '未知'} MHz，基站小区设定功率 {check.scope.tx_power_dbm ?? '未知'} dBm。</Text>
      <Text>基站 {check.scope.base_station_id || '未知'} · 信道仿真器 {check.scope.channel_emulator_id || '未知'} · 车载设备 {check.scope.dut_id || '未知'}</Text>
    </>}
    {check.required_margin_db != null && <Text>要求的最小安全余量 {check.required_margin_db} dB</Text>}
    {check.reasons.map(message => <Text key={message} c="red">{message}</Text>)}
    {!!check.ports.length && <Table.ScrollContainer minWidth={660}><Table><Table.Thead><Table.Tr>
      {['发射 → 接收端口', '测量位置', '上游物理输出（dBm）', '电缆损耗（dB）', '实测峰值（dBm）', '不确定度（dB）', '输入上限（dBm）', '安全余量（dB）'].map(label => <Table.Th key={label}>{label}</Table.Th>)}
    </Table.Tr></Table.Thead><Table.Tbody>{check.ports.flatMap(p => (['emulator_input', 'dut_input'] as const).map(k =>
      <Table.Tr key={p.tx + '-' + p.rx + k}><Table.Td>{p.tx} → {p.rx}</Table.Td>
        <Table.Td>{k === 'emulator_input' ? '仿真器输入 ' + p.input_port : '车载设备输入 ' + p.rx}</Table.Td>
        <Table.Td>{k === 'emulator_input' ? p.base_station_output_dbm : p.emulator_output_dbm}</Table.Td>
        <Table.Td>{k === 'emulator_input' ? p.tx_cable_loss_db : p.rx_cable_loss_db}</Table.Td>
        <Table.Td>{p[k].peak_dbm}</Table.Td><Table.Td>{p[k].uncertainty_db}</Table.Td>
        <Table.Td>{p[k].max_safe_input_dbm}</Table.Td><Table.Td>{p[`${k}_margin_db`]}</Table.Td>
      </Table.Tr>))}</Table.Tbody></Table></Table.ScrollContainer>}
  </Stack>
}
