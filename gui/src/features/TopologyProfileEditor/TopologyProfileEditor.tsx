/**
 * P2-1 Phase 2.2 — UXM Topology Profile editor modal.
 *
 * Distinct from the existing `TopologyEditor` component (RF switch
 * wiring editor under `features/TopologyEditor/`) — namespace
 * collision avoided by the `Profile` suffix. This editor manages
 * `UxmTestProfile` rows in `instrument_topology_profiles` (the
 * Phase 2.1 DB-backed catalog) — cell/MIMO/power/MAC throughput
 * knobs for the UXM Test App, NOT switch wiring.
 *
 * Three operating modes derived from props:
 * - `mode='create'` — empty form, POST on save
 * - `mode='edit'` (operator-owned profile) — pre-filled, PUT on save
 * - `mode='edit'` + `initialData.is_system_preset === true` — pre-
 *   filled but all inputs disabled with a banner directing the
 *   operator to duplicate first (mirrors backend's 409 on PUT to
 *   system preset; we surface the constraint up-front)
 */

import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Group,
  Modal,
  NumberInput,
  Paper,
  Select,
  Stack,
  Switch,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  createTopologyProfile,
  updateTopologyProfile,
  type TopologyProfileDetail,
  type CreateTopologyProfilePayload,
  type UpdateTopologyProfilePayload,
} from '../../api/service'

interface TopologyProfileEditorProps {
  opened: boolean
  // 'create' = blank form, will POST on save.
  // 'edit'   = pre-filled form, will PUT on save (or read-only banner
  //            if initialData.is_system_preset).
  mode: 'create' | 'edit'
  // Required for both create (defaults seed) and edit (initial state).
  // In create mode, only `compatible_test_apps` default is meaningful.
  initialData: TopologyProfileDetail | null
  categoryKey: string
  onClose: () => void
  onSaved: (saved: TopologyProfileDetail) => void
}

// Defaults mirror the UxmTestProfile dataclass — keep in sync if the
// dataclass surface ever changes. The reason we duplicate defaults
// rather than letting the backend fill them in: NumberInput etc need
// a concrete initial value before the operator interacts.
const BLANK: Omit<TopologyProfileDetail, 'profile_id' | 'is_system_preset'> = {
  name: '',
  description: '',
  category: 'mimo',
  band: 'N78',
  frequency_mhz: 3500,
  bandwidth_mhz: 100,
  scs_khz: 30,
  duplex: 'TDD',
  arfcn: null,
  mimo_layers: 2,
  mimo_port_preset: '2x2',
  dl_power_dbm: -50,
  ssb_power_dbm: -50,
  modulation: '256QAM',
  target_mcs: 28,
  sched_algo: 'FULLBUFFER',
  enable_amc: false,
  tdd_pattern: 'DDDSU',
  tdd_period: '5MS',
  harq_max_trans: 4,
  harq_processes: 16,
  csi_rs_ports: null,
  stat_count: 5000,
  cell_id: 'CELL0',
  state_file: null,
  compatible_test_apps: ['5G_NR_Test'],
  notes: '',
  created_by: null,
}

const CATEGORY_OPTIONS = [
  { value: 'siso', label: 'SISO' },
  { value: 'mimo', label: 'MIMO' },
  { value: 'calibration', label: 'Calibration' },
  { value: 'general', label: 'General' },
]

const DUPLEX_OPTIONS = [
  { value: 'TDD', label: 'TDD' },
  { value: 'FDD', label: 'FDD' },
]

const MIMO_PORT_PRESETS = [
  { value: 'siso', label: 'SISO (1 port)' },
  { value: '2x2', label: '2x2 (RF1+RF2)' },
  { value: '2x2_alt', label: '2x2 alt (RF3+RF4)' },
  { value: '4x4', label: '4x4 (RF1-RF4)' },
]

const MODULATION_OPTIONS = [
  { value: 'QPSK', label: 'QPSK' },
  { value: '16QAM', label: '16QAM' },
  { value: '64QAM', label: '64QAM' },
  { value: '256QAM', label: '256QAM' },
]

// Known Test Apps the operator can declare compat with. Free-text
// fallback (TextInput) so future Test Apps can be referenced without
// a code change — but the curated list covers today's two profiles
// (matching app/hal/uxm_command_profiles.py).
const KNOWN_TEST_APPS = ['5G_NR_Test', 'LTE_NR_IRAT']

