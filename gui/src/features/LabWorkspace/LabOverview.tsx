import { useQuery } from '@tanstack/react-query'
import { Alert, Badge, Button, Card, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { fetchInstrumentCatalog, fetchReadiness } from '../../api/service'
import { fetchRFChains } from '../../api/labProfileService'
import { useOperationalLab } from '../OperationalLab'
import type { BaseStationBindingPreviewResponse, ChannelEmulatorBindingPreviewResponse } from '../../types/api'

function BindingCard({ title, binding }: {
  title: string
  binding: BaseStationBindingPreviewResponse | ChannelEmulatorBindingPreviewResponse | null
}) {
  const diagnostic = binding?.execution_mode === 'simulated' || binding?.status === 'diagnostic_unbound'
  return <Card withBorder>
    <Stack gap="xs">
      <Title order={4}>{title}</Title>
      <Badge color={!binding || binding.status === 'invalid' ? 'red' : diagnostic ? 'yellow' : 'blue'}>
        {diagnostic ? '仅诊断' : binding?.status ?? '未解析'}
      </Badge>
      <Text>{binding?.model_name ?? '未解析型号'}</Text>
      <Text>{binding?.adapter_id ?? '未解析adapter'}</Text>
      <Text size="sm" style={{ overflowWrap: 'anywhere' }}>binding digest：{binding?.binding_digest ?? '未解析'}</Text>
      <Text size="sm">{binding?.detail ?? '服务器未返回绑定投影'}</Text>
    </Stack>
  </Card>
}

export function LabOverview() {
  const { selectedLabProfileId: labId, selectedLabProfile: lab, chamberId, chamberName, loading, error } = useOperationalLab()
  const enabled = Boolean(labId) && !loading && !error
  const catalog = useQuery({
    queryKey: ['instruments', 'catalog'],
    queryFn: fetchInstrumentCatalog,
    enabled,
    retry: false,
  })
  const readiness = useQuery({
    queryKey: ['cockpit', 'readiness', labId ?? 'unselected'],
    queryFn: () => fetchReadiness(labId!),
    enabled,
    retry: false,
  })
  const chains = useQuery({
    queryKey: ['lab-workspace', 'rf-chains', labId],
    queryFn: () => fetchRFChains(labId!),
    enabled,
    retry: false,
  })

  if (loading) return <Text>LabProfile加载中…</Text>
  if (error) return <Alert color="red">LabProfile读取失败：{error}</Alert>
  if (!labId || !lab) return <Alert color="yellow">请先在顶部选择LabProfile；未选择时不读取实验室总览。</Alert>

  const report = readiness.data
  const identityMismatch = report && (report.lab_profile.profile_id !== labId
    || (report.base_station_binding && report.base_station_binding.lab_profile_id !== labId)
    || (report.channel_emulator_binding && report.channel_emulator_binding.lab_profile_id !== labId)
    || report.base_station_testcase_compatibility.lab_profile_id !== labId)
  const rf = chains.data
  const rfMismatch = rf && (rf.lab_profile_id !== labId || rf.chamber_id !== chamberId)

  return <Stack gap="md">
    <Group justify="space-between">
      <Title order={3}>实验室总览：{lab.name}</Title>
      <Button onClick={() => { void catalog.refetch(); void readiness.refetch(); void chains.refetch() }}
        loading={catalog.isFetching || readiness.isFetching || chains.isFetching || catalog.isPaused || readiness.isPaused || chains.isPaused}>刷新总览</Button>
    </Group>
    <Alert color="blue">只读总览不保存、不加载仪器、不同步LabProfile。用例兼容性未评估；此处不表示正式测试资格。</Alert>
    <Card withBorder>
      <Text>LabProfile：{lab.name}</Text>
      <Text size="sm" style={{ overflowWrap: 'anywhere' }}>{labId}</Text>
      <Text>绑定暗室：{chamberName ?? '未绑定暗室'}</Text>
      {!chamberId && <Alert color="yellow">未绑定暗室，暗室相关配置尚不可解析。</Alert>}
    </Card>
    <Card withBorder data-testid="lab-saved-resources">
      <Title order={4}>当前保存资源（全局目录）</Title>
      <Text size="sm">保存值不是本LabProfile执行绑定，也不证明HAL已激活。</Text>
      {catalog.isError ? <Alert color="red">保存资源读取失败：{catalog.error.message}</Alert>
        : catalog.isPaused ? <Alert color="yellow">保存资源读取暂停；旧目录不作为刷新成功结果。</Alert>
        : catalog.isFetching ? <Text>保存资源读取中…</Text>
        : catalog.data ? catalog.data.categories.length ? catalog.data.categories.map(category => <Text key={category.key}
          size="sm" style={{ overflowWrap: 'anywhere' }}>
          {category.label}：{category.models.find(model => model.id === category.selectedModelId)?.model ?? '未选择型号'}
          {' · '}{category.connection.endpoint || '未设置端点'}{' · '}{category.driverMode}
        </Text>) : <Text>当前目录无保存资源。</Text> : <Text>尚未取得保存资源。</Text>}
    </Card>
    {readiness.isError ? <Alert color="red">配置快照读取失败：{readiness.error.message}</Alert>
      : readiness.isPaused ? <Alert color="yellow">配置快照读取暂停，等待网络恢复；旧快照不作为刷新成功结果。</Alert>
      : readiness.isFetching ? <Text>配置快照读取中…</Text>
      : identityMismatch ? <Alert color="red">响应实验室身份不一致；拒绝展示其他LabProfile快照。</Alert>
      : report ? <>
        <Text size="sm">服务器快照时间：{report.generated_at_iso}</Text>
        <Text>{report.available ? 'HAL快照已返回（不代表正式就绪）' : 'HAL尚未初始化'}</Text>
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <BindingCard title="基站执行绑定" binding={report.base_station_binding} />
          <BindingCard title="信道仿真器执行绑定" binding={report.channel_emulator_binding} />
        </SimpleGrid>
        <Card withBorder>
          <Title order={4}>HAL分类快照</Title>
          <Text size="sm">运行快照不是已保存资源，也不是冻结执行的实测结果。</Text>
          {report.drivers.length ? report.drivers.map(driver => <Text key={driver.category} size="sm"
            style={{ overflowWrap: 'anywhere' }}>{driver.category}：{driver.model} · {driver.endpoint} · {driver.status} · {driver.detail}</Text>)
            : <Text>无已加载驱动快照</Text>}
        </Card>
      </> : <Alert color="yellow">配置快照未取得。</Alert>}
    <Card withBorder>
      <Title order={4}>射频拓扑与链路</Title>
      {chains.isError ? <Alert color="red">射频链路读取失败：{chains.error.message}</Alert>
        : chains.isPaused ? <Alert color="yellow">射频链路读取暂停，等待网络恢复。</Alert>
        : chains.isFetching ? <Text>射频链路读取中…</Text>
        : rfMismatch ? <Alert color="red">射频响应实验室身份不一致；拒绝展示分叉暗室或拓扑。</Alert>
        : rf ? <Stack gap="xs">
          <Text>拓扑：{rf.topology_name ?? '未解析拓扑'}</Text>
          <Text>模式：{rf.operating_mode} · 服务器返回链路数：{rf.chains.length}</Text>
          {!rf.success && <Badge color="yellow">链路尚未解析成功</Badge>}
          {rf.warnings.map((warning, index) => <Text key={index} size="sm" c="orange">{warning}</Text>)}
        </Stack> : <Text>未取得射频链路。</Text>}
    </Card>
  </Stack>
}
