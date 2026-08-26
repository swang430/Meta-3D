/**
 * Standard Channel Definition (SCD) 管理卡片 — P2-12 slice 3 (A)。
 *
 * 挂在信道仿真器 (channelEmulator) 设备抽屉, ChannelModelsCard 下方。让 operator:
 *  - 列出该 F64 绑定的标准信道定义 (SCD)
 *  - 新建 SCD (规范字段 → 后端算标准名, 单一真值)
 *  - 关联实际 .smu 文件 (路径 b/c) → 更新 available_channel_models projection
 *  - 删除 SCD
 *
 * associate / delete 已关联 SCD 会改 connection_params['available_channel_models'],
 * 故成功后 invalidate channel-models 两个 queryKey (ChannelModelsCard 只读卡 +
 * MIMOOTAConfigForm 的 emulation_file 下拉 #120) 让它们刷新。
 *
 * 风格仿 ChannelModelsCard (App.tsx): useQuery + useMutation + response.data.detail
 * 错误内联 + Alert statusBanner。手写 service (standardChannelService.ts)。
 */
import { useState } from 'react'
import {
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  associateStandardChannelFile,
  createStandardChannel,
  deleteStandardChannel,
  fetchStandardChannels,
  type StandardChannel,
} from '../api/standardChannelService'

function extractDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  return detail ? String(detail) : fallback
}

const SOURCE_META: Record<string, { label: string; color: string }> = {
  declared_only: { label: '未关联', color: 'gray' },
  standard_generated: { label: '标准生成', color: 'green' },
  vendor_associated: { label: '厂商关联', color: 'blue' },
}

const POLARIZATION_OPTIONS = [
  { value: 'DP', label: '双极化 (DP)' },
  { value: 'V', label: '垂直 (V)' },
  { value: 'H', label: '水平 (H)' },
]

const ASSOCIATION_SOURCE_OPTIONS = [
  { value: 'vendor_associated', label: '厂商关联 (路径 c: 已有 .smu, 仅频率 cross-check)' },
  { value: 'standard_generated', label: '标准生成 (路径 a/b: 文件名须 == 标准名)' },
]

const EMPTY_CREATE = {
  radio_technology: 'nr5g' as 'nr5g' | 'lte',
  band: '',
  channel_number: '' as number | '',
  bandwidth_mhz: '' as number | '',
  model: '',
  scenario: '',
  mimo: '',
  polarization: 'DP',
  version: 1 as number | '',
  description: '',
}

