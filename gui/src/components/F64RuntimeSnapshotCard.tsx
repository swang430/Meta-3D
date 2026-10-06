import { Alert, Button, Card, Group, Stack, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { fetchF64RuntimeSnapshot } from '../api/service'

const labels: Record<string, string> = {
  identity: '连接身份缓存', loaded_emulation_file: '请求加载的工程',
  emulation_running: '运行布尔缓存（非实时状态）', input_ports: '输入端口',
  output_ports: '输出端口', center_frequency_mhz: '中心频率回读缓存（MHz）',
  input_power: '输入功率', output_power: '输出功率',
}
const sources: Record<string, string> = {
  unknown: '未知', declared: '人工声明', readback_cache: '既有回读缓存',
  requested_project_cache: '请求缓存（非工程回读）', driver_state_cache: '驱动混合缓存',
  connection_identity_cache: '既有连接身份缓存',
}
const availabilityLabels = {
  driver_not_loaded: 'HAL 未加载信道仿真器驱动', unsupported_adapter: '当前 adapter 不提供 F64 快照',
  simulated: '当前是模拟驱动，不展示为真实 F64 运行态', available: '仅诊断',
}

export function F64RuntimeSnapshotCard({ halChanging = false }: { halChanging?: boolean }) {
  const query = useQuery({ queryKey: ['instruments', 'f64RuntimeSnapshot'], queryFn: fetchF64RuntimeSnapshot,
    staleTime: 0, retry: false, refetchOnWindowFocus: false, refetchOnReconnect: false })
  // 刷新中/失败不沿用 React Query 保留的旧 data。
  const snapshot = !halChanging && query.isSuccess && !query.isFetching && !query.isPaused ? query.data : null
  return <Card withBorder data-testid="f64-runtime-snapshot">
    <Stack gap="xs">
      <Group justify="space-between"><Text fw={600}>F64 运行态只读诊断快照</Text>
        <Button size="xs" onClick={() => void query.refetch()} disabled={halChanging} loading={query.isFetching}>刷新内存快照</Button></Group>
      <Alert color="yellow">缓存时效与执行/会话归属未知；不是实时采样，也不是历史冻结证据。</Alert>
      <Text size="xs" c="dimmed">仅刷新服务器内存，不发送仪器命令。历史冻结证据请在执行详情查看；本页不用于正式 KPI 或现场认证。</Text>
      {halChanging ? <Text>HAL 正在变更；旧快照不再展示。</Text> : query.isError ? <Text c="red">刷新失败；旧快照不再展示。</Text> : !snapshot ? <Text>正在读取服务器内存…</Text> : <>
        <Text size="sm">{availabilityLabels[snapshot.availability]}</Text>
        {snapshot.availability === 'available' && <>
          <Text size="xs">HAL 驱动：{snapshot.instrument_id} · {snapshot.driver_status}；前面板控制保留：{snapshot.local_control_reserved ? '是' : '否'}</Text>
          <Text size="xs">响应生成时间（非采样时间）：{snapshot.generated_at}</Text>
          {snapshot.fields.map(field => <Stack gap={0} key={field.key}>
            <Text size="sm" fw={500}>{labels[field.key] ?? field.key}</Text>
            <Text size="sm" style={{ overflowWrap: 'anywhere' }}>{field.value == null ? '未知（无可信缓存）' : typeof field.value === 'string' ? field.value : JSON.stringify(field.value)}</Text>
            <Text size="xs" c="dimmed">来源：{sources[field.source] ?? field.source} · 采样时间未知 · 时效未知 · 执行/会话归属未知</Text>
          </Stack>)}
        </>}
      </>}
    </Stack>
  </Card>
}
