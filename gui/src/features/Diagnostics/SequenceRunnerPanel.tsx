/**
 * P3 Phase 2: Sequence runner — list + parameterise + execute + show result.
 *
 * Operators picked a sequence (.py file under app/diagnostics/sequences/),
 * pick a LabProfile, fill the metadata-declared params, hit Run. Result
 * panel shows live log + per-step ✓/✗ + summary, plus a Recent Runs feed
 * (last 20 in this kind) so re-running yesterday's diagnostic is one click.
 *
 * Intentionally not a TestPlan replacement — every run lands in
 * diagnostic_runs but never as TestExecution / cert.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Stack,
  Paper,
  Title,
  Text,
  Select,
  TextInput,
  NumberInput,
  Switch,
  Button,
  Group,
  Alert,
  Badge,
  Code,
  Loader,
  Center,
  Divider,
  ScrollArea,
  Table,
  SimpleGrid,
} from '@mantine/core'
import {
  IconAlertTriangle,
  IconAlertCircle,
  IconCheck,
  IconHistory,
  IconPlayerPlay,
  IconRefresh,
  IconTerminal,
  IconX,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'

import {
  fetchLabProfiles,
  type LabProfileSummary,
} from '../../api/labProfileService'
import {
  listDiagnosticSequences,
  runDiagnosticSequence,
  listDiagnosticRuns,
  type DiagnosticSequenceMetadata,
  type SequenceRunResponse,
  type DiagnosticRunSummary,
} from '../../api/diagnosticService'
import { logFrontendEvent } from '../../observability/frontendLogger'

type ParamValue = number | string | boolean

const PARAM_LABEL_OVERRIDES: Record<string, string> = {
  remote_playback_file: 'FS16 .smu 文件',
  verify_remote_file_exists: '加载前校验文件',
  start_playback: '启动 FS16 playback',
  stop_after_s: '自动停止秒数',
  cleanup_on_finish: '结束时清理',
  base_station_mode: '基站模式',
  frequency_mhz: '频率 MHz',
  bandwidth_mhz: '带宽 MHz',
  scs_khz: 'SCS kHz',
  band: '频段',
  mimo_layers: 'MIMO 层数',
  dl_power_dbm: 'DL 功率 dBm',
  attach_timeout_s: 'Attach 超时秒数',
  attach_poll_interval_s: 'Attach 轮询秒数',
  throughput_windows: 'KPI 采样窗口数',
  throughput_window_s: 'KPI 窗口秒数',
}

const PARAM_DESCRIPTION_OVERRIDES: Record<string, string> = {
  remote_playback_file: 'FS16 内已有文件名，或完整 D:\\ 路径',
  verify_remote_file_exists: '先查目录，确认文件可见',
  start_playback: 'load 成功后自动播放',
  stop_after_s: '0 表示不自动停止',
  cleanup_on_finish: '结束时停止并释放状态',
  base_station_mode: '今天用 mock，接真实基站再改 real',
  frequency_mhz: '虚拟基站中心频点',
  bandwidth_mhz: '虚拟小区带宽',
  scs_khz: '子载波间隔',
  band: 'NR 频段',
  mimo_layers: '下行 MIMO 层数',
  dl_power_dbm: 'mock 下行功率',
  attach_timeout_s: '等待终端接入',
  attach_poll_interval_s: '接入状态轮询间隔',
  throughput_windows: 'KPI 采样次数',
  throughput_window_s: '单次 KPI 窗口时长',
}

function getParamLabel(spec: DiagnosticSequenceMetadata['params_schema'][number]) {
  return PARAM_LABEL_OVERRIDES[spec.name] || spec.label || spec.name
}

function getParamDescription(spec: DiagnosticSequenceMetadata['params_schema'][number]) {
  return PARAM_DESCRIPTION_OVERRIDES[spec.name] || ''
}

const KPI_LABELS: Record<string, string> = {
  dl_throughput_mbps: 'DL throughput',
  ul_throughput_mbps: 'UL throughput',
  dl_bler: 'DL BLER',
  ul_bler: 'UL BLER',
  cqi: 'CQI',
  rank_indicator: 'Rank Indicator',
  mcs_dl: 'MCS DL',
  mcs_ul: 'MCS UL',
  rsrp_dbm: 'RSRP',
  sinr_db: 'SINR',
}

const KPI_UNITS: Record<string, string> = {
  dl_throughput_mbps: 'Mbps',
  ul_throughput_mbps: 'Mbps',
  rsrp_dbm: 'dBm',
  sinr_db: 'dB',
}

const KPI_ORDER = [
  'dl_throughput_mbps',
  'ul_throughput_mbps',
  'dl_bler',
  'ul_bler',
  'cqi',
  'rank_indicator',
  'mcs_dl',
  'mcs_ul',
  'rsrp_dbm',
  'sinr_db',
]

type KpiSummaryValue = {
  mean?: number
  min?: number
  max?: number
  std?: number
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function formatKpi(value: unknown, unit?: string): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  const digits = Math.abs(value) < 10 && !Number.isInteger(value) ? 4 : 2
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ''}`
}

function getKpiRows(extra: Record<string, unknown>) {
  const raw = extra.kpi_summary
  if (!isRecord(raw)) return []
  const keys = [
    ...KPI_ORDER.filter((key) => key in raw),
    ...Object.keys(raw).filter((key) => !KPI_ORDER.includes(key)),
  ]
  return keys
    .map((key) => {
      const item = raw[key]
      if (!isRecord(item)) return null
      const value: KpiSummaryValue = {
        mean: typeof item.mean === 'number' ? item.mean : undefined,
        min: typeof item.min === 'number' ? item.min : undefined,
        max: typeof item.max === 'number' ? item.max : undefined,
        std: typeof item.std === 'number' ? item.std : undefined,
      }
      return {
        key,
        label: KPI_LABELS[key] || key,
        unit: KPI_UNITS[key],
        value,
      }
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)
}

function getInstrumentModes(extra: Record<string, unknown>) {
  const raw = extra.instrument_modes
  return isRecord(raw) ? raw : null
}

function getFs16Playback(extra: Record<string, unknown>) {
  const raw = extra.fs16_playback
  return isRecord(raw) ? raw : null
}

function formatExtraValue(value: unknown): string {
  if (value === undefined || value === null || value === '') return '-'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3)
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function getFs16PlaybackRows(playback: Record<string, unknown> | null) {
  if (!playback) return []
  const rows = [
    ['SMU file', playback.remote_playback_file],
    ['FS16 path', playback.remote_playback_path],
    ['File visible', playback.visible],
    ['Precheck', playback.checked],
    ['Checked by', playback.checked_by],
    ['Start playback', playback.start_playback],
    ['Stop after', playback.stop_after_s],
    ['Cleanup on finish', playback.cleanup_on_finish],
    ['Playback left running', playback.playback_left_running],
    ['BS signaling left running', playback.bs_signaling_left_running],
  ] as const
  return rows
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([label, value]) => ({ label, value }))
}

function fs16BooleanColor(label: string, value: boolean): string {
  const normalized = label.toLowerCase()
  if (normalized.includes('left running')) return value ? 'red' : 'green'
  if (normalized.includes('visible')) return value ? 'green' : 'red'
  if (normalized.includes('precheck')) return value ? 'green' : 'gray'
  if (normalized.includes('start') || normalized.includes('cleanup')) {
    return value ? 'blue' : 'gray'
  }
  return value ? 'blue' : 'gray'
}

function getCleanupWarnings(extra: Record<string, unknown>) {
  const raw = extra.cleanup_warnings
  return Array.isArray(raw) ? raw.map(String).filter(Boolean) : []
}

export function SequenceRunnerPanel() {
  const [labs, setLabs] = useState<LabProfileSummary[]>([])
  const [labsLoading, setLabsLoading] = useState(true)
  const [selectedLabId, setSelectedLabId] = useState<string>('')

  const [sequences, setSequences] = useState<DiagnosticSequenceMetadata[]>([])
  const [seqLoading, setSeqLoading] = useState(true)
  const [selectedKey, setSelectedKey] = useState<string>('')

  // Params form state — keyed by param name, reset when sequence changes.
  const [paramValues, setParamValues] = useState<Record<string, ParamValue>>({})
  const [runBy, setRunBy] = useState<string>('')

  const [running, setRunning] = useState(false)
  const [lastResult, setLastResult] = useState<SequenceRunResponse | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)

  const [recentRuns, setRecentRuns] = useState<DiagnosticRunSummary[]>([])
  const [recentLoading, setRecentLoading] = useState(false)

  const selectedSequence = useMemo(
    () => sequences.find((s) => s.key === selectedKey) || null,
    [sequences, selectedKey],
  )
  const selectedParamGroups = useMemo(() => {
    const params = selectedSequence?.params_schema ?? []
    return {
      file: params.filter((p) => p.name === 'remote_playback_file'),
      switches: params.filter((p) => p.type === 'boolean'),
      other: params.filter((p) => p.name !== 'remote_playback_file' && p.type !== 'boolean'),
    }
  }, [selectedSequence])
  const resultKpiRows = useMemo(
    () => (lastResult ? getKpiRows(lastResult.extra) : []),
    [lastResult],
  )
  const resultInstrumentModes = useMemo(
    () => (lastResult ? getInstrumentModes(lastResult.extra) : null),
    [lastResult],
  )
  const resultFs16Playback = useMemo(
    () => (lastResult ? getFs16Playback(lastResult.extra) : null),
    [lastResult],
  )
  const resultFs16PlaybackRows = useMemo(
    () => getFs16PlaybackRows(resultFs16Playback),
    [resultFs16Playback],
  )
  const resultCleanupWarnings = useMemo(
    () => (lastResult ? getCleanupWarnings(lastResult.extra) : []),
    [lastResult],
  )

  // Initial load: labs + sequences in parallel.
  useEffect(() => {
    setLabsLoading(true)
    fetchLabProfiles()
      .then((data) => {
        setLabs(data)
        if (data.length > 0) setSelectedLabId(data[0].id)
      })
      .catch((e: unknown) => {
        notifications.show({
          title: '加载 LabProfile 失败',
          message: (e as Error)?.message || String(e),
          color: 'red',
        })
      })
      .finally(() => setLabsLoading(false))

    setSeqLoading(true)
    listDiagnosticSequences()
      .then((data) => {
        setSequences(data)
        if (data.length > 0) setSelectedKey(data[0].key)
      })
      .catch((e: unknown) => {
        notifications.show({
          title: '加载序列失败',
          message: (e as Error)?.message || String(e),
          color: 'red',
        })
      })
      .finally(() => setSeqLoading(false))
  }, [])

  // Reset param form whenever the selected sequence changes — defaults
  // come from the metadata-declared schema.
  useEffect(() => {
    if (!selectedSequence) {
      setParamValues({})
      return
    }
    const next: Record<string, ParamValue> = {}
    for (const p of selectedSequence.params_schema) {
      if (p.default !== undefined && p.default !== null) {
        next[p.name] = p.default as ParamValue
      } else if (p.type === 'number') {
        next[p.name] = 0
      } else if (p.type === 'boolean') {
        next[p.name] = false
      } else {
        next[p.name] = ''
      }
    }
    setParamValues(next)
  }, [selectedSequence])

  const refreshRecent = () => {
    setRecentLoading(true)
    listDiagnosticRuns({ kind: 'scpi_sequence', limit: 20 })
      .then((res) => setRecentRuns(res.items))
      .catch(() => {
        /* recent list is best-effort; don't notify */
      })
      .finally(() => setRecentLoading(false))
  }

  useEffect(refreshRecent, [])

  const handleRun = async () => {
    if (!selectedKey) return
    setRunning(true)
    setLastError(null)
    setLastResult(null)
    try {
      const resp = await runDiagnosticSequence(selectedKey, {
        lab_profile_id: selectedLabId || undefined,
        params: paramValues,
        run_by: runBy || undefined,
      })
      setLastResult(resp)
      notifications.show({
        title: resp.success ? '序列执行成功' : '序列报告失败',
        message: resp.summary,
        color: resp.success ? 'green' : 'orange',
        icon: resp.success ? <IconCheck size={18} /> : <IconAlertTriangle size={18} />,
      })
      logFrontendEvent({
        action: 'diagnostic_sequence.run',
        component: 'SequenceRunnerPanel',
        message: `key=${selectedKey} success=${resp.success} duration=${resp.duration_ms}ms lab=${selectedLabId || '-'}`,
      })
      refreshRecent()
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e as Error)?.message ||
        '执行失败'
      setLastError(typeof detail === 'string' ? detail : JSON.stringify(detail))
      notifications.show({
        title: '执行失败',
        message: typeof detail === 'string' ? detail : JSON.stringify(detail),
        color: 'red',
        icon: <IconX size={18} />,
      })
      logFrontendEvent({
        level: 'ERROR',
        action: 'diagnostic_sequence.run_failed',
        component: 'SequenceRunnerPanel',
        error: typeof detail === 'string' ? detail : JSON.stringify(detail),
      })
    } finally {
      setRunning(false)
    }
  }

  const renderParamField = (spec: DiagnosticSequenceMetadata['params_schema'][number]) => {
    const value = paramValues[spec.name]
    const label = getParamLabel(spec)
    const description = getParamDescription(spec)
    if (spec.options && spec.options.length > 0) {
      return (
        <Select
          key={spec.name}
          label={label}
          description={description}
          data={spec.options.map((option) => ({ value: option, label: option }))}
          value={typeof value === 'string' ? value : String(spec.default ?? spec.options[0] ?? '')}
          onChange={(v) =>
            setParamValues((p) => ({
              ...p,
              [spec.name]: v || String(spec.default ?? spec.options?.[0] ?? ''),
            }))
          }
          allowDeselect={false}
          style={{ minWidth: 0 }}
          styles={{
            label: { lineHeight: 1.25 },
            description: { lineHeight: 1.2 },
          }}
        />
      )
    }
    if (spec.type === 'number') {
      return (
        <NumberInput
          key={spec.name}
          label={label}
          description={description}
          value={typeof value === 'number' ? value : 0}
          onChange={(v) => setParamValues((p) => ({ ...p, [spec.name]: Number(v) }))}
          style={{ minWidth: 0 }}
          styles={{
            label: { lineHeight: 1.25 },
            description: { lineHeight: 1.2 },
          }}
        />
      )
    }
    if (spec.type === 'boolean') {
      return (
        <Switch
          key={spec.name}
          label={label}
          description={description}
          checked={Boolean(value)}
          onChange={(e) =>
            setParamValues((p) => ({ ...p, [spec.name]: e.currentTarget.checked }))
          }
          style={{ minWidth: 0 }}
          styles={{
            body: { alignItems: 'flex-start' },
            label: { lineHeight: 1.25 },
            description: { lineHeight: 1.2 },
          }}
        />
      )
    }
    return (
      <TextInput
        key={spec.name}
        label={label}
        description={description}
        value={typeof value === 'string' ? value : ''}
        onChange={(e) =>
          setParamValues((p) => ({ ...p, [spec.name]: e.currentTarget.value }))
        }
        style={{ minWidth: 0 }}
        styles={{
          label: { lineHeight: 1.25 },
          description: { lineHeight: 1.2 },
        }}
      />
    )
  }

  return (
    <Stack gap="md">
      <Paper p="md" withBorder>
        <Stack gap="xs">
          <Group gap="xs">
            <IconTerminal size={18} />
            <Title order={4}>调试序列 (Sequence Runner)</Title>
            <Badge color="orange" variant="light" size="sm">workshop tier</Badge>
          </Group>
          <Text size="sm" c="dimmed">
            序列代码活在{' '}
            <Code>api-service/app/diagnostics/sequences/</Code>{' '}
            目录下,改完重启就能用. 这里所有运行都记入{' '}
            <Code>diagnostic_runs</Code>{' '}
            审计表 (查"昨天打通的命令")  —  但不进 TestPlan 链路, 不出正式 cert.
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
              <Select
                label="LabProfile"
                description="多数序列需要绑定 lab 才能找到仪器 endpoint; 直连 IP 类可留空"
                data={labs.map((l) => ({
                  value: l.id,
                  label: l.chamber_name ? `${l.name} — ${l.chamber_name}` : l.name,
                }))}
                value={selectedLabId || null}
                onChange={(v) => setSelectedLabId(v || '')}
                placeholder="选择 LabProfile..."
                clearable
              />
            )}
            {seqLoading ? (
              <Group gap="xs">
                <Loader size="xs" />
                <Text size="sm" c="dimmed">加载序列...</Text>
              </Group>
            ) : (
              <Select
                label="序列"
                data={sequences.map((s) => ({ value: s.key, label: s.name }))}
                value={selectedKey || null}
                onChange={(v) => v && setSelectedKey(v)}
                required
                allowDeselect={false}
              />
            )}
          </Group>

          {selectedSequence && (
            <Alert color={selectedSequence.safe_during_test ? 'blue' : 'yellow'} variant="light"
              icon={selectedSequence.safe_during_test ? <IconCheck size={18} /> : <IconAlertTriangle size={18} />}
              title={selectedSequence.safe_during_test ? '可在测试运行中执行' : '会改变仪器状态 — 不要在正式测试中跑'}
            >
              <Stack gap={4}>
                <Text size="sm">{selectedSequence.description}</Text>
                {selectedSequence.required_categories.length > 0 && (
                  <Text size="xs" c="dimmed">
                    需要 lab 绑定: {selectedSequence.required_categories.join(', ')}
                  </Text>
                )}
              </Stack>
            </Alert>
          )}

          {selectedSequence && selectedSequence.params_schema.length > 0 && (
            <>
              <Divider label="参数" labelPosition="left" />
              <Stack gap="md">
                {selectedParamGroups.file.length > 0 && (
                  <Stack gap={6}>
                    <Text size="xs" fw={700} c="dimmed">文件</Text>
                    <SimpleGrid cols={1} spacing="md">
                      {selectedParamGroups.file.map(renderParamField)}
                    </SimpleGrid>
                  </Stack>
                )}

                {selectedParamGroups.switches.length > 0 && (
                  <Stack gap={6}>
                    <Text size="xs" fw={700} c="dimmed">开关选项</Text>
                    <SimpleGrid
                      cols={{ base: 1, sm: 2, lg: 3 }}
                      spacing="md"
                      verticalSpacing="sm"
                    >
                      {selectedParamGroups.switches.map(renderParamField)}
                    </SimpleGrid>
                  </Stack>
                )}

                {selectedParamGroups.other.length > 0 && (
                  <Stack gap={6}>
                    <Text size="xs" fw={700} c="dimmed">运行参数</Text>
                    <SimpleGrid
                      cols={{ base: 1, sm: 2, lg: 3, xl: 4 }}
                      spacing="md"
                      verticalSpacing="sm"
                    >
                      {selectedParamGroups.other.map(renderParamField)}
                    </SimpleGrid>
                  </Stack>
                )}
              </Stack>
            </>
          )}

          <TextInput
            label="操作员"
            placeholder="工号 / 姓名 (审计行)"
            value={runBy}
            onChange={(e) => setRunBy(e.currentTarget.value)}
          />

          <Group justify="flex-end">
            <Button
              leftSection={<IconPlayerPlay size={16} />}
              onClick={handleRun}
              disabled={!selectedKey || running}
              loading={running}
            >
              运行序列
            </Button>
          </Group>
        </Stack>
      </Paper>

      {/* Result panel */}
      {(lastResult || lastError) && (
        <Paper p="md" withBorder>
          {lastError ? (
            <Alert color="red" icon={<IconAlertCircle size={18} />} title="执行失败 (HTTP)">
              {lastError}
            </Alert>
          ) : lastResult && (
            <Stack gap="sm">
              <Group gap="sm">
                <Title order={5}>结果</Title>
                <Badge color={lastResult.success ? 'green' : 'orange'}>
                  {lastResult.success ? 'success' : 'failure'}
                </Badge>
                <Badge variant="light">{lastResult.duration_ms} ms</Badge>
                <Code>{lastResult.diagnostic_run_id.slice(0, 8)}...</Code>
              </Group>
              <Text size="sm">{lastResult.summary}</Text>
              {resultInstrumentModes && (
                <Group gap="xs" wrap="wrap">
                  <Badge color="blue" variant="light">
                    CE {String(resultInstrumentModes.channelEmulator || '-')}
                  </Badge>
                  <Badge color={resultInstrumentModes.baseStation === 'real' ? 'red' : 'gray'} variant="light">
                    BS {String(resultInstrumentModes.baseStation || '-')}
                  </Badge>
                  <Badge color="gray" variant="light">
                    DUT {String(resultInstrumentModes.DUT || '-')}
                  </Badge>
                  {Boolean(resultInstrumentModes.kpi_source) && (
                    <Badge color="cyan" variant="outline">
                      KPI: {String(resultInstrumentModes.kpi_source)}
                    </Badge>
                  )}
                </Group>
              )}
              {resultFs16Playback && typeof resultFs16Playback.playback_left_running === 'boolean' && (
                <Group gap="xs" wrap="wrap">
                  <Badge
                    color={resultFs16Playback.playback_left_running ? 'red' : 'green'}
                    variant="light"
                  >
                    FS16 playback {resultFs16Playback.playback_left_running ? 'left running' : 'stopped'}
                  </Badge>
                  {typeof resultFs16Playback.bs_signaling_left_running === 'boolean' && (
                    <Badge
                      color={resultFs16Playback.bs_signaling_left_running ? 'orange' : 'green'}
                      variant="light"
                    >
                      BS signaling {resultFs16Playback.bs_signaling_left_running ? 'left running' : 'stopped'}
                    </Badge>
                  )}
                </Group>
              )}
              {resultFs16PlaybackRows.length > 0 && (
                <>
                  <Divider label="FS16 playback" labelPosition="left" />
                  <Table.ScrollContainer minWidth={520}>
                    <Table withTableBorder withColumnBorders striped>
                      <Table.Tbody>
                        {resultFs16PlaybackRows.map((row) => (
                          <Table.Tr key={row.label}>
                            <Table.Td w={180}>
                              <Text size="sm" fw={500}>{row.label}</Text>
                            </Table.Td>
                            <Table.Td>
                              {typeof row.value === 'boolean' ? (
                                <Badge
                                  size="sm"
                                  color={fs16BooleanColor(row.label, row.value)}
                                  variant="light"
                                >
                                  {formatExtraValue(row.value)}
                                </Badge>
                              ) : (
                                <Text size="sm" style={{ wordBreak: 'break-all' }}>
                                  {formatExtraValue(row.value)}
                                </Text>
                              )}
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                </>
              )}
              {resultCleanupWarnings.length > 0 && (
                <Alert color="orange" icon={<IconAlertTriangle size={18} />} title="Cleanup warnings">
                  <Stack gap={2}>
                    {resultCleanupWarnings.map((warning, index) => (
                      <Text key={`${warning}-${index}`} size="xs">{warning}</Text>
                    ))}
                  </Stack>
                </Alert>
              )}
              {resultKpiRows.length > 0 && (
                <>
                  <Divider label="KPI 摘要" labelPosition="left" />
                  <Table.ScrollContainer minWidth={560}>
                    <Table striped highlightOnHover withTableBorder withColumnBorders>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>指标</Table.Th>
                          <Table.Th>Mean</Table.Th>
                          <Table.Th>Min</Table.Th>
                          <Table.Th>Max</Table.Th>
                          <Table.Th>Std</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {resultKpiRows.map((row) => (
                          <Table.Tr key={row.key}>
                            <Table.Td>
                              <Text size="sm" fw={500}>{row.label}</Text>
                            </Table.Td>
                            <Table.Td>{formatKpi(row.value.mean, row.unit)}</Table.Td>
                            <Table.Td>{formatKpi(row.value.min, row.unit)}</Table.Td>
                            <Table.Td>{formatKpi(row.value.max, row.unit)}</Table.Td>
                            <Table.Td>{formatKpi(row.value.std, row.unit)}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                  <Text size="xs" c="dimmed">
                    当前 hybrid smoke 的终端通信性能指标来自 mock BS/DUT 或所选 BS driver 的 KPI surface；FS16 负责真实 .smu playback 控制链路。
                  </Text>
                </>
              )}
              {lastResult.steps.length > 0 && (
                <Stack gap={4}>
                  {lastResult.steps.map((s, i) => (
                    <Stack key={i} gap={2}>
                      <Group gap="xs" wrap="nowrap" align="flex-start">
                        <Badge color={s.success ? 'green' : 'red'} size="sm" variant="filled">
                          {s.success ? '✓' : '✗'}
                        </Badge>
                        <Text size="xs" fw={500} style={{ flexShrink: 0 }}>{s.label}</Text>
                        <Text size="xs" c="dimmed" style={{ wordBreak: 'break-all' }}>
                          {s.detail}
                        </Text>
                        {s.duration_ms !== undefined && s.duration_ms !== null && (
                          <Text size="xs" c="dimmed" ml="auto">{s.duration_ms} ms</Text>
                        )}
                      </Group>
                      {/* 仪器原始回复单独一行 —— 现场"它到底返回什么字面值"是
                          一整类待验问题的问法, 混进 detail 就抄不准。空串回复
                          也要显示 (是一条结论), 故判 null/undefined 而非真值。 */}
                      {s.raw !== undefined && s.raw !== null && (
                        <Code
                          style={{ fontSize: 11, marginLeft: 34, wordBreak: 'break-all' }}
                        >
                          {JSON.stringify(s.raw)}
                        </Code>
                      )}
                    </Stack>
                  ))}
                </Stack>
              )}
              {lastResult.log.length > 0 && (
                <>
                  <Divider label="日志" labelPosition="left" />
                  <ScrollArea h={150}>
                    <Code block style={{ fontSize: 12 }}>
                      {lastResult.log.join('\n')}
                    </Code>
                  </ScrollArea>
                </>
              )}
            </Stack>
          )}
        </Paper>
      )}

      {/* Recent runs */}
      <Paper p="md" withBorder>
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            <IconHistory size={16} />
            <Title order={5}>最近运行 (本类型)</Title>
            <Badge variant="light">{recentRuns.length}</Badge>
          </Group>
          <Button
            variant="subtle"
            size="xs"
            leftSection={<IconRefresh size={14} />}
            onClick={refreshRecent}
            loading={recentLoading}
          >
            刷新
          </Button>
        </Group>

        {recentLoading ? (
          <Center py="md"><Loader size="sm" /></Center>
        ) : recentRuns.length === 0 ? (
          <Text size="sm" c="dimmed">还没有运行历史</Text>
        ) : (
          <ScrollArea h={Math.min(280, 40 + recentRuns.length * 28)}>
            <Stack gap={4}>
              {recentRuns.map((r) => (
                <Group key={r.id} gap="xs" wrap="nowrap">
                  <Badge color={r.success ? 'green' : 'red'} size="xs" variant="filled">
                    {r.success ? '✓' : '✗'}
                  </Badge>
                  <Code style={{ flexShrink: 0 }}>{r.target_name}</Code>
                  {r.duration_ms != null && (
                    <Badge variant="light" size="xs">{r.duration_ms} ms</Badge>
                  )}
                  <Text size="xs" c="dimmed" style={{ flexShrink: 0 }}>
                    {new Date(r.run_at).toLocaleString()}
                  </Text>
                  {r.run_by && (
                    <Text size="xs" c="dimmed" ml="auto">@ {r.run_by}</Text>
                  )}
                </Group>
              ))}
            </Stack>
          </ScrollArea>
        )}
      </Paper>
    </Stack>
  )
}
