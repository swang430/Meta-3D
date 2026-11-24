import { isAxiosError } from 'axios'
import { useState } from 'react'
import { Alert, Button, Group, Modal, NumberInput, Select, Stack, Text } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { archiveExecutionReport, fetchExecutionObservations, controlExecution, createExecution, fetchExecutionDetail, fetchExecutions, fetchTwinComparison, fetchTwinTimeline } from '../../api/roadTestService'
import { TestReportModal } from './TestReportModal'

import { ExecutionObservations } from './ExecutionObservations'
import { ModelInput, SimulationTimeline, ThroughputPlot } from './SimulationTimeline'

interface Props {
  scenario: { id: string; name: string }
  initialId?: string
  onClose: () => void
}

function reason(error: unknown) {
  const value = error as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = value.response?.data?.detail
  return typeof detail === 'string' ? detail : value.message || '读取失败，请重试。'
}

export function DigitalTwinExecutionModal({ scenario, initialId, onClose }: Props) {
  const client = useQueryClient()
  const [id, setId] = useState(() => initialId || sessionStorage.getItem('vrt-twin:' + scenario.id) || '')
  const [seed, setSeed] = useState<number | string>(0)
  const [conducted, setConducted] = useState<string | null>(null)
  const [report, setReport] = useState(false)
  const detail = useQuery({ queryKey: ['twin-detail', id], queryFn: () => fetchExecutionDetail(id),
    enabled: !!id, refetchInterval: query => query.state.data?.status === 'running' ? 1500 : false })
  const matches = detail.data?.mode === 'digital_twin'
    && (initialId === id || detail.data.scenario_id === scenario.id)
  const missing = isAxiosError(detail.error) && detail.error.response?.status === 404
  const status = matches ? detail.data?.status : undefined
  const snapshot = matches ? detail.data?.config.digital_twin : undefined
  const timeline = useQuery({ queryKey: ['twin-timeline', id, status], queryFn: () => fetchTwinTimeline(id),
    enabled: !!status && status !== 'idle', refetchInterval: status === 'running' ? 1500 : false, retry: false })
  const records = useQuery({ queryKey: ['twin-conducted'], queryFn: () => fetchExecutions({ mode: 'conducted' }), enabled: !!id })
  const comparison = useQuery({ queryKey: ['twin-comparison', id, conducted, status],
    queryFn: () => fetchTwinComparison(id, conducted!), enabled: !!conducted && !!status && status !== 'idle', refetchInterval: status === 'running' ? 1500 : false, retry: false })
  const observations = useQuery({ queryKey: ['twin-conducted-observations', conducted], queryFn: () => fetchExecutionObservations(conducted!), enabled: !!conducted })
  const archive = useMutation({ mutationFn: () => archiveExecutionReport(id) })
  const action = useMutation({
    mutationFn: async (command: 'start' | 'stop' | 'complete') => {
      let current = id
      if (!current) {
        const record = await createExecution({ mode: 'digital_twin', scenario_id: scenario.id, config: { model_parameters: { seed } } })
        current = record.execution_id
        sessionStorage.setItem('vrt-twin:' + scenario.id, current)
        setId(current)
      }
      await controlExecution(current, command)
    },
    onSettled: async () => {
      await Promise.all([client.invalidateQueries({ queryKey: ['twin-detail'] }), client.invalidateQueries({ queryKey: ['road-test-executions'] })])
    },
  })
  const labels: Record<string, string> = { idle: '待启动', configured: '已配置', initializing: '初始化中', running: '运行中', paused: '已暂停', stopped: '已停止', completed: '已完成', failed: '失败' }
  const terminal = ['completed', 'stopped', 'failed'].includes(status || '')
  const frozenName = snapshot?.scenario_snapshot?.name
  const data = timeline.data
  const result = comparison.data
  return <Modal opened closeOnEscape={!report} onClose={onClose} title={`数字孪生（模拟） · ${typeof frozenName === 'string' ? frozenName : scenario.name}`} size="lg">
    <Stack>
      <Text>本次执行仅运行软件模型，模拟吞吐率不参与正式性能判定。</Text>
      {!id && <NumberInput label="随机种子（相同场景和种子可重现结果）" min={0} max={2147483647} allowDecimal={false} value={seed} onChange={setSeed} />}
      {id && <Text>执行记录 {id} · {status ? labels[status] || '状态待确认' : '正在读取状态'}</Text>}
      <Group>
        {(!id || status === 'idle' || status === 'configured') && <Button disabled={(!!id && !snapshot) || typeof seed !== 'number' || !Number.isInteger(seed) || seed < 0 || seed > 2147483647} loading={action.isPending} onClick={() => action.mutate('start')}>启动数字孪生</Button>}
        {(status === 'running' || status === 'paused') && <Button loading={action.isPending} onClick={() => action.mutate('stop')}>停止数字孪生</Button>}
        {status === 'running' && <Button variant="light" loading={action.isPending} onClick={() => action.mutate('complete')}>生成剩余模拟样本并结束</Button>}
        {id && terminal && <Button variant="light" onClick={() => setReport(true)}>查看模拟报告</Button>}
        {terminal && <Button disabled={archive.isSuccess} loading={archive.isPending} onClick={() => archive.mutate()}>归档模拟报告</Button>}
        {(terminal || missing || (detail.data && !matches)) && !initialId && <Button variant="subtle" onClick={() => {
          sessionStorage.removeItem('vrt-twin:' + scenario.id)
          setSeed(snapshot?.model_parameters?.seed ?? 0)
          setConducted(null)
          archive.reset()
          action.reset()
          setId('')
        }}>重新准备模拟执行</Button>}
      </Group>
      {archive.data && <Group><Text>归档报告编号 {archive.data.id}</Text><Button component="a" href={`/api/v1/reports/${encodeURIComponent(archive.data.id)}/download`} download>下载模拟报告</Button></Group>}
      {[archive.error, observations.error, action.error, detail.error, timeline.error, records.error, comparison.error].map((error, index) => error && <Alert key={index} color="red">{reason(error)}</Alert>)}
      {detail.data && !matches && <Alert color="red">保存的执行编号与本场景和模式不符，请重新准备。</Alert>}
      {matches && <ModelInput input={snapshot} />}
      {data && <SimulationTimeline timeline={data} />}
      {matches && status !== 'idle' && <Select label="选择传导记录进行对照" searchable clearable value={conducted} onChange={setConducted}
        data={(records.data || []).filter(r => r.mode === 'conducted').map(r => ({ value: r.execution_id, label: r.scenario_name + ' · ' + r.execution_id }))} />}
      {observations.data && <>
        {(['server_measured', 'simulated', 'unverified'] as const).map(origin => {
          const readings = observations.data.filter(p => p.metric === 'dl_throughput_mbps' && p.provenance === origin)
          return readings.length > 0 && <ThroughputPlot key={origin} title={{server_measured:'传导设备实测', simulated:'传导模拟', unverified:'传导来源未核验'}[origin]}
            axis="设备采样时间" x={readings.map(p => p.sampled_at)} y={readings.map(p => typeof p.value === 'number' ? p.value : null)} />
        })}
        <ExecutionObservations samples={observations.data} />
      </>}
      {result && <><Text>{result.reason}</Text>{result.comparable && result.formal_kpi === false ?
        result.differences.map((d, i) => <Text key={i}>{d.source_frame_time_s} 秒 · 下行吞吐率差值（模拟减实测） {d.delta_dl_throughput_mbps} Mbps</Text>) :
        <Text>对照未核验。</Text>}</>}
      {report && <TestReportModal opened executionId={id} onClose={() => setReport(false)} />}
    </Stack>
  </Modal>
}