export function StandardChannelDefinitionCard({ connectionId }: { connectionId: string }) {
  const queryClient = useQueryClient()
  const scdQueryKey = ['standardChannels', connectionId]

  const { data, isLoading, isError } = useQuery({
    queryKey: scdQueryKey,
    queryFn: () => fetchStandardChannels(connectionId),
    refetchOnWindowFocus: false,
  })
  const scds = data ?? []

  // 关联文件改了 projection → 让两个 channel-models 消费方刷新。
  const invalidateChannelModels = () => {
    queryClient.invalidateQueries({ queryKey: ['instruments', 'channelModels'] })
    queryClient.invalidateQueries({ queryKey: ['channelModels'] })
  }

  // ---- 新建 SCD ----
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState({ ...EMPTY_CREATE })
  const [createError, setCreateError] = useState<string | null>(null)

  const createMutation = useMutation({
    mutationFn: () =>
      createStandardChannel({
        instrument_connection_id: connectionId,
        radio_technology: form.radio_technology,
        channel_kind: form.radio_technology === 'lte' ? 'lte_dl_earfcn' : 'nr_arfcn',
        band: form.band.trim(),
        arfcn: form.radio_technology === 'nr5g' ? Number(form.channel_number) : null,
        lte_dl_earfcn: form.radio_technology === 'lte' ? Number(form.channel_number) : null,
        bandwidth_mhz: Number(form.bandwidth_mhz),
        model: form.model.trim(),
        scenario: form.scenario.trim(),
        mimo: form.mimo.trim(),
        polarization: form.polarization,
        version: form.version === '' ? 1 : Number(form.version),
        description: form.description.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: scdQueryKey })
      setForm({ ...EMPTY_CREATE })
      setCreateError(null)
      setCreateOpen(false)
    },
    onError: (err) => setCreateError(extractDetail(err, '创建失败')),
  })

  const createValid =
    form.band.trim() &&
    form.channel_number !== '' &&
    form.bandwidth_mhz !== '' &&
    form.model.trim() &&
    form.scenario.trim() &&
    form.mimo.trim() &&
    form.polarization

  // ---- 关联文件 ----
  const [associateTarget, setAssociateTarget] = useState<StandardChannel | null>(null)
  const [filePath, setFilePath] = useState('')
  const [associationSource, setAssociationSource] = useState('vendor_associated')
  const [associateError, setAssociateError] = useState<string | null>(null)

  const associateMutation = useMutation({
    mutationFn: () =>
      associateStandardChannelFile(associateTarget!.id, {
        file_path: filePath.trim(),
        association_source: associationSource,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: scdQueryKey })
      invalidateChannelModels()
      setAssociateTarget(null)
      setFilePath('')
      setAssociationSource('vendor_associated')
      setAssociateError(null)
    },
    onError: (err) => setAssociateError(extractDetail(err, '关联失败')),
  })

  // ---- 删除 ----
  const [opError, setOpError] = useState<string | null>(null)
  const deleteMutation = useMutation({
    mutationFn: (scd: StandardChannel) => deleteStandardChannel(scd.id),
    onSuccess: (_void, scd) => {
      queryClient.invalidateQueries({ queryKey: scdQueryKey })
      if (scd.associated_file_path) invalidateChannelModels()
      setOpError(null)
    },
    onError: (err) => setOpError(extractDetail(err, '删除失败')),
  })

  const statusBanner = (() => {
    if (isLoading) return null
    if (isError) return <Alert color="red" variant="light">无法加载标准信道定义 — 请重试或检查后端日志</Alert>
    if (scds.length === 0) {
      return (
        <Alert color="blue" variant="light">
          暂无标准信道定义. 点击「+ 新建」定义一个 (软件掌控命名), 再「关联文件」绑定实际 .smu —
          关联后会出现在上方可用信道模型清单, 供测试编排的 emulation_file 下拉选择.
        </Alert>
      )
    }
    return null
  })()

  return (
    <Card withBorder padding="md" radius="md" shadow="xs" bg="gray.0">
      <Stack gap="sm">
        <Group justify="space-between" align="center">
          <Stack gap={0}>
            <Text fw={600} size="sm">标准信道定义 (SCD)</Text>
            <Text size="xs" c="dimmed">
              软件掌控标准命名; 定义 → 关联 .smu → 投影到可用信道模型清单.
            </Text>
          </Stack>
          <Button
            variant="light"
            size="xs"
            onClick={() => {
              setForm({ ...EMPTY_CREATE })
              setCreateError(null)
              setCreateOpen(true)
            }}
          >
            + 新建
          </Button>
        </Group>

        {/* P2-16 deprecate-legacy: SCD 已统一为 vendor_file ChannelAsset (信道工作台); 消费
            (scd_id) 已收敛到 ChannelAsset。此处仅供存量兼容, 新建/编辑请去信道工作台。 */}
        <Alert color="orange" variant="light" py="xs">
          此为 legacy SCD 编辑器。SCD 已统一为信道工作台的 <b>ChannelAsset（厂商文件 / vendor_file）</b>，
          测试执行的消费也已收敛到 ChannelAsset。新建 / 编辑请去 <b>侧栏「信道工作台」</b>；此处仅供存量兼容。
        </Alert>

        {statusBanner}
        {opError && <Alert color="red" variant="light" onClose={() => setOpError(null)} withCloseButton>{opError}</Alert>}

        {scds.map((scd) => {
          const meta = SOURCE_META[scd.association_source] ?? { label: scd.association_source, color: 'gray' }
          return (
            <Card key={scd.id} withBorder padding="xs" radius="sm">
              <Group justify="space-between" align="flex-start" wrap="nowrap">
                <Stack gap={2} style={{ minWidth: 0 }}>
                  <Group gap="xs">
                    <Code>{scd.standard_name}</Code>
                    <Badge size="xs" color={meta.color} variant="light">{meta.label}</Badge>
                  </Group>
                  <Text size="xs" c="dimmed">
                    {scd.radio_technology === 'lte' ? 'LTE' : 'NR'} · {scd.band} · {scd.channel_kind === 'lte_dl_earfcn' ? `DL EARFCN ${scd.lte_dl_earfcn}` : `NR-ARFCN ${scd.arfcn}`} · BW{scd.bandwidth_mhz} · {scd.model}/{scd.scenario} · {scd.mimo} · {scd.polarization} · v{scd.version}
                  </Text>
                  {scd.associated_file_path && (
                    <Text size="xs" c="dimmed" style={{ wordBreak: 'break-all' }}>📎 {scd.associated_file_path}</Text>
                  )}
                </Stack>
                <Group gap={4} wrap="nowrap">
                  <Button
                    variant="subtle"
                    size="compact-xs"
                    onClick={() => {
                      setAssociateTarget(scd)
                      setFilePath(scd.associated_file_path ?? '')
                      setAssociationSource(scd.association_source === 'standard_generated' ? 'standard_generated' : 'vendor_associated')
                      setAssociateError(null)
                    }}
                  >
                    {scd.associated_file_path ? '重新关联' : '关联文件'}
                  </Button>
                  <Button
                    variant="subtle"
                    size="compact-xs"
                    color="red"
                    loading={deleteMutation.isPending && deleteMutation.variables?.id === scd.id}
                    onClick={() => {
                      if (window.confirm(`删除标准信道 ${scd.standard_name}?`)) deleteMutation.mutate(scd)
                    }}
                  >
                    删除
                  </Button>
                </Group>
              </Group>
            </Card>
          )
        })}
      </Stack>

      {/* 新建 SCD */}
      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="新建标准信道定义" size="md">
        <Stack gap="sm">
          <Text size="xs" c="dimmed">标准名由这些规范字段自动生成 (单一真值, 不手填名字).</Text>
          <Select
            label="无线制式"
            data={[{ value: 'nr5g', label: '5G NR' }, { value: 'lte', label: 'LTE' }]}
            value={form.radio_technology}
            onChange={(v) => setForm({ ...form, radio_technology: v === 'lte' ? 'lte' : 'nr5g', band: '', channel_number: '' })}
            allowDeselect={false}
          />
          <Group grow>
            <TextInput label="频段 Band" placeholder={form.radio_technology === 'lte' ? 'B3' : 'N78'} value={form.band} onChange={(e) => setForm({ ...form, band: e.currentTarget.value })} required />
            <NumberInput label={form.radio_technology === 'lte' ? 'DL EARFCN' : 'NR-ARFCN'} placeholder={form.radio_technology === 'lte' ? '1575' : '640000'} value={form.channel_number} onChange={(v) => setForm({ ...form, channel_number: typeof v === 'number' ? v : '' })} min={0} required />
          </Group>
          <Group grow>
            <NumberInput label="带宽 (MHz)" placeholder="100" value={form.bandwidth_mhz} onChange={(v) => setForm({ ...form, bandwidth_mhz: typeof v === 'number' ? v : '' })} min={1} required />
            <TextInput label="信道模型 Model" placeholder="CDLC" value={form.model} onChange={(e) => setForm({ ...form, model: e.currentTarget.value })} required />
          </Group>
          <Group grow>
            <TextInput label="场景 Scenario" placeholder="UMa" value={form.scenario} onChange={(e) => setForm({ ...form, scenario: e.currentTarget.value })} required />
            <TextInput label="MIMO" placeholder="4x4" value={form.mimo} onChange={(e) => setForm({ ...form, mimo: e.currentTarget.value })} required />
          </Group>
          <Group grow>
            <Select label="极化" data={POLARIZATION_OPTIONS} value={form.polarization} onChange={(v) => setForm({ ...form, polarization: v ?? 'DP' })} allowDeselect={false} />
            <NumberInput label="版本" value={form.version} onChange={(v) => setForm({ ...form, version: typeof v === 'number' ? v : '' })} min={1} />
          </Group>
          <TextInput label="描述 (可选)" value={form.description} onChange={(e) => setForm({ ...form, description: e.currentTarget.value })} />
          {createError && <Alert color="red" variant="light">{createError}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setCreateOpen(false)}>取消</Button>
            <Button loading={createMutation.isPending} disabled={!createValid} onClick={() => createMutation.mutate()}>创建</Button>
          </Group>
        </Stack>
      </Modal>

      {/* 关联文件 */}
      <Modal opened={associateTarget !== null} onClose={() => setAssociateTarget(null)} title="关联 .smu 文件" size="md">
        <Stack gap="sm">
          {associateTarget && (
            <Text size="xs" c="dimmed">为 <Code>{associateTarget.standard_name}</Code> 绑定实际文件. 频率 cross-check 不一致会被后端拒绝.</Text>
          )}
          <TextInput
            label="文件路径 (F64 上的完整路径)"
            placeholder="D:\\Scenario Packs\\...\\..._3600M.smu"
            value={filePath}
            onChange={(e) => setFilePath(e.currentTarget.value)}
            required
          />
          <Select
            label="关联类型"
            data={ASSOCIATION_SOURCE_OPTIONS}
            value={associationSource}
            onChange={(v) => setAssociationSource(v ?? 'vendor_associated')}
            allowDeselect={false}
          />
          {associateError && <Alert color="red" variant="light">{associateError}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setAssociateTarget(null)}>取消</Button>
            <Button loading={associateMutation.isPending} disabled={!filePath.trim()} onClick={() => associateMutation.mutate()}>关联</Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  )
}
