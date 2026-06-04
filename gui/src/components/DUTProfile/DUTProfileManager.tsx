/**
 * DUTProfile (被测设备自声明能力) 管理界面 — 填写/编辑/删除 DUT 能力档案。
 *
 * 这是用户问「DUT 声明的 GUI 在哪里」的主答案: operator 在规划期 (attach 前) 这里建/管
 * DUT 自声明能力 (max layers/调制/频段/UE category/双工)。TestCase 配置 (MIMOOTAConfigForm)
 * 选其中一个 → precheck section 2.3 拿请求跟声明比, 请求 > 声明提前 fail。
 *
 * 平行 ProbeManager 的内联 CRUD 模式, 但独立成组件 (App.tsx 已 178KB)。Mantine 表格 + Modal 表单。
 * 合法值 (调制/双工) 由 dutProfileService 导出常量给, 跟后端 _validate 同源。
 */
import { useMemo, useState } from 'react'
import {
  ActionIcon,
  Badge,
  Button,
  Group,
  LoadingOverlay,
  Modal,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  TagsInput,
  Text,
  Textarea,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import { IconDeviceMobile, IconEdit, IconPlus, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  createDUTProfile,
  deleteDUTProfile,
  DUT_DUPLEX_OPTIONS,
  DUT_MODULATION_OPTIONS,
  fetchDUTProfiles,
  updateDUTProfile,
  type DUTProfile,
  type DUTProfileCreatePayload,
} from '../../api/dutProfileService'

const DUT_PROFILES_KEY = ['dut-profiles'] as const

/** 表单草稿 — 数字字段用 number|'' (NumberInput 空态), 提交时转 number|null。 */
interface DraftState {
  name: string
  manufacturer: string
  model_name: string
  description: string
  max_dl_layers: number | ''
  max_ul_layers: number | ''
  max_modulation_dl: string | null
  max_modulation_ul: string | null
  ue_category: string
  duplex_mode: string | null
  supported_bands: string[]
}

const EMPTY_DRAFT: DraftState = {
  name: '',
  manufacturer: '',
  model_name: '',
  description: '',
  max_dl_layers: '',
  max_ul_layers: '',
  max_modulation_dl: null,
  max_modulation_ul: null,
  ue_category: '',
  duplex_mode: null,
  supported_bands: [],
}

function profileToDraft(p: DUTProfile): DraftState {
  return {
    name: p.name,
    manufacturer: p.manufacturer ?? '',
    model_name: p.model_name ?? '',
    description: p.description ?? '',
    max_dl_layers: p.max_dl_layers ?? '',
    max_ul_layers: p.max_ul_layers ?? '',
    max_modulation_dl: p.max_modulation_dl ?? null,
    max_modulation_ul: p.max_modulation_ul ?? null,
    ue_category: p.ue_category ?? '',
    duplex_mode: p.duplex_mode ?? null,
    supported_bands: p.supported_bands ?? [],
  }
}

/** 草稿 → API payload。空串/空数组 → null (显式清空该声明; 后端 exclude_unset 下 null=清空)。 */
function draftToPayload(d: DraftState): DUTProfileCreatePayload {
  const blank = (s: string) => (s.trim() === '' ? null : s.trim())
  const num = (n: number | '') => (n === '' ? null : n)
  return {
    name: d.name.trim(),
    manufacturer: blank(d.manufacturer),
    model_name: blank(d.model_name),
    description: blank(d.description),
    max_dl_layers: num(d.max_dl_layers),
    max_ul_layers: num(d.max_ul_layers),
    max_modulation_dl: d.max_modulation_dl,
    max_modulation_ul: d.max_modulation_ul,
    ue_category: blank(d.ue_category),
    duplex_mode: d.duplex_mode,
    supported_bands: d.supported_bands.length > 0 ? d.supported_bands : null,
  }
}

export function DUTProfileManager() {
  const queryClient = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)
  // null = 新建; 非空 = 编辑该 id
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT)

  const profilesQuery = useQuery({
    queryKey: DUT_PROFILES_KEY,
    queryFn: () => fetchDUTProfiles(false),
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: DUT_PROFILES_KEY })

  const createMutation = useMutation({
    mutationFn: (payload: DUTProfileCreatePayload) => createDUTProfile(payload),
    onSuccess: (p) => {
      notifications.show({ title: 'DUT 声明已创建', message: p.name, color: 'green' })
      setModalOpen(false)
      invalidate()
    },
    onError: (e: unknown) => notifyError('创建失败', e),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: DUTProfileCreatePayload }) =>
      updateDUTProfile(id, payload),
    onSuccess: (p) => {
      notifications.show({ title: 'DUT 声明已更新', message: p.name, color: 'green' })
      setModalOpen(false)
      invalidate()
    },
    onError: (e: unknown) => notifyError('更新失败', e),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteDUTProfile(id, false),
    onSuccess: () => {
      notifications.show({ title: 'DUT 声明已删除', message: '已置为非活动', color: 'gray' })
      invalidate()
    },
    onError: (e: unknown) => notifyError('删除失败', e),
  })

  const openCreate = () => {
    setEditingId(null)
    setDraft(EMPTY_DRAFT)
    setModalOpen(true)
  }

  const openEdit = (p: DUTProfile) => {
    setEditingId(p.id)
    setDraft(profileToDraft(p))
    setModalOpen(true)
  }

  const confirmDelete = (p: DUTProfile) =>
    modals.openConfirmModal({
      title: '删除 DUT 声明',
      children: (
        <Text size="sm">
          确认删除 DUT 声明「{p.name}」? 软删除 (置为非活动), 引用它的历史测试例不受影响。
        </Text>
      ),
      labels: { confirm: '删除', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteMutation.mutate(p.id),
    })

  const submit = () => {
    const payload = draftToPayload(draft)
    if (payload.name === '') {
      notifications.show({ title: '名称必填', message: 'DUT 声明名称不能为空', color: 'red' })
      return
    }
    if (editingId) updateMutation.mutate({ id: editingId, payload })
    else createMutation.mutate(payload)
  }

  const profiles = profilesQuery.data ?? []
  const saving = createMutation.isPending || updateMutation.isPending
  const draftValid = useMemo(() => draft.name.trim() !== '', [draft.name])

  return (
    <Stack gap="md">
      <Group justify="space-between" align="center">
        <Group gap="xs">
          <IconDeviceMobile size={22} />
          <Title order={3}>DUT 声明能力</Title>
        </Group>
        <Button leftSection={<IconPlus size={16} />} onClick={openCreate}>
          新建 DUT 声明
        </Button>
      </Group>

      <Text size="sm" c="dimmed">
        被测设备 (DUT) 的自声明能力档案 —— 规划期 (attach 前) 维护。测试例配置里选一个 DUT
        声明后, 预检会拿测试请求 (层数/调制) 跟声明能力比, 请求超声明则提前 fail, 不浪费真跑。
      </Text>

      <Paper withBorder pos="relative">
        <LoadingOverlay visible={profilesQuery.isLoading} />
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>名称</Table.Th>
              <Table.Th>厂商 / 型号</Table.Th>
              <Table.Th>DL 层</Table.Th>
              <Table.Th>UL 层</Table.Th>
              <Table.Th>调制 (DL/UL)</Table.Th>
              <Table.Th>双工</Table.Th>
              <Table.Th>频段</Table.Th>
              <Table.Th>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {profiles.length === 0 && !profilesQuery.isLoading ? (
              <Table.Tr>
                <Table.Td colSpan={8}>
                  <Text size="sm" c="dimmed" ta="center" py="md">
                    还没有 DUT 声明 — 点「新建 DUT 声明」添加被测设备能力档案。
                  </Text>
                </Table.Td>
              </Table.Tr>
            ) : (
              profiles.map((p) => (
                <Table.Tr key={p.id}>
                  <Table.Td>
                    <Text fw={500}>{p.name}</Text>
                    {p.ue_category ? (
                      <Text size="xs" c="dimmed">
                        UE Cat {p.ue_category}
                      </Text>
                    ) : null}
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {[p.manufacturer, p.model_name].filter(Boolean).join(' / ') || '—'}
                    </Text>
                  </Table.Td>
                  <Table.Td>{p.max_dl_layers ?? '—'}</Table.Td>
                  <Table.Td>{p.max_ul_layers ?? '—'}</Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {(p.max_modulation_dl ?? '—') + ' / ' + (p.max_modulation_ul ?? '—')}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    {p.duplex_mode ? <Badge variant="light">{p.duplex_mode}</Badge> : '—'}
                  </Table.Td>
                  <Table.Td>
                    {p.supported_bands && p.supported_bands.length > 0 ? (
                      <Group gap={4}>
                        {p.supported_bands.slice(0, 4).map((b) => (
                          <Badge key={b} size="sm" variant="outline" color="gray">
                            {b}
                          </Badge>
                        ))}
                        {p.supported_bands.length > 4 ? (
                          <Text size="xs" c="dimmed">
                            +{p.supported_bands.length - 4}
                          </Text>
                        ) : null}
                      </Group>
                    ) : (
                      '—'
                    )}
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

      <Modal
        opened={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editingId ? '编辑 DUT 声明' : '新建 DUT 声明'}
        size="lg"
      >
        <Stack gap="md">
          <TextInput
            label="名称"
            description="唯一标识, 测试例配置里按此名选 DUT"
            required
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.currentTarget.value })}
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput
              label="厂商"
              value={draft.manufacturer}
              onChange={(e) => setDraft({ ...draft, manufacturer: e.currentTarget.value })}
            />
            <TextInput
              label="型号"
              value={draft.model_name}
              onChange={(e) => setDraft({ ...draft, model_name: e.currentTarget.value })}
            />
          </SimpleGrid>
          <Textarea
            label="描述"
            autosize
            minRows={2}
            value={draft.description}
            onChange={(e) => setDraft({ ...draft, description: e.currentTarget.value })}
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <NumberInput
              label="最大 DL 层数"
              description="下行 MIMO 层上限 (留空=未声明, 跳过该项校验)"
              min={1}
              max={8}
              value={draft.max_dl_layers}
              onChange={(v) =>
                setDraft({ ...draft, max_dl_layers: typeof v === 'number' ? v : '' })
              }
            />
            <NumberInput
              label="最大 UL 层数"
              min={1}
              max={8}
              value={draft.max_ul_layers}
              onChange={(v) =>
                setDraft({ ...draft, max_ul_layers: typeof v === 'number' ? v : '' })
              }
            />
            <Select
              label="最大 DL 调制"
              data={DUT_MODULATION_OPTIONS}
              value={draft.max_modulation_dl}
              onChange={(v) => setDraft({ ...draft, max_modulation_dl: v })}
              clearable
              placeholder="(未声明)"
            />
            <Select
              label="最大 UL 调制"
              data={DUT_MODULATION_OPTIONS}
              value={draft.max_modulation_ul}
              onChange={(v) => setDraft({ ...draft, max_modulation_ul: v })}
              clearable
              placeholder="(未声明)"
            />
            <Select
              label="双工模式"
              data={DUT_DUPLEX_OPTIONS}
              value={draft.duplex_mode}
              onChange={(v) => setDraft({ ...draft, duplex_mode: v })}
              clearable
              placeholder="(未声明)"
            />
            <TextInput
              label="UE Category"
              value={draft.ue_category}
              onChange={(e) => setDraft({ ...draft, ue_category: e.currentTarget.value })}
            />
          </SimpleGrid>
          <TagsInput
            label="支持频段"
            description="用回车分隔, 例如 n78 n79 n41"
            value={draft.supported_bands}
            onChange={(tags) => setDraft({ ...draft, supported_bands: tags })}
          />
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={() => setModalOpen(false)}>
              取消
            </Button>
            <Button onClick={submit} loading={saving} disabled={!draftValid}>
              {editingId ? '保存' : '创建'}
            </Button>
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

export default DUTProfileManager
