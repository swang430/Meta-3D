import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, Button, Checkbox, Code, Group, SimpleGrid, Stack, Text, TextInput, Title } from '@mantine/core'
import { cancelFixedRouteAcquisition, fetchFixedRouteAcquisition,
  fetchFixedRouteAcquisitions, startFixedRouteAcquisition, selectFixedRouteReference } from '../../api/labProfileService'
import { fixedRouteDisplay, fixedRouteStillActive, acquisitionStatus } from '../LabWorkspace/fixedRouteDisplay'
import type { FixedRouteRequest, FixedRouteRecord, CalibrationScopeSnapshot } from '../../types/api'

function failure(error: unknown) {
  const response = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof response === 'string' ? response : error instanceof Error ? error.message : '请求未成功，请查看原始记录'
}

/** 父组件按实验室/暗室key挂载；取消通过服务器执行，不用断开HTTP冒充停发。 */
export function FixedRouteAcquisitionPanel({ labId, snapshot, chainId, blocked, onBusy, onRecord }: {
  labId: string; snapshot: CalibrationScopeSnapshot; chainId: string; blocked: boolean
  onBusy: (busy: boolean) => void; onRecord: (record: FixedRouteRecord | undefined) => void
}) {
  const history = useQuery({ queryKey: ['fixed-route-acquisitions', labId, chainId], queryFn: () => fetchFixedRouteAcquisitions(labId, chainId), retry: false })
  const [runId, setRunId] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [values, setValues] = useState({ frequency: '', power: '', antenna: '', cable: '', cableSource: '', samples: '5' })
  const [fixed, setFixed] = useState(false)
  const [safe, setSafe] = useState(false)
  const [inputError, setInputError] = useState('')
  const [settingsOpen,setSettingsOpen]=useState(true)
  const [referenceConfirmed,setReferenceConfirmed]=useState(false)
  const progress = useQuery({ queryKey: ['fixed-route-acquisition', labId, runId],
    queryFn: () => fetchFixedRouteAcquisition(labId, runId!), enabled: Boolean(runId), retry: false,
    refetchInterval: query => query.state.data?.status === 'running' ? 300 : false })
  const start = useMutation({ mutationFn: (request: FixedRouteRequest) => startFixedRouteAcquisition(labId, request),
    onSuccess: value => { setRunId(value.run_id); setActiveRunId(value.run_id); void history.refetch() } })
  const cancel = useMutation({ mutationFn: () => cancelFixedRouteAcquisition(labId, runId!),
    onSuccess: () => { void progress.refetch() } })
  const adopt=useMutation({mutationFn:()=>selectFixedRouteReference(labId,runId!,snapshot.digest),
    onSuccess:()=>{setReferenceConfirmed(false);void progress.refetch();void history.refetch()}})
  const result = !progress.isError && !progress.isPaused ? progress.data : undefined
  const running = start.isPending || fixedRouteStillActive(activeRunId, result)
  useEffect(() => { onBusy(running); return () => onBusy(false) }, [running, onBusy])
  useEffect(() => { onRecord(result) }, [result, onRecord])
  useEffect(() => {
    if (activeRunId && !fixedRouteStillActive(activeRunId, result)) setActiveRunId(null)
  }, [activeRunId, result])
  useEffect(() => {
    const pending = history.data?.find(value => value.status === 'running')
    if (pending && !activeRunId) { setRunId(pending.run_id); setActiveRunId(pending.run_id) }
    else if(!runId){const reference=history.data?.find(value=>value.selected_as_reference);if(reference)setRunId(reference.run_id)}
  }, [history.data])
  useEffect(() => { if (result && result.status !== 'running') void history.refetch() }, [result?.status, result?.run_id])
  useEffect(()=>{if(result&&result.status!=='running')setSettingsOpen(false)},[result?.status,result?.run_id])
  useEffect(()=>{setReferenceConfirmed(false);adopt.reset()},[runId])
  const chain = snapshot.payload.chains.find(value => value.chain_id === chainId)
  const shown = result ? fixedRouteDisplay(result) : null
  const edit = (key: keyof typeof values, value: string) => { setValues(old => ({ ...old, [key]: value })); setInputError(''); start.reset() }
  return <Stack gap="sm" data-testid="topology-acquisition-panel">
    <Title order={4}>测量这条通路</Title>
    <Text size="sm">图中所选：F64 {chain?.ce_port} → 探头{chain?.probe_id} {chain?.polarization} → 参考天线</Text>
    <Text size="xs" c="dimmed">开关不动；不自动覆盖配置值或应用测试补偿。</Text>
    <Button variant="light" disabled={running} onClick={()=>setSettingsOpen(value=>!value)}>{settingsOpen?'收起测量设置':'测量设置'}</Button>
    {settingsOpen&&<form onSubmit={event => {
      event.preventDefault()
      const frequency = Number(values.frequency), power = Number(values.power), count = Number(values.samples)
      if (blocked || !chain || !fixed || !safe || !values.frequency.trim() || !values.power.trim()
        || !Number.isFinite(frequency) || !Number.isFinite(power) || !Number.isInteger(count)
        || (values.cable.trim() && !Number.isFinite(Number(values.cable)))) {
        setInputError('请选择当前链路、填写有效频率和功率，并确认固定接线及安全条件。'); return
      }
      cancel.reset()
      start.mutate({ chain_id: chain.chain_id, configuration_digest: snapshot.digest,
        frequency_mhz: frequency, requested_power_dbm: power, sample_count: count,
        reference_antenna: values.antenna, receive_cable_loss_db: values.cable.trim() ? Number(values.cable) : null,
        receive_cable_source: values.cableSource.trim() || null, fixed_route_confirmed: true, safety_confirmed: true })
    }}><fieldset disabled={running} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}><Stack gap="sm">
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <TextInput label="采集频率（MHz）" required type="number" min={0.001} step="any" value={values.frequency} onChange={e => edit('frequency', e.currentTarget.value)} />
        <TextInput label="允许的单音设置功率（dBm，非实测）" required type="number" min={-100} max={0} step="any" value={values.power} onChange={e => edit('power', e.currentTarget.value)} />
        <TextInput label="参考天线身份、极化及位置" required maxLength={500} value={values.antenna} onChange={e => edit('antenna', e.currentTarget.value)} />
        <TextInput label="重复采样次数" required type="number" min={2} max={10} value={values.samples} onChange={e => edit('samples', e.currentTarget.value)} />
        <TextInput label="接收线缆损耗（dB，可空）" type="number" step="any" value={values.cable} onChange={e => edit('cable', e.currentTarget.value)} />
        <TextInput label="接收线缆记录来源及适用频率" maxLength={500} value={values.cableSource} onChange={e => edit('cableSource', e.currentTarget.value)} />
      </SimpleGrid>
      <Text size="xs">接收线缆只指参考天线到分析仪的一段；已有拓扑线损不是这段接收线缆的实测记录。缺少资料时只采集功率，不计算整条路径损耗。</Text>
      <Checkbox label="我已核对所选链的实际接线，开关已固定到该通路" checked={fixed} onChange={e => setFixed(e.currentTarget.checked)} />
      <Checkbox label="我已确认专用校准仿真正在运行、本输出口无其它混入信号，以及设置功率对功放和接收端安全" checked={safe} onChange={e => setSafe(e.currentTarget.checked)} />
      <Button type="submit" disabled={blocked || !chain || !fixed || !safe} loading={start.isPending}>开始自动采集</Button>
    </Stack></fieldset></form>}
    {running && <Group><Text>服务器正在采集；关闭页面不等于停止仪器。</Text><Button color="red" loading={cancel.isPending} disabled={!runId} onClick={() => cancel.mutate()}>取消采集并停止本次单音</Button></Group>}
    {inputError && <Alert color="red">{inputError}</Alert>}
    {start.isError && <Alert color="red">无法开始采集：{failure(start.error)}</Alert>}
    {cancel.isError && <Alert color="red">停止请求失败：{failure(cancel.error)}</Alert>}
    {progress.isError && <Alert color="red">采集状态读取失败，不能据此认为仪器已停止：{failure(progress.error)}<Button variant="light" onClick={() => void progress.refetch()}>重新读取采集状态</Button></Alert>}
    {shown && result && <Alert color={result.status === 'completed' ? 'blue' : result.status === 'simulated' ? 'yellow' : 'red'}>
      <Text fw={600}>{shown.label}</Text>
      <Text size="sm">记录频率：{result.result?.request.frequency_mhz} MHz；当时设置功率：{result.result?.request.requested_power_dbm} dBm（非实测）</Text>
      <Text>F64输出口实测功率：{shown.source}；分析仪输入口实测功率：{shown.received}</Text>
      <Text>整条路径损耗或增益：{shown.loss}</Text>
      <Text>停发确认：{shown.cleanup}</Text>
      {result.result?.error && <Text>{result.result.error}</Text>}
      {result.result?.missing_items?.map((value, i) => <Text size="sm" key={i}>{value}</Text>)}
      <details><summary>查看本次配置、逐次读数、原始回复和计算结果</summary><Code block style={{ maxHeight: 400, overflow: 'auto', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(result, null, 2)}</Code></details>
    </Alert>}
    {result&&<Stack gap="xs">
      {result.selected_as_reference?<Alert color="blue">操作员已选为本通路参考；没有自动覆盖配置损耗或应用测试补偿。</Alert>
        :<><Checkbox label="我已复核这条实测记录，确认选作本通路参考（不自动应用补偿）" checked={referenceConfirmed}
          disabled={running||result.status!=='completed'} onChange={e=>setReferenceConfirmed(e.currentTarget.checked)}/>
          <Button variant="light" disabled={running||blocked||!referenceConfirmed||result.status!=='completed'} loading={adopt.isPending}
            onClick={()=>adopt.mutate()}>确认采用为参考</Button></>}
      {result.status==='simulated'&&<Text size="xs" c="orange">模拟记录不能作为实测参考。</Text>}
      {adopt.isError&&<Alert color="red">参考记录未保存：{failure(adopt.error)}</Alert>}
    </Stack>}
    <Title order={5}>自动采集历史</Title>
    {history.isError ? <Alert color="red">历史读取失败：{failure(history.error)}</Alert> : history.data?.length ? history.data.map(row => <Group key={row.run_id} justify="space-between">
      <Text size="sm">{new Date(row.run_at).toLocaleString()} · {row.result?.request.frequency_mhz ?? '未知频率'} MHz · {acquisitionStatus[row.status] ?? '状态未知'}</Text>
      <Button variant="subtle" disabled={running} onClick={() => { setRunId(row.run_id); cancel.reset() }}>查看记录</Button>
    </Group>) : <Text size="sm">暂无自动采集记录。</Text>}
  </Stack>
}
