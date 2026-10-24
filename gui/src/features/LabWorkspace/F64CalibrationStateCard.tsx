import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, Badge, Button, Card, SimpleGrid, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { fetchF64CalibrationHistory, readF64CalibrationState } from '../../api/labProfileService'
import type { F64StateRecord } from '../../types/api'

function RecordView({ record }: { record: F64StateRecord }) {
  const state = record.state
  return <Stack gap="xs">
    <Text size="sm">读取时间：{new Date(state?.captured_at ?? record.run_at).toLocaleString()}</Text>
    {!record.success && <Alert color="yellow">读取未全部完成：{record.error_message ?? '部分项目未知，请核对原始回复。'}</Alert>}
    {!state ? <Alert color="yellow">记录不完整，不能从当前设置补全。</Alert> : <>
      <Badge color="yellow">{state.acquisition_status === 'simulated' ? '模拟记录，不含真实仪器读数' : '当时读取记录，不代表持续当前状态'}</Badge>
      <Text size="sm">信道组 {state.requested.group_id} · 输入口 {state.requested.input_port} · 输出口 {state.requested.output_port}</Text>
      <Text size="xs" style={{ overflowWrap: 'anywhere' }}>本次配置标识：{state.binding_digest}</Text>
      {state.warnings?.map((warning, i) => <Alert key={i} color="yellow">{warning}</Alert>)}
      <Table.ScrollContainer minWidth={650}>
        <Table striped withTableBorder>
          <Table.Thead><Table.Tr><Table.Th>项目</Table.Th><Table.Th>读取结果</Table.Th><Table.Th>值 / 原始回复 / 出处</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{state.fields.map(field => <Table.Tr key={field.key}>
            <Table.Td>{field.label}</Table.Td>
            <Table.Td>{field.status === 'confirmed' ? '已读取' : field.status === 'simulated' ? '模拟' : '未知'}</Table.Td>
            <Table.Td style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>
              <Text size="sm">值：{field.value === null || field.value === undefined ? '无可信读数' : JSON.stringify(field.value)}</Text>
              <Text size="xs">原始回复：{field.raw === null || field.raw === undefined ? '无回复' : JSON.stringify(field.raw)}</Text>
              <Text size="xs">{field.source_reference} · {field.detail}</Text>
            </Table.Td>
          </Table.Tr>)}</Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </>}
  </Stack>
}

/** 只显示服务器存档；父层用实验室编号作为key，切换时不保留旧结果。 */
export function F64CalibrationStateCard({ labId }: { labId: string }) {
  const [inputs, setInputs] = useState({ group_id: '', input_port: '', output_port: '' })
  const [inputError, setInputError] = useState('')
  const history = useQuery({ queryKey: ['f64-calibration-state', labId], queryFn: () => fetchF64CalibrationHistory(labId), retry: false })
  const capture = useMutation({ mutationFn: (request: { group_id: number; input_port: number; output_port: number }) => readF64CalibrationState(labId, request),
    onSuccess: () => { void history.refetch() }, retry: false })
  return <Card withBorder data-testid="f64-calibration-state"><Stack gap="sm">
    <Title order={4}>F64 对齐与补偿状态记录（PC-03A）</Title>
    <Alert color="yellow">只读取和记录。不自动对齐、不切换开关、不写补偿、不改变就绪状态。读取成功不代表校准有效；模拟结果不能作为现场证据。</Alert>
    <Text size="sm">请按 F64 实际仿真填写编号，没有预设值。仅在仿真已加载并停止时读取组及端口设置；这里的损耗和增益是设置值，不是实测功率。</Text>
    <form onSubmit={event => {
      event.preventDefault()
      const request = { group_id: Number(inputs.group_id), input_port: Number(inputs.input_port), output_port: Number(inputs.output_port) }
      if (Object.values(request).some(value => !Number.isSafeInteger(value) || value <= 0)) {
        setInputError('请填写三个正整数编号。'); return
      }
      setInputError(''); capture.mutate(request)
    }}>
      <fieldset disabled={capture.isPending} style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}><Stack>
        <SimpleGrid cols={{ base: 1, md: 3 }}>{([
          ['group_id', '信道组编号'], ['input_port', '物理输入口编号'], ['output_port', '物理输出口编号'],
        ] as const).map(([key, label]) => <TextInput key={key} label={label} type="number" min={1} step={1} required
          value={inputs[key]} onChange={event => {
            const value = event.currentTarget.value
            setInputs(old => ({ ...old, [key]: value })); setInputError(''); capture.reset()
          }} />)}</SimpleGrid>
        <Button type="submit" loading={capture.isPending} style={{ alignSelf: 'start' }}>读取 F64 状态</Button>
      </Stack></fieldset>
    </form>
    {inputError && <Alert color="red">{inputError}</Alert>}
    {capture.isPaused && <Alert color="yellow">读取请求等待网络恢复，尚无新结果。</Alert>}
    {capture.isError && <Alert color="red">读取失败：{capture.error.message}</Alert>}
    {!capture.isPending && !capture.isError && capture.data && <div data-testid="f64-current-result"><RecordView record={capture.data} /></div>}
    <Title order={5}>历史读取记录（不是当前仪器状态）</Title>
    <Button variant="light" onClick={() => { void history.refetch() }} loading={history.isFetching}>刷新历史记录</Button>
    {history.isError ? <Alert color="red">历史读取失败：{history.error.message}</Alert>
      : history.isFetching || history.isPaused ? <Text>正在读取历史记录…</Text>
      : history.data?.length ? history.data.map(record => <details key={record.diagnostic_run_id}>
        <summary>{new Date(record.run_at).toLocaleString()} · {record.record_status === 'incomplete' ? '记录不完整' : record.state?.acquisition_status === 'simulated' ? '模拟记录' : '当时读取记录'}</summary>
        <RecordView record={record} />
      </details>) : <Text>尚无读取记录。</Text>}
  </Stack></Card>
}
