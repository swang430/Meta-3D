/**
 * CustomCDLProfile (自定义 CDL 簇编辑) 管理界面 — 建/编辑/删自定义 CDL + 簇级参数 (P2-15)。
 *
 * 标称 CDL (CDL-A~E) 是 38.901 内置固定表; 这里 operator 编辑自定义 CDL 的簇级参数 (每簇
 * delay/角度/功率/AS/XPR/子径数), 持久化可复用。测试例配置选 cdl_profile_id → 后端
 * input_mode=custom → ChannelEgine 合成反映自定义簇。
 *
 * 平行 DUTProfileManager: 列表 + Modal 表单 + 软删; 多一个【簇编辑器】(簇数组增删 + 嵌套
 * Modal 编辑单簇)。
 */
import { useMemo, useState } from 'react'
import {
  ActionIcon, Alert, Badge, Button, Group, LoadingOverlay, Modal, NumberInput, Paper,
  Select, SimpleGrid, Stack, Table, Text, Textarea, TextInput, Title, Tooltip,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import { IconAlertTriangle, IconEdit, IconPlus, IconTrash, IconWaveSine } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  createCustomCDLProfile,
  deleteCustomCDLProfile,
  fetchCustomCDLProfiles,
  updateCustomCDLProfile,
  DEFAULT_CLUSTER,
  type CustomCDLProfile,
  type CustomCDLProfileCreatePayload,
  type CDLClusterInput,
} from '../../api/customCdlProfileService'

const KEY = ['custom-cdl-profiles'] as const

interface DraftState {
  name: string
  description: string
  center_frequency_ghz: number | ''
  pathloss_db: number | ''
  is_los: boolean | null           // null = 未声明 (保留原始 nullable, Codex P2 #171)
  k_factor_db: number | ''
  velocity_x_mps: number | ''
  velocity_y_mps: number | ''      // 保全 3 分量, 不丢 y/z (Codex P2 #171)
  velocity_z_mps: number | ''
  clusters: CDLClusterInput[]
}

const EMPTY_DRAFT: DraftState = {
  name: '', description: '', center_frequency_ghz: '', pathloss_db: '',
  is_los: null, k_factor_db: '', velocity_x_mps: '', velocity_y_mps: '',
  velocity_z_mps: '', clusters: [],
}

function profileToDraft(p: CustomCDLProfile): DraftState {
  return {
    name: p.name,
    description: p.description ?? '',
    center_frequency_ghz: p.center_frequency_hz != null ? p.center_frequency_hz / 1e9 : '',
    pathloss_db: p.pathloss_db ?? '',
    is_los: p.is_los ?? null,                    // 保留 null (不 coerce false, Codex P2 #171)
    k_factor_db: p.k_factor_db ?? '',
    velocity_x_mps: p.ue_velocity_mps?.[0] ?? '',
    velocity_y_mps: p.ue_velocity_mps?.[1] ?? '',
    velocity_z_mps: p.ue_velocity_mps?.[2] ?? '',
    clusters: p.clusters ?? [],
  }
}

function draftToPayload(d: DraftState): CustomCDLProfileCreatePayload {
  const num = (n: number | '') => (n === '' ? null : n)
  const blank = (s: string) => (s.trim() === '' ? null : s.trim())
  return {
    name: d.name.trim(),
    description: blank(d.description),
    center_frequency_hz: d.center_frequency_ghz === '' ? null : d.center_frequency_ghz * 1e9,
    pathloss_db: num(d.pathloss_db),
    is_los: d.is_los,
    k_factor_db: num(d.k_factor_db),
    // 保全 3 分量 (Codex P2 #171): 任一分量设了就发全 3 (空当 0); 全空 → null
    ue_velocity_mps:
      d.velocity_x_mps === '' && d.velocity_y_mps === '' && d.velocity_z_mps === ''
        ? null
        : [num(d.velocity_x_mps) ?? 0, num(d.velocity_y_mps) ?? 0, num(d.velocity_z_mps) ?? 0],
    clusters: d.clusters,
  }
}

function numOr0(v: number | string): number {
  return typeof v === 'number' ? v : 0
}

