/**
 * SIMProfile (SIM/eSIM 身份+鉴权声明) 管理界面 (P2-13 Phase 3) — 填写/编辑/删除测试卡档案。
 *
 * 平行 DUTProfileManager。operator 规划期登记测试卡池 (IMSI/PLMN/Ki/OPc/算法/卡类型)。
 * TestCase 配置选其中一张 → managed 流程在 MEASURE 受控 attach 后拿 UXM/UE 实测 IMSI
 * 跟声明核对（防插错卡）；legacy/unmanaged 流程仍在 PRECHECK 核对已有 attach 快照。
 *
 * ⚠️ 凭据 ki/opc write-only: 后端响应不回原始值 (只 ki_set/ki_masked)。编辑时 ki/opc 输入框
 * **留空 = 保持原值**, 填新值才改。card_kind=commercial → 禁用 ki/opc (商用卡不存 Ki)。
 */
import { useMemo, useState } from 'react'
import {
  ActionIcon,
  Badge,
  Button,
  Group,
  LoadingOverlay,
  Modal,
  Paper,
  PasswordInput,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import { IconEdit, IconPlus, IconDeviceSim, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  createSIMProfile,
  deleteSIMProfile,
  fetchSIMProfiles,
  SIM_AUTH_ALGORITHMS,
  SIM_CARD_KINDS,
  SIM_FORMS,
  updateSIMProfile,
  type SIMProfile,
  type SIMProfileCreatePayload,
  type SIMProfileUpdatePayload,
} from '../../api/simProfileService'

const SIM_PROFILES_KEY = ['sim-profiles'] as const

interface DraftState {
  name: string
  description: string
  imsi: string
  iccid: string
  mcc: string
  mnc: string
  ki: string
  opc: string
  auth_algorithm: string | null
  card_kind: string | null
  sim_form: string | null
  eid: string
  esim_profile_id: string
}

const EMPTY_DRAFT: DraftState = {
  name: '', description: '', imsi: '', iccid: '', mcc: '', mnc: '',
  ki: '', opc: '', auth_algorithm: null, card_kind: null, sim_form: null,
  eid: '', esim_profile_id: '',
}

function profileToDraft(p: SIMProfile): DraftState {
  return {
    name: p.name,
    description: p.description ?? '',
    imsi: p.imsi ?? '',
    iccid: p.iccid ?? '',
    mcc: p.mcc ?? '',
    mnc: p.mnc ?? '',
    ki: '',  // write-only: 留空 = 保持原值 (后端不回原始 ki)
    opc: '',
    auth_algorithm: p.auth_algorithm ?? null,
    card_kind: p.card_kind ?? null,
    sim_form: p.sim_form ?? null,
    eid: p.eid ?? '',
    esim_profile_id: p.esim_profile_id ?? '',
  }
}

const blank = (s: string) => (s.trim() === '' ? null : s.trim())

/** 草稿 → create payload (全量, 空串→null)。 */
function draftToCreate(d: DraftState): SIMProfileCreatePayload {
  const isCommercial = d.card_kind === 'commercial'
  return {
    name: d.name.trim(),
    description: blank(d.description),
    imsi: blank(d.imsi),
    iccid: blank(d.iccid),
    mcc: blank(d.mcc),
    mnc: blank(d.mnc),
    ki: isCommercial ? null : blank(d.ki),  // 商用卡不存 ki
    opc: isCommercial ? null : blank(d.opc),
    auth_algorithm: d.auth_algorithm,
    card_kind: d.card_kind,
    sim_form: d.sim_form,
    eid: blank(d.eid),
    esim_profile_id: blank(d.esim_profile_id),
  }
}

/** 草稿 → update payload。ki/opc 留空 = 不传 (保持原值); 商用卡不传 ki。 */
function draftToUpdate(d: DraftState): SIMProfileUpdatePayload {
  const isCommercial = d.card_kind === 'commercial'
  const payload: SIMProfileUpdatePayload = {
    name: d.name.trim(),
    description: blank(d.description),
    imsi: blank(d.imsi),
    iccid: blank(d.iccid),
    mcc: blank(d.mcc),
    mnc: blank(d.mnc),
    auth_algorithm: d.auth_algorithm,
    card_kind: d.card_kind,
    sim_form: d.sim_form,
    eid: blank(d.eid),
    esim_profile_id: blank(d.esim_profile_id),
  }
  // 凭据: 只在填了新值时才送 (留空 = 保持); 商用卡明确清空
  if (isCommercial) {
    payload.ki = null
    payload.opc = null
  } else {
    if (d.ki.trim() !== '') payload.ki = d.ki.trim()
    if (d.opc.trim() !== '') payload.opc = d.opc.trim()
  }
  return payload
}

function notifyError(title: string, e: unknown) {
  const detail =
    (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
    (e as Error)?.message ??
    '未知错误'
  notifications.show({ title, message: String(detail), color: 'red' })
}

export function SIMProfileManager() {
  const queryClient = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingKiSet, setEditingKiSet] = useState(false)
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT)

  const profilesQuery = useQuery({
    queryKey: SIM_PROFILES_KEY,
    queryFn: () => fetchSIMProfiles(false),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: SIM_PROFILES_KEY })

  const createMutation = useMutation({
    mutationFn: (payload: SIMProfileCreatePayload) => createSIMProfile(payload),
    onSuccess: (p) => {
      notifications.show({ title: 'SIM 卡已创建', message: p.name, color: 'green' })
      setModalOpen(false)
      invalidate()
    },
    onError: (e: unknown) => notifyError('创建失败', e),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: SIMProfileUpdatePayload }) =>
      updateSIMProfile(id, payload),
    onSuccess: (p) => {
      notifications.show({ title: 'SIM 卡已更新', message: p.name, color: 'green' })
      setModalOpen(false)
      invalidate()
    },
    onError: (e: unknown) => notifyError('更新失败', e),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteSIMProfile(id, false),
    onSuccess: () => {
      notifications.show({ title: 'SIM 卡已删除', message: '已置为非活动', color: 'gray' })
      invalidate()
    },
    onError: (e: unknown) => notifyError('删除失败', e),
  })

  const openCreate = () => {
    setEditingId(null)
    setEditingKiSet(false)
    setDraft(EMPTY_DRAFT)
    setModalOpen(true)
  }

  const openEdit = (p: SIMProfile) => {
    setEditingId(p.id)
    setEditingKiSet(Boolean(p.ki_set))
    setDraft(profileToDraft(p))
    setModalOpen(true)
  }

  const confirmDelete = (p: SIMProfile) =>
    modals.openConfirmModal({
      title: '删除 SIM 卡',
      children: (
        <Text size="sm">
          确认删除 SIM 卡「{p.name}」? 软删除 (置为非活动), 引用它的历史测试不受影响。
        </Text>
      ),
      labels: { confirm: '删除', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteMutation.mutate(p.id),
    })

  const submit = () => {
    if (draft.name.trim() === '') {
      notifications.show({ title: '名称必填', message: 'SIM 卡名称不能为空', color: 'red' })
      return
    }
    if (editingId) updateMutation.mutate({ id: editingId, payload: draftToUpdate(draft) })
    else createMutation.mutate(draftToCreate(draft))
  }

  const profiles = profilesQuery.data ?? []
  const saving = createMutation.isPending || updateMutation.isPending
  const draftValid = useMemo(() => draft.name.trim() !== '', [draft.name])
  const isCommercial = draft.card_kind === 'commercial'

  return (
    <Stack gap="md">
      <Group justify="space-between" align="center">
        <Group gap="xs">
          <IconDeviceSim size={22} />
          <Title order={3}>SIM 卡管理</Title>
        </Group>
        <Button leftSection={<IconPlus size={16} />} onClick={openCreate}>
          新建 SIM 卡
        </Button>
      </Group>

      <Text size="sm" c="dimmed">
        测试卡池 (SIM/eSIM 身份 + 鉴权凭据) —— 规划期维护。测试例配置里选一张卡后, 预检会拿
        attach 实测 IMSI 跟声明比, 不一致则提示插错卡。凭据 (Ki/OPc) 仅显示后 4 位, 编辑时留空保持原值。
      </Text>

      <Paper withBorder pos="relative">
        <LoadingOverlay visible={profilesQuery.isLoading} />
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>名称</Table.Th>
              <Table.Th>IMSI</Table.Th>
              <Table.Th>PLMN</Table.Th>
              <Table.Th>卡类型</Table.Th>
              <Table.Th>算法</Table.Th>
              <Table.Th>鉴权凭据</Table.Th>
              <Table.Th>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {profiles.length === 0 && !profilesQuery.isLoading ? (
              <Table.Tr>
                <Table.Td colSpan={7}>
                  <Text size="sm" c="dimmed" ta="center" py="md">
                    还没有 SIM 卡 — 点「新建 SIM 卡」添加测试卡档案。
                  </Text>
                </Table.Td>
              </Table.Tr>
            ) : (
              profiles.map((p) => (
                <Table.Tr key={p.id}>
                  <Table.Td>
                    <Text fw={500}>{p.name}</Text>
                    {p.sim_form ? (
                      <Text size="xs" c="dimmed">
                        {p.sim_form}
                      </Text>
                    ) : null}
                  </Table.Td>
                  <Table.Td>{p.imsi ?? '—'}</Table.Td>
                  <Table.Td>{p.mcc && p.mnc ? `${p.mcc}-${p.mnc}` : '—'}</Table.Td>
                  <Table.Td>
                    {p.card_kind ? (
                      <Badge variant="light" color={p.card_kind === 'commercial' ? 'gray' : 'blue'}>
                        {p.card_kind}
                      </Badge>
                    ) : (
                      '—'
                    )}
                  </Table.Td>
                  <Table.Td>{p.auth_algorithm ?? '—'}</Table.Td>
                  <Table.Td>
                    {p.ki_set ? (
                      <Tooltip label={`Ki ${p.ki_masked ?? ''}`}>
                        <Badge variant="outline" color="green">
                          Ki 已设
                        </Badge>
                      </Tooltip>
                    ) : (
                      <Text size="sm" c="dimmed">
                        无
                      </Text>
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
        title={editingId ? '编辑 SIM 卡' : '新建 SIM 卡'}
        size="lg"
      >
        <Stack gap="md">
          <TextInput
            label="名称"
            description="唯一标识, 测试例配置里按此名选卡"
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
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput
              label="IMSI"
              description="15 位; MCC+MNC 须与下方一致"
              value={draft.imsi}
              onChange={(e) => setDraft({ ...draft, imsi: e.currentTarget.value })}
            />
            <TextInput
              label="ICCID (卡序列号)"
              value={draft.iccid}
              onChange={(e) => setDraft({ ...draft, iccid: e.currentTarget.value })}
            />
            <TextInput
              label="MCC"
              description="3 位移动国家码"
              value={draft.mcc}
              onChange={(e) => setDraft({ ...draft, mcc: e.currentTarget.value })}
            />
            <TextInput
              label="MNC"
              description="2-3 位移动网络码"
              value={draft.mnc}
              onChange={(e) => setDraft({ ...draft, mnc: e.currentTarget.value })}
            />
            <Select
              label="卡类型"
              data={SIM_CARD_KINDS}
              value={draft.card_kind}
              onChange={(v) => setDraft({ ...draft, card_kind: v })}
              clearable
              placeholder="(未指定)"
              description="commercial = 商用卡 (不可存 Ki)"
            />
            <Select
              label="SIM 形态"
              data={SIM_FORMS}
              value={draft.sim_form}
              onChange={(v) => setDraft({ ...draft, sim_form: v })}
              clearable
              placeholder="(未指定)"
            />
            <Select
              label="鉴权算法"
              data={SIM_AUTH_ALGORITHMS}
              value={draft.auth_algorithm}
              onChange={(v) => setDraft({ ...draft, auth_algorithm: v })}
              clearable
              placeholder="(未指定)"
            />
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <PasswordInput
              label="Ki (订户密钥)"
              description={
                isCommercial
                  ? '商用卡不可存 Ki'
                  : editingKiSet
                    ? '已设, 留空保持原值; 填新值才改'
                    : '32 位十六进制 (128-bit)'
              }
              value={draft.ki}
              onChange={(e) => setDraft({ ...draft, ki: e.currentTarget.value })}
              disabled={isCommercial}
              placeholder={editingKiSet ? '已设 (留空保持)' : ''}
            />
            <PasswordInput
              label="OPc (运营商变体)"
              description={isCommercial ? '商用卡不可存' : '32 位十六进制'}
              value={draft.opc}
              onChange={(e) => setDraft({ ...draft, opc: e.currentTarget.value })}
              disabled={isCommercial}
            />
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput
              label="EID (eSIM 芯片号)"
              description="eSIM 选填; 同 EID = 同芯片多 profile"
              value={draft.eid}
              onChange={(e) => setDraft({ ...draft, eid: e.currentTarget.value })}
            />
            <TextInput
              label="eSIM profile ID"
              description="eSIM profile 标识 / ICCID (选填)"
              value={draft.esim_profile_id}
              onChange={(e) => setDraft({ ...draft, esim_profile_id: e.currentTarget.value })}
            />
          </SimpleGrid>
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

export default SIMProfileManager
