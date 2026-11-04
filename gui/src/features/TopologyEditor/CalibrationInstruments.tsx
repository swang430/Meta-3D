import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Stack, Text } from '@mantine/core'
import { fetchInstrumentCatalog, fetchReadiness } from '../../api/service'
import type { SwitchTopology } from '../../api/switchTopologyService'
import { instrumentPresentation } from './calibrationChainView'

export function CalibrationInstruments({ graph, labId, onOpenResources }: {
  graph: SwitchTopology; labId: string; onOpenResources?: () => void
}) {
  const catalog = useQuery({ queryKey: ['instruments', 'catalog'], queryFn: fetchInstrumentCatalog, retry: false })
  const readiness = useQuery({ queryKey: ['cockpit', 'readiness', labId], queryFn: () => fetchReadiness(labId), retry: false })
  const fresh = !readiness.isFetching && !readiness.isError && !readiness.isPaused
  const current = fresh && readiness.data?.lab_profile.profile_id === labId ? readiness.data : undefined
  const categories = !catalog.isFetching && !catalog.isError && !catalog.isPaused ? catalog.data?.categories ?? [] : []
  const instruments = graph.nodes.filter(node => ['channel_emulator', 'ce_port', 'signal_analyzer', 'sa_port', 'vna', 'signal_generator'].includes(node.type))
  return <Card withBorder padding="sm" data-testid="calibration-instruments"><Stack gap="xs">
    <Text fw={600}>校准仪器与接线</Text>
    <Text size="xs">当前自动采集：F64内部单音源 → 所选通路 → 参考天线／接收线缆 → 分析仪。矢网及独立信号源仅展示声明，不开放此方法的自动控制。</Text>
    {!instruments.some(node => ['channel_emulator', 'ce_port'].includes(node.type)) && <Alert color="yellow">缺少激励端节点声明</Alert>}
    {!instruments.some(node => ['signal_analyzer', 'sa_port'].includes(node.type)) && <Alert color="yellow">缺少分析仪节点声明</Alert>}
    {!graph.nodes.some(node => node.type === 'reference_antenna') && <Alert color="yellow">缺少参考天线节点声明</Alert>}
    {catalog.isError && <Alert color="red">仪器资源读取失败：{catalog.error.message}</Alert>}
    {!current && <Text c="orange" size="sm">运行快照读取中、不可用或实验室身份不符；运行状态未知。</Text>}
    {instruments.map(node => {
      const shown = instrumentPresentation(node, categories, current, labId)
      return <div key={node.id}>
        <Text size="sm" fw={500}>{node.label}</Text>
        <Text size="xs">{shown.resource}</Text><Text size="xs">{shown.snapshot}</Text><Text size="xs">{shown.binding}</Text>
        <Text size="xs">端口声明：{Array.isArray(node.params.ports) ? node.params.ports.join('、') || '未填写' : '未填写'}；{graph.connections.some(edge => edge.source === node.id || edge.target === node.id) ? '已有接线声明，实物仍须本次确认' : '尚未声明接线'}</Text>
      </div>
    })}
    <Button variant="light" size="xs" loading={catalog.isFetching || readiness.isFetching} onClick={() => { void catalog.refetch(); void readiness.refetch() }}>刷新仪器状态</Button>
    {onOpenResources && <Button variant="subtle" size="xs" onClick={onOpenResources}>前往仪器资源核对驱动</Button>}
  </Stack></Card>
}
