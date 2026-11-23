import { useState } from 'react'
import { Alert, Button, Group, Modal, Select, Stack, Text } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import {
  archiveExecutionReport, controlExecution, fetchConductedOptions, fetchExecutionDetail,
  fetchExecutionObservations, fetchExecutionStatus, prepareConducted, saveConducted,
} from '../../api/roadTestService'
import { ConductedSetup } from './ConductedSetup'
import type { ConductedPreparation, ConductedSelection, ExecutionStatus } from '../../types/roadTest'
import { TestReportModal } from './TestReportModal'
import { ExecutionObservations } from './ExecutionObservations'

const labels: Record<ExecutionStatus, string> = {
  idle: '等待启动', initializing: '正在初始化', configured: '配置完成', running: '运行中',
  paused: '已暂停', stopped: '已停止', failed: '执行失败', completed: '执行完成',
}
const fields = [
  ['实验室', 'labs', 'lab_profile_id'], ['接线方案', 'topologies', 'topology_id'], ['可播放工程', 'assets', 'asset_id'],
] as const

export function ConductedExecutionModal({ opened, onClose, scenario, initialId }: {
  opened: boolean
  onClose: () => void
  scenario: { id: string; name: string }
  initialId?: string
}) {
  const cache = useQueryClient()
  const key = 'vrt-conducted:' + scenario.id
  const [id, setId] = useState(() => initialId || sessionStorage.getItem(key) || '')
  const [selection, setSelection] = useState<ConductedSelection>({
    scenario_id: scenario.id, direction: 'downlink', lab_profile_id: null, topology_id: null, asset_id: null,
  })
  const [report, setReport] = useState(false)
  const options = useQuery({ queryKey: ['vrt-options'], queryFn: fetchConductedOptions, enabled: opened })
  const detail = useQuery({ queryKey: ['vrt-detail', id], queryFn: () => fetchExecutionDetail(id), enabled: opened && !!id })
  const missing = isAxiosError(detail.error) && detail.error.response?.status === 404
  const matches = !missing && detail.data?.mode === 'conducted' && (initialId === id || detail.data.scenario_id === selection.scenario_id)
  const preview = useQuery({ queryKey: ['vrt-prepare', selection], queryFn: () => prepareConducted(selection), enabled: opened && !id })
  const snapshot: ConductedPreparation | undefined = id ? (matches && detail.data?.config.conducted || undefined) : preview.data
  const state = useQuery({
    queryKey: ['vrt-status', id], queryFn: () => fetchExecutionStatus(id),
    enabled: opened && matches, refetchInterval: opened && matches ? 2000 : false,
  })
  const status = state.data?.status
  const terminal = status === 'failed' || status === 'completed' || status === 'stopped'
  const samples = useQuery({ queryKey: ['vrt-samples', id], queryFn: () => fetchExecutionObservations(id),
    enabled: opened && matches, refetchInterval: opened && matches && !terminal ? 2000 : false })
  const save = useMutation({
    mutationFn: () => saveConducted(selection),
    onSuccess: record => {
      sessionStorage.setItem('vrt-conducted:' + record.scenario_id, record.execution_id)
      setId(record.execution_id)
      void cache.invalidateQueries({ queryKey: ['road-test-executions'] })
    },
  })
  function refreshExecution() {
    void cache.invalidateQueries({ queryKey: ['vrt-status', id] })
    void cache.invalidateQueries({ queryKey: ['vrt-detail', id] })
    void cache.invalidateQueries({ queryKey: ['road-test-executions'] })
  }
  const start = useMutation({ mutationFn: () => controlExecution(id, 'start'), onSettled: refreshExecution })
  const stop = useMutation({ mutationFn: () => controlExecution(id, 'stop'), onSettled: refreshExecution })
  const controlling = start.isPending || stop.isPending
  const archive = useMutation({ mutationFn: () => archiveExecutionReport(id) })
  function retry() {
    if (!snapshot && detail.data) setSelection(previous => ({ ...previous, scenario_id: detail.data!.scenario_id }))
    if (snapshot) setSelection({ scenario_id: snapshot.scenario_id, direction: 'downlink', lab_profile_id: snapshot.lab_profile_id,
      topology_id: snapshot.topology_id, asset_id: snapshot.asset_id })
    const storedKey = 'vrt-conducted:' + (detail.data?.scenario_id || selection.scenario_id)
    if (sessionStorage.getItem(storedKey) === id) sessionStorage.removeItem(storedKey)
    setId(''); archive.reset(); start.reset(); stop.reset(); save.reset()
  }
  const error = stop.error || start.error || save.error || archive.error || state.error || samples.error || detail.error || preview.error || options.error
  const reason = isAxiosError(error) ? error.response?.data?.detail : null
  return <Modal opened={opened} onClose={onClose} closeOnEscape={!report} closeOnClickOutside={!report} title="传导测试准备与执行" size="xl">
    <Stack>
      <Text fw={600}>{scenario.name} · 下行四发二收</Text>
      {fields.map(([label, list, field]) => <Select key={field} label={label} value={id ? snapshot?.[field] || null : selection[field]}
        disabled={!!id || save.isPending} placeholder={'请选择' + label} clearable searchable
        data={(options.data?.[list] || []).map(x => ({ value: x.id, label: x.name }))}
        onChange={value => setSelection(previous => ({ ...previous, [field]: value }))} />)}
      {snapshot && <ConductedSetup snapshot={snapshot} />}
      {snapshot?.ready && !snapshot.asset?.mock_only && <Alert>当前执行器仅开放八路模拟输入。真实设备的载频、带宽、功率和适用校准仍待核对。</Alert>}
      {!id && <Button disabled={!snapshot} loading={save.isPending} onClick={() => save.mutate()}>保存准备记录</Button>}
      {id && <Text>执行编号 {id} · 服务端状态 {status ? labels[status] : '尚未取得'}</Text>}
      {state.data && <Text>服务端进度 {state.data.progress_percent}% · 已用 {state.data.elapsed_time_s} 秒</Text>}
      {state.data?.last_error && <Alert color="red">{state.data.last_error}</Alert>}
      {state.data?.warnings.map((message, i) => <Text key={i}>{message}</Text>)}
      {error && <Alert color="red" title="请求失败">{typeof reason === 'string' ? reason : error.message}</Alert>}
      {!terminal && <Group>
        <Button disabled={!id || !snapshot?.ready || !snapshot.asset?.mock_only || snapshot.binding?.execution_mode !== 'simulated' || status !== 'idle' || controlling || state.isError}
          onClick={() => start.mutate()}>启动传导测试</Button>
        <Button disabled>暂停或恢复（设备支持情况未知）</Button>
        {id && matches && <Button disabled={stop.isPending} onClick={() => stop.mutate()}>停止本次执行</Button>}
      </Group>}
      {id && <Button variant="light" onClick={() => { void detail.refetch(); if (matches) void state.refetch() }}>重新读取执行状态</Button>}
      {samples.data && <ExecutionObservations samples={samples.data} />}
      {terminal && <Group>
        <Button onClick={() => setReport(true)}>查看报告</Button>
        <Button loading={archive.isPending} disabled={archive.isSuccess} onClick={() => archive.mutate()}>归档报告</Button>
      </Group>}
      {(terminal || status === 'idle' || (missing && !!selection.scenario_id)) && !controlling && <Button variant="light" onClick={retry}>重新准备一次执行</Button>}
      {archive.data && <Group><Text>归档报告编号 {archive.data.id}</Text>
        <Button component="a" href={`/api/v1/reports/${encodeURIComponent(archive.data.id)}/download`} download variant="light">下载归档报告</Button>
      </Group>}
    </Stack>
    {report && <TestReportModal opened onClose={() => setReport(false)} executionId={id} />}
  </Modal>
}