export function CustomCDLProfileManager() {
  const queryClient = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT)
  // 簇编辑: null=关闭; idx<clusters.length=编辑现有; idx===length=新建
  const [editClusterIdx, setEditClusterIdx] = useState<number | null>(null)
  const [clusterDraft, setClusterDraft] = useState<CDLClusterInput>(DEFAULT_CLUSTER)

  const profilesQuery = useQuery({ queryKey: KEY, queryFn: () => fetchCustomCDLProfiles(false) })
  const invalidate = () => queryClient.invalidateQueries({ queryKey: KEY })

  const createMutation = useMutation({
    mutationFn: (p: CustomCDLProfileCreatePayload) => createCustomCDLProfile(p),
    onSuccess: (p) => {
      notifications.show({ title: '自定义 CDL 已创建', message: p.name, color: 'green' })
      setModalOpen(false)
      invalidate()
    },
    onError: (e: unknown) => notifyError('创建失败', e),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: CustomCDLProfileCreatePayload }) =>
      updateCustomCDLProfile(id, payload),
    onSuccess: (p) => {
      notifications.show({ title: '自定义 CDL 已更新', message: p.name, color: 'green' })
      setModalOpen(false)
      invalidate()
    },
    onError: (e: unknown) => notifyError('更新失败', e),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteCustomCDLProfile(id, false),
    onSuccess: () => {
      notifications.show({ title: '自定义 CDL 已删除', message: '已置为非活动', color: 'gray' })
      invalidate()
    },
    onError: (e: unknown) => notifyError('删除失败', e),
  })

  const openCreate = () => { setEditingId(null); setDraft(EMPTY_DRAFT); setModalOpen(true) }
  const openEdit = (p: CustomCDLProfile) => {
    setEditingId(p.id); setDraft(profileToDraft(p)); setModalOpen(true)
  }

  const confirmDelete = (p: CustomCDLProfile) =>
    modals.openConfirmModal({
      title: '删除自定义 CDL',
      children: (
        <Text size="sm">
          确认删除「{p.name}」? 软删除 (置为非活动), 引用它的历史测试例不受影响。
        </Text>
      ),
      labels: { confirm: '删除', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteMutation.mutate(p.id),
    })

  // ── 簇编辑器 ──
  const openAddCluster = () => {
    setClusterDraft({ ...DEFAULT_CLUSTER })
    setEditClusterIdx(draft.clusters.length)
  }
  const openEditCluster = (idx: number) => {
    setClusterDraft({ ...draft.clusters[idx] })
    setEditClusterIdx(idx)
  }
  const removeCluster = (idx: number) =>
    setDraft({ ...draft, clusters: draft.clusters.filter((_, i) => i !== idx) })
  const saveCluster = () => {
    if (editClusterIdx === null) return
    const next = [...draft.clusters]
    next[editClusterIdx] = clusterDraft
    setDraft({ ...draft, clusters: next })
    setEditClusterIdx(null)
  }

  const submit = () => {
    if (draft.name.trim() === '') {
      notifications.show({ title: '名称必填', message: '不能为空', color: 'red' })
      return
    }
    if (draft.clusters.length === 0) {
      notifications.show({ title: '至少 1 簇', message: '自定义 CDL 需至少一个簇', color: 'red' })
      return
    }
    const payload = draftToPayload(draft)
    if (editingId) updateMutation.mutate({ id: editingId, payload })
    else createMutation.mutate(payload)
  }

  const profiles = profilesQuery.data ?? []
  const saving = createMutation.isPending || updateMutation.isPending
  const draftValid = useMemo(
    () => draft.name.trim() !== '' && draft.clusters.length > 0,
    [draft.name, draft.clusters.length],
  )

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Group gap="xs">
          <IconWaveSine size={22} />
          <Title order={3}>自定义 CDL 信道</Title>
        </Group>
        <Button leftSection={<IconPlus size={16} />} onClick={openCreate}>
          新建自定义 CDL
        </Button>
      </Group>
      {/* P2-16 deprecate-legacy: 消费已收敛到 ChannelAsset (信道工作台)。此为 legacy 编辑器,
          仅供存量档案兼容; 新建/编辑请去信道工作台建 custom_static ChannelAsset。 */}
      <Alert
        icon={<IconAlertTriangle size={18} />}
        color="orange"
        variant="light"
        title="此为 legacy 编辑器 — 请改用「信道工作台」"
      >
        自定义 CDL 已统一为信道工作台的 <b>ChannelAsset（自定义 CDL / custom_static）</b>，测试执行
        的消费也已收敛到 ChannelAsset。请去 <b>侧栏「信道工作台」</b> 新建 / 编辑 custom_static 资产，
        并在测试步骤用「统一信道资产」引用。此处仅供存量档案兼容（尚未迁移的旧档案仍可在此编辑）。
      </Alert>
      <Text size="sm" c="dimmed">
        编辑自定义 CDL 的簇级参数 (每簇时延/角度/功率/角度扩展/子径数), 持久化可复用。标称
        CDL-A~E 是 38.901 固定表; 测试例选自定义 CDL → 后端 input_mode=custom → ChannelEgine 合成。
      </Text>

      <Paper withBorder pos="relative">
        <LoadingOverlay visible={profilesQuery.isLoading} />
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>名称</Table.Th>
              <Table.Th>簇数</Table.Th>
              <Table.Th>中心频率</Table.Th>
              <Table.Th>LOS</Table.Th>
              <Table.Th>描述</Table.Th>
              <Table.Th>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {profiles.length === 0 && !profilesQuery.isLoading ? (
              <Table.Tr>
                <Table.Td colSpan={6}>
                  <Text size="sm" c="dimmed" ta="center" py="md">
                    还没有自定义 CDL — 点「新建自定义 CDL」添加。
                  </Text>
                </Table.Td>
              </Table.Tr>
            ) : (
              profiles.map((p) => (
                <Table.Tr key={p.id}>
                  <Table.Td><Text fw={500}>{p.name}</Text></Table.Td>
                  <Table.Td><Badge variant="light">{p.clusters?.length ?? 0} 簇</Badge></Table.Td>
                  <Table.Td>
                    {p.center_frequency_hz != null
                      ? `${(p.center_frequency_hz / 1e9).toFixed(3)} GHz`
                      : '—'}
                  </Table.Td>
                  <Table.Td>
                    {p.is_los == null ? '—' : p.is_los
                      ? <Badge color="green" variant="light">LOS</Badge>
                      : <Badge color="gray" variant="light">NLOS</Badge>}
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" c="dimmed" lineClamp={1}>{p.description ?? '—'}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      <Tooltip label="编辑">
                        <ActionIcon variant="subtle" onClick={() => openEdit(p)}>
                          <IconEdit size={16} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label="删除 (软删除)">
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          onClick={() => confirmDelete(p)}
                          loading={deleteMutation.isPending}
                        >
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))
            )}
          </Table.Tbody>
        </Table>
      </Paper>

      {/* 主 Modal: 顶层物理 + 簇编辑器 */}
      <Modal
        opened={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editingId ? '编辑自定义 CDL' : '新建自定义 CDL'}
        size="xl"
      >
        <Stack gap="md">
          <TextInput
            label="名称"
            description="唯一标识, 测试例配置里按此选"
            required
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.currentTarget.value })}
          />
          <Textarea
            label="描述"
            autosize
            minRows={1}
            value={draft.description}
            onChange={(e) => setDraft({ ...draft, description: e.currentTarget.value })}
          />
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <NumberInput
              label="中心频率 (GHz)"
              description="留空=测试时绑"
              decimalScale={3}
              value={draft.center_frequency_ghz}
              onChange={(v) =>
                setDraft({ ...draft, center_frequency_ghz: typeof v === 'number' ? v : '' })}
            />
            <NumberInput
              label="路损 (dB)"
              value={draft.pathloss_db}
              onChange={(v) => setDraft({ ...draft, pathloss_db: typeof v === 'number' ? v : '' })}
            />
            <NumberInput
              label="K 因子 (dB)"
              description="仅 LOS"
              value={draft.k_factor_db}
              onChange={(v) => setDraft({ ...draft, k_factor_db: typeof v === 'number' ? v : '' })}
            />
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Select
              label="视距 (LOS)"
              description="留空=不声明 (保留 null)"
              data={[{ value: 'true', label: 'LOS' }, { value: 'false', label: 'NLOS' }]}
              value={draft.is_los === null ? null : String(draft.is_los)}
              onChange={(v) => setDraft({ ...draft, is_los: v === null ? null : v === 'true' })}
              clearable
              placeholder="(未设)"
            />
            <Group gap="xs" grow>
              <NumberInput label="UE 速度 vx (m/s)" value={draft.velocity_x_mps}
                onChange={(v) =>
                  setDraft({ ...draft, velocity_x_mps: typeof v === 'number' ? v : '' })} />
              <NumberInput label="vy" value={draft.velocity_y_mps}
                onChange={(v) =>
                  setDraft({ ...draft, velocity_y_mps: typeof v === 'number' ? v : '' })} />
              <NumberInput label="vz" value={draft.velocity_z_mps}
                onChange={(v) =>
                  setDraft({ ...draft, velocity_z_mps: typeof v === 'number' ? v : '' })} />
            </Group>
          </SimpleGrid>

          {/* 簇编辑器 */}
          <Group justify="space-between" mt="sm">
            <Text fw={500} size="sm">簇列表 ({draft.clusters.length})</Text>
            <Button
              size="compact-sm"
              variant="light"
              leftSection={<IconPlus size={14} />}
              onClick={openAddCluster}
            >
              添加簇
            </Button>
          </Group>
          {draft.clusters.length === 0 ? (
            <Text size="sm" c="dimmed">无簇 — 至少加一个簇 (点「添加簇」)。</Text>
          ) : (
            <Stack gap="xs">
              {draft.clusters.map((c, idx) => (
                <Paper key={idx} withBorder p="xs">
                  <Group justify="space-between">
                    <Stack gap={0}>
                      <Text size="sm" fw={500}>簇 {idx + 1}</Text>
                      <Text size="xs" c="dimmed">
                        τ={c.delay_s}s · AoA={c.aoa_deg}° AoD={c.aod_deg}° · P={c.power_linear} ·{' '}
                        {c.num_rays ?? 20} rays
                      </Text>
                    </Stack>
                    <Group gap="xs">
                      <ActionIcon variant="subtle" onClick={() => openEditCluster(idx)}>
                        <IconEdit size={15} />
                      </ActionIcon>
                      <ActionIcon variant="subtle" color="red" onClick={() => removeCluster(idx)}>
                        <IconTrash size={15} />
                      </ActionIcon>
                    </Group>
                  </Group>
                </Paper>
              ))}
            </Stack>
          )}

          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={() => setModalOpen(false)}>取消</Button>
            <Button onClick={submit} loading={saving} disabled={!draftValid}>
              {editingId ? '保存' : '创建'}
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* 簇编辑 Modal */}
      <Modal
        opened={editClusterIdx !== null}
        onClose={() => setEditClusterIdx(null)}
        title={`编辑簇 ${(editClusterIdx ?? 0) + 1}`}
        size="lg"
      >
        <Stack gap="sm">
          <SimpleGrid cols={2}>
            <NumberInput label="时延 delay_s (s)" min={0} decimalScale={10}
              value={clusterDraft.delay_s}
              onChange={(v) => setClusterDraft({ ...clusterDraft, delay_s: numOr0(v) })} />
            <NumberInput label="功率 power_linear" min={0} decimalScale={4} step={0.01}
              value={clusterDraft.power_linear}
              onChange={(v) => setClusterDraft({ ...clusterDraft, power_linear: numOr0(v) })} />
            <NumberInput label="AoA (deg)" value={clusterDraft.aoa_deg}
              onChange={(v) => setClusterDraft({ ...clusterDraft, aoa_deg: numOr0(v) })} />
            <NumberInput label="AoD (deg)" value={clusterDraft.aod_deg}
              onChange={(v) => setClusterDraft({ ...clusterDraft, aod_deg: numOr0(v) })} />
            <NumberInput label="ZoA (deg)" min={0} max={180} value={clusterDraft.zoa_deg ?? 90}
              onChange={(v) => setClusterDraft({ ...clusterDraft, zoa_deg: numOr0(v) })} />
            <NumberInput label="ZoD (deg)" min={0} max={180} value={clusterDraft.zod_deg ?? 90}
              onChange={(v) => setClusterDraft({ ...clusterDraft, zod_deg: numOr0(v) })} />
            <NumberInput label="AS AoA (deg)" min={0} value={clusterDraft.as_aoa_deg ?? 0}
              onChange={(v) => setClusterDraft({ ...clusterDraft, as_aoa_deg: numOr0(v) })} />
            <NumberInput label="AS AoD (deg)" min={0} value={clusterDraft.as_aod_deg ?? 0}
              onChange={(v) => setClusterDraft({ ...clusterDraft, as_aod_deg: numOr0(v) })} />
            <NumberInput label="AS ZoA (deg)" description="兼探头权重 el 宽" min={0}
              value={clusterDraft.as_zoa_deg ?? 0}
              onChange={(v) => setClusterDraft({ ...clusterDraft, as_zoa_deg: numOr0(v) })} />
            <NumberInput label="AS ZoD (deg)" min={0} value={clusterDraft.as_zod_deg ?? 0}
              onChange={(v) => setClusterDraft({ ...clusterDraft, as_zod_deg: numOr0(v) })} />
            <NumberInput label="XPR (dB)" value={clusterDraft.xpr_db ?? undefined}
              onChange={(v) =>
                setClusterDraft({ ...clusterDraft, xpr_db: typeof v === 'number' ? v : null })} />
            <NumberInput label="子径数 num_rays" min={1} value={clusterDraft.num_rays ?? 20}
              onChange={(v) =>
                setClusterDraft({ ...clusterDraft, num_rays: typeof v === 'number' ? v : 20 })} />
          </SimpleGrid>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setEditClusterIdx(null)}>取消</Button>
            <Button onClick={saveCluster} disabled={clusterDraft.power_linear <= 0}>保存簇</Button>
          </Group>
        </Stack>
      </Modal>
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

export default CustomCDLProfileManager