export function TopologyProfileEditor({
  opened,
  mode,
  initialData,
  categoryKey,
  onClose,
  onSaved,
}: TopologyProfileEditorProps) {
  const queryClient = useQueryClient()
  // Form state — one big object so reset on initialData change is a
  // single setForm call rather than 25 setX calls.
  const [form, setForm] = useState(BLANK)
  // Track compat list as comma-separated string in the input field,
  // converted back to array on save. Keeps the UX simple (no MultiSelect
  // needed for a 2-3 item list).
  const [compatText, setCompatText] = useState('5G_NR_Test')
  const [formError, setFormError] = useState<string | null>(null)

  const isPreset = initialData?.is_system_preset === true
  const readOnly = mode === 'edit' && isPreset

  useEffect(() => {
    if (!opened) return
    if (mode === 'edit' && initialData) {
      // strip the immutable / DB-managed keys before spreading
      const {
        profile_id: _pid,
        is_system_preset: _sp,
        ...editable
      } = initialData
      void _pid
      void _sp
      setForm({ ...BLANK, ...editable })
      setCompatText((initialData.compatible_test_apps ?? []).join(', '))
    } else {
      setForm(BLANK)
      setCompatText('5G_NR_Test')
    }
    setFormError(null)
  }, [opened, mode, initialData])

  const createMutation = useMutation({
    mutationFn: (payload: CreateTopologyProfilePayload) =>
      createTopologyProfile(categoryKey, payload),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({
        queryKey: ['instruments', 'topologyProfiles', categoryKey],
      })
      notifications.show({
        title: '已创建拓扑 Profile',
        message: `${saved.name} (${saved.profile_id})`,
        color: 'teal',
      })
      onSaved(saved)
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? '创建失败'
      setFormError(String(detail))
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({
      profileId,
      payload,
    }: {
      profileId: string
      payload: UpdateTopologyProfilePayload
    }) => updateTopologyProfile(categoryKey, profileId, payload),
    onSuccess: (saved) => {
      queryClient.invalidateQueries({
        queryKey: ['instruments', 'topologyProfiles', categoryKey],
      })
      notifications.show({
        title: '已更新',
        message: `${saved.name}`,
        color: 'teal',
      })
      onSaved(saved)
    },
    onError: (err: unknown) => {
      // 409 on system preset surfaces ``refused: true``; everything
      // else is a generic detail string.
      const data = (err as {
        response?: { data?: { refused?: boolean; reason?: string; detail?: string } }
      })?.response?.data
      if (data?.refused) {
        setFormError(`无法保存：${data.detail ?? data.reason}`)
      } else {
        setFormError(String(data?.detail ?? '保存失败'))
      }
    },
  })

  const handleSave = () => {
    if (!form.name.trim()) {
      setFormError('请填写名称')
      return
    }
    setFormError(null)

    const compat = compatText
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

    // Build the field payload. Skip null on non-nullable per backend's
    // Phase 2.1 Codex P2 fix — but here we don't even need to, since
    // we never send `band` etc as null from this form (NumberInput
    // doesn't produce null; TextInput trims to empty string which the
    // backend rejects for `band` separately if it were sent).
    const payload = {
      name: form.name.trim(),
      description: form.description?.trim() || null,
      category: form.category,
      band: form.band,
      frequency_mhz: form.frequency_mhz,
      bandwidth_mhz: form.bandwidth_mhz,
      scs_khz: form.scs_khz,
      duplex: form.duplex,
      arfcn: form.arfcn,
      mimo_layers: form.mimo_layers,
      mimo_port_preset: form.mimo_port_preset,
      dl_power_dbm: form.dl_power_dbm,
      ssb_power_dbm: form.ssb_power_dbm,
      modulation: form.modulation,
      target_mcs: form.target_mcs,
      sched_algo: form.sched_algo,
      enable_amc: form.enable_amc,
      tdd_pattern: form.tdd_pattern,
      tdd_period: form.tdd_period,
      harq_max_trans: form.harq_max_trans,
      harq_processes: form.harq_processes,
      csi_rs_ports: form.csi_rs_ports,
      stat_count: form.stat_count,
      cell_id: form.cell_id,
      state_file: form.state_file?.trim() || null,
      compatible_test_apps: compat,
      notes: form.notes?.trim() || null,
    }

    if (mode === 'create') {
      createMutation.mutate(payload)
    } else if (initialData) {
      updateMutation.mutate({
        profileId: initialData.profile_id,
        payload,
      })
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        mode === 'create'
          ? '新建拓扑 Profile'
          : isPreset
            ? `查看系统预设：${initialData?.name}（只读）`
            : `编辑拓扑 Profile：${initialData?.name}`
      }
      size="xl"
      closeOnClickOutside={false}
    >
      <Stack gap="md">
        {readOnly ? (
          <Alert color="yellow" title="系统预设不可编辑">
            <Text size="sm">
              系统预设（{initialData?.profile_id}）是只读的。要修改，请先在
              卡片上 "复制为副本"，然后编辑副本。
            </Text>
          </Alert>
        ) : null}

        {/* ============ 标识 ============ */}
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="sm">
            标识
          </Text>
          <Stack gap="sm">
            <TextInput
              label="名称"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              disabled={readOnly}
            />
            <Textarea
              label="描述"
              autosize
              minRows={2}
              value={form.description ?? ''}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              disabled={readOnly}
            />
            <Select
              label="分类"
              data={CATEGORY_OPTIONS}
              value={form.category}
              onChange={(v) => v && setForm({ ...form, category: v })}
              disabled={readOnly}
              allowDeselect={false}
            />
            <TextInput
              label="兼容 Test App"
              description={`逗号分隔；已知：${KNOWN_TEST_APPS.join(', ')}。留空 = 任意 Test App。`}
              value={compatText}
              onChange={(e) => setCompatText(e.target.value)}
              disabled={readOnly}
            />
          </Stack>
        </Paper>

        {/* ============ NR 小区 ============ */}
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="sm">
            NR 小区参数
          </Text>
          <Group grow>
            <TextInput
              label="频段 (band)"
              value={form.band}
              onChange={(e) => setForm({ ...form, band: e.target.value })}
              disabled={readOnly}
            />
            <NumberInput
              label="频率 (MHz)"
              value={form.frequency_mhz}
              onChange={(v) =>
                setForm({
                  ...form,
                  frequency_mhz: typeof v === 'number' ? v : 0,
                })
              }
              decimalScale={2}
              disabled={readOnly}
            />
          </Group>
          <Group grow mt="sm">
            <NumberInput
              label="带宽 (MHz)"
              value={form.bandwidth_mhz}
              onChange={(v) =>
                setForm({
                  ...form,
                  bandwidth_mhz: typeof v === 'number' ? v : 0,
                })
              }
              decimalScale={1}
              disabled={readOnly}
            />
            <NumberInput
              label="SCS (kHz)"
              value={form.scs_khz}
              onChange={(v) =>
                setForm({ ...form, scs_khz: typeof v === 'number' ? v : 30 })
              }
              disabled={readOnly}
            />
          </Group>
          <Group grow mt="sm">
            <Select
              label="双工模式"
              data={DUPLEX_OPTIONS}
              value={form.duplex}
              onChange={(v) => v && setForm({ ...form, duplex: v })}
              disabled={readOnly}
              allowDeselect={false}
            />
            <NumberInput
              label="ARFCN（可选）"
              description="留空 = 由驱动从频率推断"
              value={form.arfcn ?? undefined}
              onChange={(v) =>
                setForm({
                  ...form,
                  arfcn: typeof v === 'number' ? v : null,
                })
              }
              disabled={readOnly}
            />
          </Group>
          <TextInput
            label="主小区 (cell_id)"
            description="5G_NR_Test 用 CELL0；LTE_NR_IRAT 用 CELL1"
            value={form.cell_id}
            onChange={(e) => setForm({ ...form, cell_id: e.target.value })}
            disabled={readOnly}
            mt="sm"
          />
        </Paper>

        {/* ============ MIMO ============ */}
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="sm">
            MIMO
          </Text>
          <Group grow>
            <NumberInput
              label="MIMO 层数"
              value={form.mimo_layers}
              onChange={(v) =>
                setForm({ ...form, mimo_layers: typeof v === 'number' ? v : 1 })
              }
              min={1}
              max={4}
              disabled={readOnly}
            />
            <Select
              label="端口预设"
              data={MIMO_PORT_PRESETS}
              value={form.mimo_port_preset}
              onChange={(v) => v && setForm({ ...form, mimo_port_preset: v })}
              disabled={readOnly}
              allowDeselect={false}
            />
          </Group>
          <NumberInput
            label="CSI-RS 端口数（可选）"
            description="2L → 4 ports, 4L → 8 ports；留空 = 由驱动推断"
            value={form.csi_rs_ports ?? undefined}
            onChange={(v) =>
              setForm({
                ...form,
                csi_rs_ports: typeof v === 'number' ? v : null,
              })
            }
            disabled={readOnly}
            mt="sm"
          />
        </Paper>

        {/* ============ 功率 ============ */}
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="sm">
            功率
          </Text>
          <Group grow>
            <NumberInput
              label="DL Power (dBm)"
              value={form.dl_power_dbm}
              onChange={(v) =>
                setForm({
                  ...form,
                  dl_power_dbm: typeof v === 'number' ? v : -50,
                })
              }
              decimalScale={1}
              disabled={readOnly}
            />
            <NumberInput
              label="SSB Power (dBm)"
              value={form.ssb_power_dbm}
              onChange={(v) =>
                setForm({
                  ...form,
                  ssb_power_dbm: typeof v === 'number' ? v : -50,
                })
              }
              decimalScale={1}
              disabled={readOnly}
            />
          </Group>
        </Paper>

        {/* ============ FRC / 调制 ============ */}
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="sm">
            FRC / 调制
          </Text>
          <Group grow>
            <Select
              label="调制方式"
              data={MODULATION_OPTIONS}
              value={form.modulation}
              onChange={(v) => v && setForm({ ...form, modulation: v })}
              disabled={readOnly}
              allowDeselect={false}
            />
            <NumberInput
              label="Target MCS"
              description="3GPP OTA 最高 MCS=28"
              value={form.target_mcs}
              onChange={(v) =>
                setForm({
                  ...form,
                  target_mcs: typeof v === 'number' ? v : 0,
                })
              }
              min={0}
              max={31}
              disabled={readOnly}
            />
          </Group>
        </Paper>

        {/* ============ MAC 吞吐量 (3GPP TR 37.977) ============ */}
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="sm">
            MAC 吞吐量参数 (3GPP TR 37.977)
          </Text>
          <Group grow>
            <TextInput
              label="调度算法"
              description="FULLBUFFER = 持续占满时隙"
              value={form.sched_algo}
              onChange={(e) => setForm({ ...form, sched_algo: e.target.value })}
              disabled={readOnly}
            />
            <Switch
              label="启用 AMC"
              description="关闭 = 固定 MCS（3GPP 要求）"
              checked={form.enable_amc}
              onChange={(e) =>
                setForm({ ...form, enable_amc: e.currentTarget.checked })
              }
              disabled={readOnly}
              mt="lg"
            />
          </Group>
          <Group grow mt="sm">
            <TextInput
              label="TDD 时隙格式"
              description="DDDSU 在 5ms 周期最大化下行"
              value={form.tdd_pattern}
              onChange={(e) =>
                setForm({ ...form, tdd_pattern: e.target.value })
              }
              disabled={readOnly}
            />
            <TextInput
              label="TDD 周期"
              value={form.tdd_period}
              onChange={(e) => setForm({ ...form, tdd_period: e.target.value })}
              disabled={readOnly}
            />
          </Group>
          <Group grow mt="sm">
            <NumberInput
              label="HARQ 最大重传"
              value={form.harq_max_trans}
              onChange={(v) =>
                setForm({
                  ...form,
                  harq_max_trans: typeof v === 'number' ? v : 4,
                })
              }
              min={1}
              max={8}
              disabled={readOnly}
            />
            <NumberInput
              label="HARQ 进程数"
              value={form.harq_processes}
              onChange={(v) =>
                setForm({
                  ...form,
                  harq_processes: typeof v === 'number' ? v : 16,
                })
              }
              min={1}
              max={32}
              disabled={readOnly}
            />
          </Group>
          <NumberInput
            label="统计窗口 (子帧)"
            description="3GPP 建议 ≥ 5000（= 5 秒）"
            value={form.stat_count}
            onChange={(v) =>
              setForm({ ...form, stat_count: typeof v === 'number' ? v : 5000 })
            }
            min={100}
            disabled={readOnly}
            mt="sm"
          />
        </Paper>

        {/* ============ 高级 ============ */}
        <Paper p="md" withBorder>
          <Text size="sm" fw={600} mb="sm">
            高级（可选）
          </Text>
          <TextInput
            label="State 文件路径"
            description="UXM 仪器端 .state 文件路径；填了就跳过所有上述参数走 MMEM:LOAD"
            value={form.state_file ?? ''}
            onChange={(e) => setForm({ ...form, state_file: e.target.value })}
            disabled={readOnly}
          />
          <Textarea
            label="备注 / 连线说明"
            autosize
            minRows={2}
            value={form.notes ?? ''}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            disabled={readOnly}
            mt="sm"
          />
        </Paper>

        {formError ? (
          <Alert color="red" title="保存失败">
            {formError}
          </Alert>
        ) : null}

        <Group justify="right">
          <Button variant="default" onClick={onClose} disabled={isSaving}>
            {readOnly ? '关闭' : '取消'}
          </Button>
          {readOnly ? null : (
            <Button onClick={handleSave} loading={isSaving}>
              {mode === 'create' ? '创建' : '保存'}
            </Button>
          )}
        </Group>
      </Stack>
    </Modal>
  )
}
