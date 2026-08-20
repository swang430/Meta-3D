/**
 * P2: RF Chain preview + path-loss calibration launcher.
 *
 * Operators picked a LabProfile + operating mode, the panel resolves the
 * SwitchTopology and renders each active chain as a horizontal flow:
 *
 *   [B1.1 (CE)] → [Cable 0.5 dB] → [Probe 12 V]
 *
 * Then they can hit Start to kick off path-loss calibration, knowing
 * exactly which chains the backend will iterate over (same resolver).
 *
 * Also surfaces resolver warnings (missing topology, mode not declared,
 * etc.) so failures are visible *before* the backend job starts.
 */
import { useEffect, useState } from 'react'
import { useOperationalLab } from '../../OperationalLab'
import {
  Stack,
  Paper,
  Title,
  Text,
  Select,
  TextInput,
  NumberInput,
  Button,
  Group,
  Alert,
  Badge,
  Code,
  Loader,
  Center,
  Divider,
  ScrollArea,
} from '@mantine/core'
import {
  IconAlertTriangle,
  IconAlertCircle,
  IconArrowRight,
  IconCheck,
  IconLink,
  IconPlayerPlay,
  IconRefresh,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'

import {
  fetchRFChains,
  startPathLossCalibrationForLab,
  type RFChainResolutionResponse,
} from '../../../api/labProfileService'
import { logFrontendEvent } from '../../../observability/frontendLogger'

const OPERATING_MODE_OPTIONS = [
  { value: 'mimo_ota', label: 'MIMO OTA (5G NR)' },
  { value: 'siso_trp', label: 'SISO TRP' },
  { value: 'tis', label: 'TIS' },
  { value: 'passive', label: 'Passive' },
]

export function RFChainDiagramPanel() {
  // P1-57：LabProfile 由全局上下文提供，本面板只读 ——
  // 原来这里「拉到列表就自动选第一项」正是禁掉的猜测行为。
  const { selectedLabProfileId, selectedLabProfile, chamberName, loading: labsLoading, error: labsError } = useOperationalLab()
  const selectedLabId = selectedLabProfileId ?? ''
  // 「重新解析」用单调计数器触发（不是清空再设回 —— latch 布尔/状态抖动那套
  // 在全局上下文下也没有 setter 可用）。
  const [resolveAttempt, setResolveAttempt] = useState(0)
  const [operatingMode, setOperatingMode] = useState<string>('mimo_ota')

  const [resolution, setResolution] = useState<RFChainResolutionResponse | null>(null)
  const [resolving, setResolving] = useState(false)
  const [resolveError, setResolveError] = useState<string | null>(null)

  // Path-loss launch form
  const [frequencyMhz, setFrequencyMhz] = useState<number>(3500)
  const [sghModel, setSghModel] = useState<string>('ETS-Lindgren 3164-06')
  const [sghGainDbi, setSghGainDbi] = useState<number>(10)
  const [calibratedBy, setCalibratedBy] = useState<string>('')
  const [starting, setStarting] = useState(false)

  // Auto-resolve whenever (lab, mode) changes — feedback should be live.
  useEffect(() => {
    if (!selectedLabId) {
      setResolution(null)
      return
    }
    setResolving(true)
    setResolveError(null)
    fetchRFChains(selectedLabId, operatingMode)
      .then(setResolution)
      .catch((e: unknown) => {
        const detail =
          (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          (e as Error)?.message
        setResolveError(detail || '链路解析失败')
        setResolution(null)
      })
      .finally(() => setResolving(false))
  }, [selectedLabId, operatingMode, resolveAttempt])

  const handleStart = async () => {
    if (!selectedLabId || !calibratedBy) return
    setStarting(true)
    try {
      const resp = await startPathLossCalibrationForLab({
        lab_profile_id: selectedLabId,
        operating_mode: operatingMode,
        frequency_mhz: frequencyMhz,
        sgh_model: sghModel,
        sgh_gain_dbi: sghGainDbi,
        calibrated_by: calibratedBy,
        use_mock: true,
      })
      notifications.show({
        title: '路损校准已启动',
        message: resp.message || `任务 ${resp.calibration_job_id}`,
        color: 'green',
        icon: <IconCheck size={18} />,
      })
      if (resp.warnings?.length) {
        // 校准成功但有清理告警 (如 tone 停不掉 / CE 留直通) — 证书带隐患入库,
        // 必须让操作员当场看到
        notifications.show({
          title: `校准告警 (${resp.warnings.length} 条)`,
          message: resp.warnings.join('\n'),
          color: 'yellow',
          icon: <IconAlertCircle size={18} />,
          autoClose: false,
        })
      }
      logFrontendEvent({
        action: 'path_loss_calibration.started',
        component: 'RFChainDiagramPanel',
        message: `lab=${selectedLabId} mode=${operatingMode} freq=${frequencyMhz}MHz chains=${resolution?.chains.length ?? 0}`,
      })
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string | object } } })?.response?.data?.detail ||
        (e as Error)?.message ||
        '启动失败'
      notifications.show({
        title: '路损校准启动失败',
        message: typeof detail === 'string' ? detail : JSON.stringify(detail),
        color: 'red',
        icon: <IconAlertCircle size={18} />,
      })
      logFrontendEvent({
        level: 'ERROR',
        action: 'path_loss_calibration.start_failed',
        component: 'RFChainDiagramPanel',
        error: typeof detail === 'string' ? detail : JSON.stringify(detail),
      })
    } finally {
      setStarting(false)
    }
  }

  const canStart =
    !!selectedLabId &&
    !!calibratedBy &&
    frequencyMhz > 0 &&
    !!resolution?.success &&
    !starting

  return (
    <Stack gap="md">
      <Paper p="md" withBorder>
        <Stack gap="xs">
          <Title order={4}>RF 链路示意 + 路损校准启动</Title>
          <Text size="sm" c="dimmed">
            选择 LabProfile 与操作模式, 解析当前 SwitchTopology 激活的 RF 通路.
            启动校准前先肉眼确认每条链 (CE 端口 → 电缆 → 探头) 与实际接线一致.
          </Text>
        </Stack>
      </Paper>

      <Paper p="md" withBorder>
        <Stack gap="md">
          <Group grow align="flex-end">
            {labsLoading ? (
              <Group gap="xs">
                <Loader size="xs" />
                <Text size="sm" c="dimmed">加载 LabProfile...</Text>
              </Group>
            ) : (
              <TextInput
                label="LabProfile"
                description="来自顶部全局选择器"
                value={selectedLabProfile
                  ? (chamberName ? `${selectedLabProfile.name} — ${chamberName}` : selectedLabProfile.name)
                  : '未选择'}
                readOnly
              />
            )}
            <Select
              label="操作模式"
              description="对应 SwitchTopology.operating_modes[*].id"
              data={OPERATING_MODE_OPTIONS}
              value={operatingMode}
              onChange={(v) => v && setOperatingMode(v)}
              required
              allowDeselect={false}
            />
          </Group>

          {labsError && (
            <Alert color="red" icon={<IconAlertCircle size={18} />}>
              {labsError}
            </Alert>
          )}
        </Stack>
      </Paper>

      {/* Resolution preview */}
      <Paper p="md" withBorder>
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            <IconLink size={18} />
            <Title order={5}>解析的 RF 通路</Title>
            {resolution && (
              <Badge color={resolution.success ? 'green' : 'orange'} variant="light">
                {resolution.chains.length} 条
              </Badge>
            )}
            {resolution?.topology_name && (
              <Text size="xs" c="dimmed">
                topology: {resolution.topology_name}
              </Text>
            )}
          </Group>
          {selectedLabId && (
            <Button
              variant="subtle"
              size="xs"
              leftSection={<IconRefresh size={14} />}
              onClick={() => setResolveAttempt((n) => n + 1)}
              disabled={resolving}
            >
              重新解析
            </Button>
          )}
        </Group>

        {resolving ? (
          <Center py="xl">
            <Loader size="md" />
          </Center>
        ) : resolveError ? (
          <Alert color="red" icon={<IconAlertCircle size={18} />} title="链路解析失败">
            {resolveError}
          </Alert>
        ) : !resolution ? (
          <Text c="dimmed" size="sm">选择 LabProfile 后自动解析。</Text>
        ) : !resolution.success ? (
          <Alert color="orange" icon={<IconAlertTriangle size={18} />} title="未找到激活通路">
            <Stack gap="xs">
              <Text size="sm">
                在 LabProfile <Code>{resolution.lab_name}</Code> 的 chamber 上找不到
                operating_mode <Code>{operatingMode}</Code> 的有效 SwitchTopology。
                先在「拓扑编辑器」中绑定暗室 + 设置 active_connections, 再回到这里启动校准。
              </Text>
              {resolution.warnings.length > 0 && (
                <Stack gap={2}>
                  {resolution.warnings.map((w, i) => (
                    <Text key={i} size="xs" c="dimmed">• {w}</Text>
                  ))}
                </Stack>
              )}
            </Stack>
          </Alert>
        ) : (
          <ScrollArea h={Math.min(420, 60 + resolution.chains.length * 36)}>
            <Stack gap={6}>
              {resolution.chains.map((c) => (
                <Paper
                  key={c.chain_id}
                  withBorder
                  p="xs"
                  radius="sm"
                  style={{ backgroundColor: 'var(--mantine-color-gray-0)' }}
                >
                  <Group gap="xs" wrap="nowrap">
                    <Badge color="blue" variant="light" size="sm">CE</Badge>
                    <Code>{c.ce_port}</Code>
                    <IconArrowRight size={14} color="var(--mantine-color-gray-6)" />
                    <Badge color="gray" variant="light" size="sm">
                      cable {c.cable_loss_db.toFixed(2)} dB
                    </Badge>
                    <IconArrowRight size={14} color="var(--mantine-color-gray-6)" />
                    <Badge
                      color={c.polarization.toUpperCase() === 'V' ? 'cyan' : 'pink'}
                      variant="filled"
                      size="sm"
                    >
                      Probe {c.probe_id} {c.polarization}
                    </Badge>
                    <Text size="xs" c="dimmed" ml="auto" style={{ wordBreak: 'break-all' }}>
                      chain={c.chain_id.slice(0, 8)}…
                    </Text>
                  </Group>
                </Paper>
              ))}
              {resolution.warnings.length > 0 && (
                <Alert color="yellow" variant="light" mt="xs" icon={<IconAlertTriangle size={16} />}>
                  <Stack gap={2}>
                    {resolution.warnings.map((w, i) => (
                      <Text key={i} size="xs">{w}</Text>
                    ))}
                  </Stack>
                </Alert>
              )}
            </Stack>
          </ScrollArea>
        )}
      </Paper>

      {/* Launch path-loss form */}
      <Paper p="md" withBorder>
        <Stack gap="md">
          <Title order={5}>启动 Path-Loss 校准</Title>
          <Text size="sm" c="dimmed">
            校准会按上方解析的每一条链 (probe + polarization) 单独测量 SGH→探头空间路损,
            加上该连接的电缆损耗写入证书的 path_loss_db_by_rf_chain 字段; 后续 measure
            阶段按 azimuth 选中的探头反查使用。
          </Text>
          <Divider />
          <Group grow>
            <NumberInput
              label="频率 (MHz)"
              value={frequencyMhz}
              onChange={(v) => setFrequencyMhz(Number(v))}
              min={100}
              max={100000}
              required
            />
            <TextInput
              label="SGH 型号"
              value={sghModel}
              onChange={(e) => setSghModel(e.currentTarget.value)}
              required
            />
            <NumberInput
              label="SGH 增益 (dBi)"
              value={sghGainDbi}
              onChange={(v) => setSghGainDbi(Number(v))}
              decimalScale={2}
              step={0.1}
              required
            />
          </Group>
          <TextInput
            label="校准人员"
            placeholder="工号 / 姓名"
            value={calibratedBy}
            onChange={(e) => setCalibratedBy(e.currentTarget.value)}
            required
          />
          <Group justify="flex-end">
            <Button
              leftSection={<IconPlayerPlay size={16} />}
              onClick={handleStart}
              disabled={!canStart}
              loading={starting}
            >
              启动校准 ({resolution?.chains.length ?? 0} 条链)
            </Button>
          </Group>
        </Stack>
      </Paper>
    </Stack>
  )
}
