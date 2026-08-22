/**
 * 信道工作台 (Channel Workbench) — P2-16 S4: 统一管理多态 ChannelAsset 信道资产。
 *
 * 收口设计 §1.2 的「信道资产四分五裂」: 四源 (standard_3gpp / custom_static / rt_dynamic /
 * vendor_file) 统一为单一 ChannelAsset 实体, 经 channelAssetService (/channel-assets) 管理。
 *
 * S4-1 (本切片): 工作台 shell — 按 source_type 分类列表 + 查看详情 + 软删。建/编辑 (四
 * source_type payload 编辑器) 是 S4-2~S4-4; 旧编辑器 (AssetProfiles CDL tab / 仪器抽屉 SCD
 * 卡片) deprecate + 浏览器闭环是 S4-5/S4-6。
 */
import { useState } from 'react'
import {
  ActionIcon, Alert, Badge, Box, Button, Code, Group, LoadingOverlay, Modal, Paper,
  ScrollArea, SegmentedControl, Stack, Switch, Table, Text, Title, Tooltip,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import { IconBroadcast, IconEdit, IconEye, IconFileSearch, IconPlus, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  deleteChannelAsset,
  fetchChannelAssets,
  scanSMUProjects,
  syncSMUProjects,
  type ChannelAsset,
  type ChannelSourceType,
  type SMUProjectSyncPreview,
} from '../../api/channelAssetService'
import { ChannelAssetForm } from './ChannelAssetForm'

const SOURCE_LABEL: Record<ChannelSourceType, string> = {
  standard_3gpp: '标准 3GPP',
  custom_static: '自定义 CDL',
  rt_dynamic: 'RT 动态',
  vendor_file: '厂商文件',
}
const SOURCE_COLOR: Record<ChannelSourceType, string> = {
  standard_3gpp: 'blue',
  custom_static: 'teal',
  rt_dynamic: 'grape',
  vendor_file: 'orange',
}
const TARGET_LABEL: Record<string, string> = {
  asc_baked: 'ASC 烘焙',
  b2_parametric: 'B-2 参数化',
  gcm_native: 'GCM native',
}

type SourceFilter = 'all' | ChannelSourceType

export function ChannelWorkbench() {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<SourceFilter>('all')
  const [includeInactive, setIncludeInactive] = useState(false)
  const [viewing, setViewing] = useState<ChannelAsset | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editingAsset, setEditingAsset] = useState<ChannelAsset | null>(null)
  const [smuOpen, setSMUOpen] = useState(false)
  const [smuPreview, setSMUPreview] = useState<SMUProjectSyncPreview | null>(null)
  const openCreate = () => { setEditingAsset(null); setFormOpen(true) }
  const openEdit = (a: ChannelAsset) => { setEditingAsset(a); setFormOpen(true) }

  const assetsQuery = useQuery({
    queryKey: ['channel-assets', filter, includeInactive],
    queryFn: () =>
      fetchChannelAssets({
        sourceType: filter === 'all' ? undefined : filter,
        includeInactive,
      }),
  })
  // 前缀失效 (covers ['channel-assets', filter, includeInactive] 各变体)
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['channel-assets'] })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteChannelAsset(id, false),
    onSuccess: () => {
      notifications.show({ title: '信道资产已删除', message: '已置为非活动 (软删)', color: 'gray' })
      invalidate()
    },
    onError: (e: unknown) => notifyError('删除失败', e),
  })

  const scanMutation = useMutation({
    mutationFn: scanSMUProjects,
    onSuccess: (preview) => { setSMUPreview(preview); setSMUOpen(true) },
    onError: (e: unknown) => notifyError('扫描失败', e),
  })

  const syncMutation = useMutation({
    mutationFn: syncSMUProjects,
    onSuccess: (result) => {
      setSMUPreview(result.preview)
      notifications.show({
        title: 'F64 工程真值已同步',
        message: `更新 ${result.updated_count} 个资产`,
        color: 'green',
      })
      queryClient.invalidateQueries({ queryKey: ['channel-assets'] })
      queryClient.invalidateQueries({ queryKey: ['instruments', 'channelModels'] })
      queryClient.invalidateQueries({ queryKey: ['channelModels'] })
    },
    onError: (e: unknown) => notifyError('同步失败', e),
  })

  const confirmDelete = (a: ChannelAsset) =>
    modals.openConfirmModal({
      title: '删除信道资产',
      children: (
        <Text size="sm">
          软删信道资产 <b>{a.name}</b> (置为非活动)？历史测试例引用仍有效, 勾选「含非活动」可查看。
        </Text>
      ),
      labels: { confirm: '软删', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteMutation.mutate(a.id),
    })

  const assets = assetsQuery.data ?? []

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={3}>
            <Group gap="xs"><IconBroadcast size={22} /> 信道工作台</Group>
          </Title>
          <Text size="sm" c="dimmed">
            统一管理多态信道资产 (ChannelAsset)：标准 3GPP / 自定义 CDL / RT 动态 / 厂商文件。
            四源统一，供测试例按 source_type 引用注入。
          </Text>
        </div>
        <Group gap="sm">
          <Button
            variant="light"
            leftSection={<IconFileSearch size={16} />}
            loading={scanMutation.isPending}
            onClick={() => scanMutation.mutate()}
          >
            扫描 F64 工程
          </Button>
          <Switch
            label="含非活动"
            checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.currentTarget.checked)}
          />
          <Button leftSection={<IconPlus size={16} />} onClick={openCreate}>新建</Button>
        </Group>
      </Group>

      <SegmentedControl
        value={filter}
        onChange={(v) => setFilter(v as SourceFilter)}
        data={[
          { label: '全部', value: 'all' },
          ...(Object.keys(SOURCE_LABEL) as ChannelSourceType[]).map((s) => ({
            label: SOURCE_LABEL[s],
            value: s,
          })),
        ]}
      />

      <Paper withBorder pos="relative">
        <LoadingOverlay visible={assetsQuery.isLoading} />
        {assets.length === 0 && !assetsQuery.isLoading ? (
          <Box p="xl" ta="center">
            <Text c="dimmed">
              {filter === 'all'
                ? '暂无信道资产'
                : `暂无「${SOURCE_LABEL[filter as ChannelSourceType]}」资产`}
              。点「新建」创建：标准 3GPP / 自定义 CDL（簇）/ RT 动态（多快照射线）/ 厂商文件。
            </Text>
          </Box>
        ) : (
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>名称</Table.Th>
                <Table.Th>来源</Table.Th>
                <Table.Th>规范名</Table.Th>
                <Table.Th>注入路径</Table.Th>
                <Table.Th>中心频率</Table.Th>
                <Table.Th>状态</Table.Th>
                <Table.Th ta="right">操作</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {assets.map((a) => (
                <Table.Tr key={a.id} opacity={a.is_active ? 1 : 0.5}>
                  <Table.Td><Text fw={500}>{a.name}</Text></Table.Td>
                  <Table.Td>
                    <Badge color={SOURCE_COLOR[a.source_type]} variant="light">
                      {SOURCE_LABEL[a.source_type]}
                    </Badge>
                  </Table.Td>
                  <Table.Td><Text size="sm" c="dimmed">{a.canonical_name ?? '—'}</Text></Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      {a.allowed_targets.map((t) => (
                        <Badge key={t} size="sm" variant="outline">{TARGET_LABEL[t] ?? t}</Badge>
                      ))}
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {a.center_frequency_hz != null
                        ? `${(a.center_frequency_hz / 1e6).toFixed(3)} MHz`
                        : '—'}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge color={a.is_active ? 'green' : 'gray'} variant="dot">
                      {a.is_active ? '活动' : '非活动'}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} justify="flex-end">
                      <Tooltip label="编辑">
                        <ActionIcon variant="subtle" color="blue" onClick={() => openEdit(a)}>
                          <IconEdit size={18} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label="查看详情">
                        <ActionIcon variant="subtle" onClick={() => setViewing(a)}>
                          <IconEye size={18} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label={a.is_active ? '软删' : '已非活动'}>
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          disabled={!a.is_active}
                          onClick={() => confirmDelete(a)}
                        >
                          <IconTrash size={18} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Paper>

      <Modal opened={viewing != null} onClose={() => setViewing(null)} title={viewing?.name} size="lg">
        {viewing && <AssetDetail asset={viewing} />}
      </Modal>

      <ChannelAssetForm opened={formOpen} asset={editingAsset} onClose={() => setFormOpen(false)} />

      <Modal
        opened={smuOpen}
        onClose={() => setSMUOpen(false)}
        title="F64 .smu 工程真值预览"
        size="xl"
      >
        {smuPreview && (
          <Stack gap="sm">
            <Alert color="blue" variant="light">
              只读取服务端配置的 SMB 挂载副本；同步时会重新扫描，不接受界面提交频率。
            </Alert>
            <Group gap="xs">
              <Badge color="green">可同步 {smuPreview.items.filter((x) => x.sync_status === 'syncable').length}</Badge>
              <Badge color="gray">受保护 {smuPreview.items.filter((x) => !['syncable', 'already_synced'].includes(x.sync_status)).length}</Badge>
              <Badge variant="outline">已扫描 {smuPreview.total_files}</Badge>
            </Group>
            <ScrollArea.Autosize mah={460}>
              <Table striped withTableBorder>
                <Table.Thead><Table.Tr>
                  <Table.Th>工程</Table.Th><Table.Th>资产</Table.Th><Table.Th>Group 0</Table.Th><Table.Th>裁决</Table.Th>
                </Table.Tr></Table.Thead>
                <Table.Tbody>
                  {smuPreview.items.map((item) => (
                    <Table.Tr key={item.instrument_path}>
                      <Table.Td><Text size="sm">{item.relative_path}</Text></Table.Td>
                      <Table.Td><Text size="sm">{item.asset_name ?? '—'}</Text></Table.Td>
                      <Table.Td><Text size="sm">{item.primary_center_frequency_hz == null ? '—' : `${(item.primary_center_frequency_hz / 1e6).toFixed(6)} MHz`}</Text></Table.Td>
                      <Table.Td>
                        <Badge color={item.sync_status === 'syncable' ? 'green' : item.sync_status === 'already_synced' ? 'blue' : 'gray'}>
                          {item.sync_status}
                        </Badge>
                        <Text size="xs" c="dimmed">{item.sync_detail}</Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea.Autosize>
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setSMUOpen(false)}>关闭</Button>
              <Button
                loading={syncMutation.isPending}
                disabled={!smuPreview.items.some((x) => x.sync_status === 'syncable')}
                onClick={() => modals.openConfirmModal({
                  title: '确认同步 F64 工程真值',
                  children: <Text size="sm">服务端将重新扫描，并仅同步仍然精确匹配且可证明的工程。受保护项不会修改。</Text>,
                  labels: { confirm: '确认同步', cancel: '取消' },
                  onConfirm: () => syncMutation.mutate(),
                })}
              >
                确认同步
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  )
}

function AssetDetail({ asset }: { asset: ChannelAsset }) {
  const rows: Array<[string, string]> = [
    ['来源 source_type', SOURCE_LABEL[asset.source_type]],
    ['规范名 canonical_name', asset.canonical_name ?? '—'],
    ['派生自 derived_from', asset.derived_from ?? '—'],
    ['注入路径 allowed_targets', asset.allowed_targets.map((t) => TARGET_LABEL[t] ?? t).join(' / ')],
    ['中心频率', asset.center_frequency_hz != null ? `${(asset.center_frequency_hz / 1e6).toFixed(3)} MHz` : '—'],
    ['带宽', asset.bandwidth_mhz != null ? `${asset.bandwidth_mhz} MHz` : '—'],
    ['LOS', asset.is_los == null ? '未声明' : asset.is_los ? '是' : '否'],
    ['K 因子', asset.k_factor_db != null ? `${asset.k_factor_db} dB` : '—'],
    ['UE 速度', asset.ue_velocity_mps ? `[${asset.ue_velocity_mps.join(', ')}] m/s` : '—'],
    ['关联文件', asset.associated_file_path ?? '—'],
    ['描述', asset.description ?? '—'],
    ['状态', asset.is_active ? '活动' : '非活动'],
  ]
  return (
    <Stack gap="sm">
      <Table withRowBorders={false}>
        <Table.Tbody>
          {rows.map(([k, v]) => (
            <Table.Tr key={k}>
              <Table.Td style={{ width: 180 }}><Text size="sm" c="dimmed">{k}</Text></Table.Td>
              <Table.Td><Text size="sm">{v}</Text></Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <div>
        <Text size="sm" c="dimmed" mb={4}>payload (多态主体)</Text>
        <ScrollArea.Autosize mah={300}>
          <Code block>{JSON.stringify(asset.payload, null, 2)}</Code>
        </ScrollArea.Autosize>
      </div>
    </Stack>
  )
}

function notifyError(title: string, e: unknown) {
  const detail =
    (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
    (e as Error)?.message ??
    '未知错误'
  notifications.show({ title, message: String(detail), color: 'red' })
}
