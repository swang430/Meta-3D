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
  UnstyledButton,
} from '@mantine/core'
import {
  IconAlertTriangle,
  IconAlertCircle,
  IconCheck,
  IconFolderOpen,
  IconHistory,
  IconLogout,
  IconPlayerPause,
  IconPlayerPlay,
  IconPlayerStop,
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
  getDiagnosticSequenceProgress,
  sendInstrumentScpiCommand,
  listDiagnosticRuns,
  getDiagnosticRun,
  type DiagnosticSequenceMetadata,
  type DiagnosticRunDetail,
  type ScpiCommandResult,
  type SequenceRunResponse,
  type DiagnosticRunSummary,
  type DiagnosticSequenceProgress,
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
  cell: 'NR 小区',
  duration_s: '持续时间（秒）',
  sample_interval_s: '采样间隔（秒）',
  measurement_length_slots: 'BTPut 窗口（DL Slot）',
}

const PARAM_DESCRIPTION_OVERRIDES: Record<string, string> = {
  remote_playback_file: 'FS16 内已有文件名，或完整 D:\\ 路径',
  source_smu_file: 'FS16 内已有 .smu 文件名，或完整 D:\\ 路径',
  verify_source_file_exists: '先查目录，确认模板 .smu 可见',
  emulation_name: '仅记录/对照；v1 不从零创建新 emulation',
  working_directory: '用于记录和读回对照，不作为新建目录指令',
  downlink_channel_model: 'v1 从模板读回校验，不自动导入新 .ctap',
  uplink_channel_model: 'v1 从模板读回校验，不自动导入新 .ctap',
  channel_numbers: '用于中心频率修改、模型和 connector readback',
  input_numbers: '用于 INP:EN / INP:LEV / INP:CRE:SET',
  output_numbers: '用于 OUTP:EN / OUTP:LEV',
  connector_map: '期望 connector，格式 BS1.1=RF1,UE1.1=RF3',
  connect_after_edit: '执行 CALC:FILT:CONN 加载到硬件路径',
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
  cell: 'RF App 最大DL吞吐第一版固定使用 CELL1',
  duration_s: '默认30秒；仅控制测量流程，不改变当前小区参数',
  sample_interval_s: '默认每1秒读取一次 BTPut 和 TMONitor',
  measurement_length_slots: '范围200–360000，必须为200的整数倍；默认200便于连续观察',
}

const FS16_PLAYBACK_CONTROLS = [
  {
    key: 'pause',
    label: '暂停',
    command: 'DIAG:SIMU:STOP',
    color: 'yellow',
    icon: IconPlayerPause,
  },
  {
    key: 'continue',
    label: '继续',
    command: 'DIAG:SIMU:CONT',
    color: 'blue',
    icon: IconPlayerPlay,
  },
  {
    key: 'stop',
    label: '停止回起点',
    command: 'DIAG:SIMU:GOS',
    color: 'red',
    icon: IconPlayerStop,
  },
  {
    key: 'close',
    label: '关闭界面',
    command: 'DIAG:SIMU:CLOSE',
    color: 'gray',
    icon: IconX,
  },
] as const

type Fs16PlaybackControl = (typeof FS16_PLAYBACK_CONTROLS)[number]

const FS16_ADD_EMULATION_PARAM_GROUPS = [
  {
    step: 1,
    title: 'Step 1/5 Basic information',
    names: [
      'emulation_name',
      'emulation_description',
      'working_directory',
      'bandwidth_mhz',
      'creation_style',
    ],
  },
  {
    step: 2,
    title: 'Step 2/5 Device and link information',
    names: [
      'radio_technology',
      'bs_name',
      'ms_name',
      'link_bandwidth_mhz',
      'bs_tx_antennas',
      'bs_rx_antennas',
      'ms_tx_antennas',
      'ms_rx_antennas',
      'connector_selection',
      'downlink_channel_model',
      'uplink_channel_model',
      'distribution_seed',
      'insertion_delay_optimization',
      'shadowing',
    ],
  },
  {
    step: 3,
    title: 'Step 3/5 Environment variables',
    names: [
      'band',
      'channel_number',
      'center_frequency_mhz',
      'crest_factor_db',
      'dl_max_tx_power_dbm',
      'ul_max_tx_power_dbm',
      'in_loss_db',
      'dl_path_loss_db',
      'ul_path_loss_db',
      'out_loss_db',
      'out_level_dbm',
      'channel_numbers',
      'input_numbers',
      'output_numbers',
      'apply_center_frequency',
      'apply_input_levels',
      'apply_output_levels',
    ],
  },
  {
    step: 4,
    title: 'Step 4/5 Active connectors selection',
    names: ['connector_map'],
  },
  {
    step: 5,
    title: 'Step 5/5 Connect / run',
    names: ['connect_after_edit', 'start_after_connect', 'cleanup_on_finish'],
  },
] as const

const FS16_ADD_EMULATION_TOTAL_STEPS = 5

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

type ResultSource =
  | { type: 'live' }
  | { type: 'history'; runAt: string; structured: boolean }

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

function getFs16AddEmulation(extra: Record<string, unknown>) {
  const raw = extra.fs16_add_emulation
  return isRecord(raw) ? raw : null
}

type UxmDlSample = {
  sampleIndex: number
  timestamp: string
  valid: boolean
  source: string
  throughput: number | null
  bler: number | null
  progressCount: number | null
  tmonitorPeak: number | null
  rawBtput: string
  rawTmonitor: string
}

function optionalNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function getUxmRfAppDlThroughput(extra: Record<string, unknown>) {
  const detail = extra.uxm_rf_app_dl_throughput
  if (!isRecord(detail)) return null
  const rawSamples = Array.isArray(extra.samples) ? extra.samples : []
  const samples = rawSamples
    .map((item, index): UxmDlSample | null => {
      if (!isRecord(item)) return null
      return {
        sampleIndex: optionalNumber(item.sample_index) ?? index + 1,
        timestamp: typeof item.timestamp === 'string' ? item.timestamp : '',
        valid: Boolean(item.valid),
        source: typeof item.source === 'string' ? item.source : 'unknown',
        throughput: optionalNumber(item.dl_throughput_mbps),
        bler: optionalNumber(item.dl_bler),
        progressCount: optionalNumber(item.progress_count),
        tmonitorPeak: optionalNumber(item.tmonitor_peak_mbps),
        rawBtput: typeof item.raw_btput === 'string' ? item.raw_btput : '',
        rawTmonitor: typeof item.raw_tmonitor === 'string' ? item.raw_tmonitor : '',
      }
    })
    .filter((item): item is UxmDlSample => item !== null)
  return {
    detail,
    samples,
    cellConfig: isRecord(extra.cell_config) ? extra.cell_config : null,
    cleanup: isRecord(extra.cleanup) ? extra.cleanup : null,
    instrument: isRecord(extra.instrument) ? extra.instrument : null,
  }
}

function formatBlerPercent(value: number | undefined | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-'
  return `${(value * 100).toFixed(2)}%`
}

type UxmLiveSample = {
  index: number
  total: number
  throughput: number | null
  bler: number | null
  source: string
}

function parseUxmLiveSamples(logLines: string[]): UxmLiveSample[] {
  const pattern = /sample\s+(\d+)\/(\d+):\s+DL=([^ ]+)\s+Mbps,\s+BLER=([^,]+),\s+source=(\S+)/i
  return logLines
    .map((line) => {
      const match = pattern.exec(line)
      if (!match) return null
      const throughput = Number(match[3])
      const bler = Number(match[4])
      return {
        index: Number(match[1]),
        total: Number(match[2]),
        throughput: Number.isFinite(throughput) ? throughput : null,
        bler: Number.isFinite(bler) ? bler : null,
        source: match[5],
      }
    })
    .filter((sample): sample is UxmLiveSample => sample !== null)
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

function getScpiResultDetail(result: ScpiCommandResult): string {
  if (result.response && result.response.trim()) {
    return result.response.trim()
  }
  if (result.error && result.error.trim()) {
    return result.error.trim()
  }
  return `${result.command} (${Math.round(result.latency_ms)} ms)`
}

function isFs16AlreadyOpenForEditing(value: string): boolean {
  return /already open for editing/i.test(value) || /SMU file already open/i.test(value)
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

function getFs16AddEmulationRows(addEmulation: Record<string, unknown> | null) {
  if (!addEmulation) return []
  const readback = isRecord(addEmulation.readback) ? addEmulation.readback : {}
  const rows = [
    ['Source .smu', addEmulation.source_smu_file],
    ['Simulation state', readback.simulation_state],
    ['Model info', readback.model_info],
    ['Left running', addEmulation.emulation_left_running],
    [
      'Applied SCPI',
      Array.isArray(addEmulation.applied_scpi) ? addEmulation.applied_scpi.length : undefined,
    ],
  ] as const
  return rows
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([label, value]) => ({ label, value }))
}

function getFs16AddEmulationWizardSteps(addEmulation: Record<string, unknown> | null) {
  const raw = addEmulation?.wizard_steps
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => {
      if (!isRecord(item)) return null
      return {
        step: typeof item.step === 'number' ? item.step : null,
        label: typeof item.label === 'string' ? item.label : '',
        success: Boolean(item.success),
        detail: formatExtraValue(item.detail),
        duration_ms: typeof item.duration_ms === 'number' ? item.duration_ms : null,
      }
    })
    .filter((item): item is NonNullable<typeof item> => item !== null && Boolean(item.label))
}

function getFs16AddEmulationScpi(addEmulation: Record<string, unknown> | null) {
  const raw = addEmulation?.applied_scpi
  return Array.isArray(raw) ? raw.map(String).filter(Boolean) : []
}

function getFs16AddEmulationUnsupported(addEmulation: Record<string, unknown> | null) {
  const raw = addEmulation?.unsupported_fields
  return Array.isArray(raw) ? raw.map(String).filter(Boolean) : []
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

function normalizeSequenceSteps(value: unknown): SequenceRunResponse['steps'] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (!isRecord(item)) return null
      const label = typeof item.label === 'string' ? item.label : ''
      if (!label) return null
      return {
        label,
        success: Boolean(item.success),
        detail: typeof item.detail === 'string' ? item.detail : formatExtraValue(item.detail),
        duration_ms: typeof item.duration_ms === 'number' ? item.duration_ms : null,
      }
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)
}

function normalizeStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : []
}

function parseHistoricalOutput(output?: string | null) {
  const parsed: {
    summary?: string
    log: string[]
    steps: SequenceRunResponse['steps']
  } = {
    log: [],
    steps: [],
  }
  if (!output) return parsed

  let mode: 'none' | 'log' | 'steps' = 'none'
  for (const line of output.split(/\r?\n/)) {
    if (line.startsWith('summary:')) {
      parsed.summary = line.slice('summary:'.length).trim()
      mode = 'none'
      continue
    }
    if (line.trim() === 'log:') {
      mode = 'log'
      continue
    }
    if (line.trim() === 'steps:') {
      mode = 'steps'
      continue
    }
    if (!line.trim()) continue
    if (mode === 'log') {
      parsed.log.push(line)
      continue
    }
    if (mode === 'steps') {
      const match = line.match(/^\s*([✓✗])\s+([^:]+):\s*(.*)$/)
      if (match) {
        parsed.steps.push({
          success: match[1] === '✓',
          label: match[2].trim(),
          detail: match[3].trim(),
          duration_ms: null,
        })
      }
    }
  }
  return parsed
}

function buildSequenceResultFromDetail(detail: DiagnosticRunDetail) {
  const sequenceResult = detail.sequence_result
  const structured = isRecord(sequenceResult)
  const raw: Record<string, unknown> = structured ? sequenceResult : {}
  const parsedOutput = parseHistoricalOutput(detail.output_excerpt)
  const normalizedLog = normalizeStringList(raw.log)
  const normalizedSteps = normalizeSequenceSteps(raw.steps)
  const summary =
    (typeof raw.summary === 'string' && raw.summary) ||
    parsedOutput.summary ||
    detail.error_message ||
    (detail.success ? '历史运行成功' : '历史运行失败')
  const result: SequenceRunResponse = {
    diagnostic_run_id: detail.id,
    success: typeof raw.success === 'boolean' ? raw.success : detail.success,
    summary,
    duration_ms:
      typeof raw.duration_ms === 'number'
        ? raw.duration_ms
        : detail.duration_ms ?? 0,
    log: normalizedLog.length > 0 ? normalizedLog : parsedOutput.log,
    steps: normalizedSteps.length > 0 ? normalizedSteps : parsedOutput.steps,
    extra: isRecord(raw.extra) ? raw.extra : {},
  }
  return { result, structured }
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
  const [fs16AddActiveStep, setFs16AddActiveStep] = useState(1)
  const [fs16SourceOpenBusy, setFs16SourceOpenBusy] = useState(false)
  const [fs16SourceCloseBusy, setFs16SourceCloseBusy] = useState(false)
  const [fs16SourceOpened, setFs16SourceOpened] = useState(false)
  const [fs16SourceOpenDetail, setFs16SourceOpenDetail] = useState<string | null>(null)
  const [runBy, setRunBy] = useState<string>('')

  const [running, setRunning] = useState(false)
  const [fs16ControlBusy, setFs16ControlBusy] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<SequenceRunResponse | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)
  const [resultSource, setResultSource] = useState<ResultSource | null>(null)
  const [liveProgress, setLiveProgress] = useState<DiagnosticSequenceProgress | null>(null)

  const [recentRuns, setRecentRuns] = useState<DiagnosticRunSummary[]>([])
  const [recentLoading, setRecentLoading] = useState(false)
  const [restoringRunId, setRestoringRunId] = useState<string | null>(null)

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
  const isFs16AddEmulation = selectedSequence?.key === 'fs16_add_emulation'
  const fs16SourceFile =
    typeof paramValues.source_smu_file === 'string'
      ? paramValues.source_smu_file.trim()
      : String(paramValues.source_smu_file ?? '').trim()
  const fs16AddCanRun =
    !isFs16AddEmulation ||
    (fs16SourceOpened && fs16AddActiveStep === FS16_ADD_EMULATION_TOTAL_STEPS)
  const showFs16PlaybackControls = useMemo(() => {
    if (!selectedSequence) return false
    const searchText = [
      selectedSequence.key,
      selectedSequence.name,
      selectedSequence.description,
    ]
      .join(' ')
      .toLowerCase()
    return searchText.includes('fs16') || searchText.includes('propsim')
  }, [selectedSequence])
  const resultKpiRows = useMemo(
    () => (lastResult ? getKpiRows(lastResult.extra) : []),
    [lastResult],
  )
  const resultInstrumentModes = useMemo(
    () => (lastResult ? getInstrumentModes(lastResult.extra) : null),
    [lastResult],
  )
  const resultUxmRfAppDl = useMemo(
    () => (lastResult ? getUxmRfAppDlThroughput(lastResult.extra) : null),
    [lastResult],
  )
  const liveUxmSamples = useMemo(
    () => parseUxmLiveSamples(liveProgress?.log ?? []),
    [liveProgress],
  )
  const resultFs16Playback = useMemo(
    () => (lastResult ? getFs16Playback(lastResult.extra) : null),
    [lastResult],
  )
  const resultFs16PlaybackRows = useMemo(
    () => getFs16PlaybackRows(resultFs16Playback),
    [resultFs16Playback],
  )
  const resultFs16AddEmulation = useMemo(
    () => (lastResult ? getFs16AddEmulation(lastResult.extra) : null),
    [lastResult],
  )
  const resultFs16AddEmulationRows = useMemo(
    () => getFs16AddEmulationRows(resultFs16AddEmulation),
    [resultFs16AddEmulation],
  )
  const resultFs16AddEmulationWizardSteps = useMemo(
    () => getFs16AddEmulationWizardSteps(resultFs16AddEmulation),
    [resultFs16AddEmulation],
  )
  const resultFs16AddEmulationScpi = useMemo(
    () => getFs16AddEmulationScpi(resultFs16AddEmulation),
    [resultFs16AddEmulation],
  )
  const resultFs16AddEmulationUnsupported = useMemo(
    () => getFs16AddEmulationUnsupported(resultFs16AddEmulation),
    [resultFs16AddEmulation],
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
    setFs16AddActiveStep(1)
    setFs16SourceOpened(false)
    setFs16SourceOpenDetail(null)
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

  useEffect(() => {
    if (!isFs16AddEmulation) return
    setFs16SourceOpened(false)
    setFs16SourceOpenDetail(null)
    setParamValues((prev) => ({ ...prev, source_already_opened: false }))
  }, [fs16SourceFile, isFs16AddEmulation])

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
    setResultSource(null)
    setLiveProgress(null)
    const progressToken = crypto.randomUUID()
    let progressTimer: number | undefined
    const refreshProgress = async () => {
      try {
        const progress = await getDiagnosticSequenceProgress(progressToken)
        setLiveProgress(progress)
      } catch {
        // The first poll can race the POST before it registers the token.
      }
    }
    try {
      progressTimer = window.setInterval(refreshProgress, 500)
      const resp = await runDiagnosticSequence(selectedKey, {
        lab_profile_id: selectedLabId || undefined,
        params: paramValues,
        run_by: runBy || undefined,
        progress_token: progressToken,
      })
      await refreshProgress()
      setLastResult(resp)
      setResultSource({ type: 'live' })
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
      setResultSource(null)
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
      if (progressTimer !== undefined) window.clearInterval(progressTimer)
      setRunning(false)
    }
  }

  const handleRestoreRecentRun = async (run: DiagnosticRunSummary) => {
    setRestoringRunId(run.id)
    setLastError(null)
    try {
      const detail = await getDiagnosticRun(run.id)
      const sequenceKey = isRecord(detail.params) && typeof detail.params.sequence_key === 'string'
        ? detail.params.sequence_key
        : detail.target_name
      if (sequenceKey && sequences.some((s) => s.key === sequenceKey)) {
        setSelectedKey(sequenceKey)
      }
      const { result, structured } = buildSequenceResultFromDetail(detail)
      setLastResult(result)
      setResultSource({ type: 'history', runAt: detail.run_at, structured })
      notifications.show({
        title: structured ? '已恢复历史结果' : '已恢复历史摘要',
        message: structured
          ? `${detail.target_name} @ ${new Date(detail.run_at).toLocaleString()}`
          : '这条旧记录没有保存 KPI/FS16 明细；新运行会完整保存。',
        color: structured ? 'blue' : 'yellow',
        icon: structured ? <IconHistory size={18} /> : <IconAlertTriangle size={18} />,
      })
      logFrontendEvent({
        action: 'diagnostic_sequence.restore_history',
        component: 'SequenceRunnerPanel',
        message: `run=${run.id} target=${detail.target_name} structured=${structured}`,
      })
    } catch (e: unknown) {
      const message =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e as Error)?.message ||
        '恢复历史运行失败'
      notifications.show({
        title: '恢复历史运行失败',
        message: typeof message === 'string' ? message : JSON.stringify(message),
        color: 'red',
        icon: <IconX size={18} />,
      })
      logFrontendEvent({
        level: 'ERROR',
        action: 'diagnostic_sequence.restore_history_failed',
        component: 'SequenceRunnerPanel',
        error: typeof message === 'string' ? message : JSON.stringify(message),
      })
    } finally {
      setRestoringRunId(null)
    }
  }

  const handleFs16PlaybackControl = async (control: Fs16PlaybackControl) => {
    const ControlIcon = control.icon
    setFs16ControlBusy(control.key)
    try {
      const commandResult = await sendInstrumentScpiCommand('channelEmulator', {
        command: control.command,
        timeout_ms: 10000,
        run_by: runBy || undefined,
      })
      if (!commandResult.success) {
        throw new Error(getScpiResultDetail(commandResult))
      }

      let stateDetail = ''
      try {
        const stateResult = await sendInstrumentScpiCommand('channelEmulator', {
          command: 'DIAG:SIMU:STATE?',
          timeout_ms: 10000,
          run_by: runBy || undefined,
        })
        if (stateResult.success) {
          stateDetail = `当前状态: ${getScpiResultDetail(stateResult)}`
        }
      } catch {
        stateDetail = ''
      }

      notifications.show({
        title: `FS16 ${control.label}已发送`,
        message: stateDetail || getScpiResultDetail(commandResult),
        color: control.color,
        icon: <ControlIcon size={18} />,
      })
      logFrontendEvent({
        action: 'fs16_playback.control',
        component: 'SequenceRunnerPanel',
        message: `command=${control.command} label=${control.label}`,
      })
    } catch (e: unknown) {
      const message = (e as Error)?.message || String(e)
      notifications.show({
        title: `FS16 ${control.label}失败`,
        message,
        color: 'red',
        icon: <IconX size={18} />,
      })
      logFrontendEvent({
        level: 'ERROR',
        action: 'fs16_playback.control_failed',
        component: 'SequenceRunnerPanel',
        error: `command=${control.command} ${message}`,
      })
    } finally {
      setFs16ControlBusy(null)
    }
  }

  const handleOpenFs16SourceFile = async () => {
    if (!fs16SourceFile) {
      notifications.show({
        title: '源文件路径为空',
        message: '请先输入 FS16 上已有 .smu 的完整路径或文件名。',
        color: 'red',
        icon: <IconX size={18} />,
      })
      return
    }

    if (fs16SourceOpened) {
      const detail = '源文件已在 FS16 编辑态中，可继续配置 Step 1。'
      setFs16SourceOpenDetail(detail)
      setParamValues((prev) => ({ ...prev, source_already_opened: true }))
      notifications.show({
        title: '源文件已打开',
        message: detail,
        color: 'green',
        icon: <IconFolderOpen size={18} />,
      })
      return
    }

    setFs16SourceOpenBusy(true)
    setFs16SourceOpened(false)
    setFs16SourceOpenDetail(null)
    setParamValues((prev) => ({ ...prev, source_already_opened: false }))

    const send = async (command: string, timeoutMs: number) => {
      const result = await sendInstrumentScpiCommand('channelEmulator', {
        command,
        timeout_ms: timeoutMs,
        run_by: runBy || undefined,
      })
      if (!result.success) {
        throw new Error(`${command}: ${getScpiResultDetail(result)}`)
      }
      return result
    }

    try {
      await send('*CLS', 5000)
      await send(`CALC:FILT:EDIT ${fs16SourceFile}`, 30000)
      await send('*OPC?', 30000)
      const err = await send('SYST:ERR?', 10000)
      const errText = getScpiResultDetail(err).trim()
      const alreadyOpenForEditing = isFs16AlreadyOpenForEditing(errText)
      if (errText && !/^0(\b|,)/.test(errText)) {
        if (!alreadyOpenForEditing) {
          throw new Error(`SYST:ERR? returned ${errText}`)
        }
      }

      let stateText = ''
      try {
        const state = await send('DIAG:SIMU:STATE?', 10000)
        stateText = getScpiResultDetail(state)
      } catch {
        stateText = ''
      }

      const detail = alreadyOpenForEditing
        ? '源文件已在 FS16 编辑态中，可继续配置 Step 1。'
        : stateText
          ? `已打开源文件，FS16 状态: ${stateText}`
          : '已打开源文件，FS16 已进入编辑态'
      setFs16SourceOpened(true)
      setFs16SourceOpenDetail(detail)
      setFs16AddActiveStep(1)
      setParamValues((prev) => ({ ...prev, source_already_opened: true }))
      notifications.show({
        title: alreadyOpenForEditing ? '源文件已在编辑态' : '源文件已打开',
        message: detail,
        color: 'green',
        icon: <IconFolderOpen size={18} />,
      })
      logFrontendEvent({
        action: 'fs16_add_emulation.open_source',
        component: 'SequenceRunnerPanel',
        message: `source=${fs16SourceFile} state=${stateText || '-'}`,
      })
    } catch (e: unknown) {
      const message = (e as Error)?.message || String(e)
      setFs16SourceOpened(false)
      setFs16SourceOpenDetail(message)
      setParamValues((prev) => ({ ...prev, source_already_opened: false }))
      notifications.show({
        title: '打开源文件失败',
        message,
        color: 'red',
        icon: <IconX size={18} />,
      })
      logFrontendEvent({
        level: 'ERROR',
        action: 'fs16_add_emulation.open_source_failed',
        component: 'SequenceRunnerPanel',
        error: `source=${fs16SourceFile} ${message}`,
      })
    } finally {
      setFs16SourceOpenBusy(false)
    }
  }

  const handleCloseFs16SourceFile = async () => {
    if (!fs16SourceOpened) {
      notifications.show({
        title: '当前没有打开的源文件',
        message: '请先打开源 .smu 文件，再退出编辑状态。',
        color: 'yellow',
        icon: <IconAlertTriangle size={18} />,
      })
      return
    }

    setFs16SourceCloseBusy(true)

    const send = async (command: string, timeoutMs: number) => {
      const result = await sendInstrumentScpiCommand('channelEmulator', {
        command,
        timeout_ms: timeoutMs,
        run_by: runBy || undefined,
      })
      if (!result.success) {
        throw new Error(`${command}: ${getScpiResultDetail(result)}`)
      }
      return result
    }

    try {
      await send('DIAG:SIMU:CLOSE', 30000)
      await send('*OPC?', 30000)
      const err = await send('SYST:ERR?', 10000)
      const errText = getScpiResultDetail(err).trim()
      if (errText && !/^0(\b|,)/.test(errText)) {
        throw new Error(`SYST:ERR? returned ${errText}`)
      }

      let stateText = ''
      try {
        const state = await send('DIAG:SIMU:STATE?', 10000)
        stateText = getScpiResultDetail(state)
      } catch {
        stateText = ''
      }

      const detail = stateText
        ? `已退出编辑状态，FS16 状态: ${stateText}`
        : '已退出源文件编辑状态'
      setFs16SourceOpened(false)
      setFs16SourceOpenDetail(detail)
      setFs16AddActiveStep(1)
      setParamValues((prev) => ({ ...prev, source_already_opened: false }))
      notifications.show({
        title: '已退出编辑',
        message: detail,
        color: 'green',
        icon: <IconLogout size={18} />,
      })
      logFrontendEvent({
        action: 'fs16_add_emulation.close_source',
        component: 'SequenceRunnerPanel',
        message: `source=${fs16SourceFile} state=${stateText || '-'}`,
      })
    } catch (e: unknown) {
      const message = (e as Error)?.message || String(e)
      setFs16SourceOpenDetail(message)
      notifications.show({
        title: '退出编辑失败',
        message,
        color: 'red',
        icon: <IconX size={18} />,
      })
      logFrontendEvent({
        level: 'ERROR',
        action: 'fs16_add_emulation.close_source_failed',
        component: 'SequenceRunnerPanel',
        error: `source=${fs16SourceFile} ${message}`,
      })
    } finally {
      setFs16SourceCloseBusy(false)
    }
  }

  const renderParamField = (
    spec: DiagnosticSequenceMetadata['params_schema'][number],
    disabled = false,
  ) => {
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
          disabled={disabled}
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
          disabled={disabled}
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
          disabled={disabled}
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
        disabled={disabled}
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

  const renderFs16AddEmulationParams = () => {
    const specByName = new Map(
      (selectedSequence?.params_schema ?? []).map((spec) => [spec.name, spec]),
    )
    const sourceSpecs = ['source_smu_file', 'verify_source_file_exists']
      .map((name) => specByName.get(name))
      .filter((spec): spec is DiagnosticSequenceMetadata['params_schema'][number] => Boolean(spec))
    return (
      <Stack gap="md">
        <Stack gap="sm">
          <Group justify="space-between" align="center" wrap="wrap">
            <Divider
              label="源文件打开"
              labelPosition="left"
              style={{ flex: 1, minWidth: 220 }}
            />
            <Badge
              color={fs16SourceOpened ? 'green' : fs16SourceOpenDetail ? 'red' : 'gray'}
              variant={fs16SourceOpened ? 'filled' : 'light'}
            >
              {fs16SourceOpened ? '已打开' : fs16SourceOpenDetail ? '打开失败' : '未打开'}
            </Badge>
          </Group>
          <SimpleGrid
            cols={{ base: 1, sm: 2, lg: 3, xl: 4 }}
            spacing="md"
            verticalSpacing="sm"
          >
            {sourceSpecs.map((spec) => renderParamField(spec, fs16SourceOpenBusy))}
          </SimpleGrid>
          <Group justify="space-between" align="center" wrap="wrap">
            <Text size="xs" c={fs16SourceOpened ? 'green' : fs16SourceOpenDetail ? 'red' : 'dimmed'}>
              {fs16SourceOpenDetail || '先打开已有 .smu，FS16 UI 进入 Step 1 后再配置参数。'}
            </Text>
            <Group gap="xs">
              <Button
                leftSection={<IconFolderOpen size={16} />}
                onClick={handleOpenFs16SourceFile}
                disabled={!fs16SourceFile || fs16SourceOpenBusy || fs16SourceCloseBusy}
                loading={fs16SourceOpenBusy}
              >
                打开源文件
              </Button>
              <Button
                leftSection={<IconLogout size={16} />}
                variant="light"
                color="gray"
                onClick={handleCloseFs16SourceFile}
                disabled={!fs16SourceOpened || fs16SourceOpenBusy || fs16SourceCloseBusy}
                loading={fs16SourceCloseBusy}
              >
                退出编辑
              </Button>
            </Group>
          </Group>
        </Stack>

        {FS16_ADD_EMULATION_PARAM_GROUPS.map((group) => {
          const specs = group.names
            .map((name) => specByName.get(name))
            .filter((spec): spec is DiagnosticSequenceMetadata['params_schema'][number] => Boolean(spec))
          if (specs.length === 0) return null
          const isActive = group.step === fs16AddActiveStep
          const isComplete = group.step < fs16AddActiveStep
          const disabled = !fs16SourceOpened || !isActive
          const statusLabel = !fs16SourceOpened
            ? '等待源文件'
            : isActive
              ? '当前'
              : isComplete
                ? '已配置'
                : '锁定'
          return (
            <Stack key={group.title} gap="sm">
              <Group justify="space-between" align="center" wrap="wrap">
                <Divider
                  label={group.title}
                  labelPosition="left"
                  style={{ flex: 1, minWidth: 220 }}
                />
                <Badge
                  color={!fs16SourceOpened ? 'gray' : isActive ? 'blue' : isComplete ? 'green' : 'gray'}
                  variant={fs16SourceOpened && isActive ? 'filled' : 'light'}
                >
                  {statusLabel}
                </Badge>
              </Group>
              <SimpleGrid
                cols={{ base: 1, sm: 2, lg: 3, xl: 4 }}
                spacing="md"
                verticalSpacing="sm"
                style={{ opacity: fs16SourceOpened && isActive ? 1 : 0.56 }}
              >
                {specs.map((spec) => renderParamField(spec, disabled))}
              </SimpleGrid>
            </Stack>
          )
        })}
        <Group justify="space-between" align="center" wrap="wrap">
          <Badge variant="light" color="blue">
            Step {fs16AddActiveStep}/{FS16_ADD_EMULATION_TOTAL_STEPS}
          </Badge>
          <Group gap="xs">
            <Button
              variant="light"
              disabled={!fs16SourceOpened || fs16AddActiveStep <= 1}
              onClick={() => setFs16AddActiveStep((step) => Math.max(1, step - 1))}
            >
              上一步
            </Button>
            <Button
              disabled={!fs16SourceOpened || fs16AddActiveStep >= FS16_ADD_EMULATION_TOTAL_STEPS}
              onClick={() =>
                setFs16AddActiveStep((step) =>
                  Math.min(FS16_ADD_EMULATION_TOTAL_STEPS, step + 1),
                )
              }
            >
              下一步
            </Button>
          </Group>
        </Group>
      </Stack>
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
              {isFs16AddEmulation ? (
                renderFs16AddEmulationParams()
              ) : (
                <Stack gap="md">
                  {selectedParamGroups.file.length > 0 && (
                    <Stack gap={6}>
                      <Text size="xs" fw={700} c="dimmed">文件</Text>
                      <SimpleGrid cols={1} spacing="md">
                        {selectedParamGroups.file.map((spec) => renderParamField(spec))}
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
                        {selectedParamGroups.switches.map((spec) => renderParamField(spec))}
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
                        {selectedParamGroups.other.map((spec) => renderParamField(spec))}
                      </SimpleGrid>
                    </Stack>
                  )}
                </Stack>
              )}
            </>
          )}

          <TextInput
            label="操作员"
            placeholder="工号 / 姓名 (审计行)"
            value={runBy}
            onChange={(e) => setRunBy(e.currentTarget.value)}
          />

          <Group justify="space-between" align="center" wrap="wrap">
            {showFs16PlaybackControls ? (
              <Group gap="xs" wrap="wrap">
                <Text size="xs" fw={700} c="dimmed">FS16 回放控制</Text>
                {FS16_PLAYBACK_CONTROLS.map((control) => {
                  const ControlIcon = control.icon
                  return (
                    <Button
                      key={control.key}
                      size="sm"
                      variant="light"
                      color={control.color}
                      leftSection={<ControlIcon size={16} />}
                      onClick={() => handleFs16PlaybackControl(control)}
                      disabled={Boolean(fs16ControlBusy)}
                      loading={fs16ControlBusy === control.key}
                    >
                      {control.label}
                    </Button>
                  )
                })}
              </Group>
            ) : <span />}
            <Button
              leftSection={<IconPlayerPlay size={16} />}
              onClick={handleRun}
              disabled={!selectedKey || running || !fs16AddCanRun}
              loading={running}
            >
              运行序列
            </Button>
          </Group>
        </Stack>
      </Paper>

      {running && selectedKey === 'uxm_rf_app_max_dl_throughput' && (
        <Paper p="md" withBorder>
          <Stack gap="sm">
            <Group justify="space-between" align="center">
              <Group gap="xs">
                <Loader size="sm" />
                <Title order={5}>RF App DL 吞吐实时采样</Title>
              </Group>
              {liveUxmSamples.length > 0 && (
                <Badge color="blue" variant="light">
                  {liveUxmSamples.at(-1)?.index}/{liveUxmSamples.at(-1)?.total}
                </Badge>
              )}
            </Group>
            {liveUxmSamples.length === 0 ? (
              <Text size="sm" c="dimmed">
                正在等待仪表启动和第一条 BTPut/TMONitor 样本……
              </Text>
            ) : (
              <>
                <Group gap="md" wrap="wrap">
                  <Paper p="sm" withBorder>
                    <Text size="xs" c="dimmed">当前 DL</Text>
                    <Text size="xl" fw={700}>
                      {liveUxmSamples.at(-1)?.throughput?.toFixed(2) ?? '-'} Mbps
                    </Text>
                  </Paper>
                  <Paper p="sm" withBorder>
                    <Text size="xs" c="dimmed">当前窗口 BLER</Text>
                    <Text size="xl" fw={700}>
                      {formatBlerPercent(liveUxmSamples.at(-1)?.bler)}
                    </Text>
                  </Paper>
                  <Alert color="blue" variant="light">
                    实时值仅用于观察，不设吞吐或 BLER 合格门限。
                  </Alert>
                </Group>
                <Table.ScrollContainer minWidth={560}>
                  <Table striped withTableBorder withColumnBorders>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>样本</Table.Th>
                        <Table.Th>DL Mbps</Table.Th>
                        <Table.Th>BLER</Table.Th>
                        <Table.Th>来源</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {liveUxmSamples.slice(-12).map((sample) => (
                        <Table.Tr key={sample.index}>
                          <Table.Td>{sample.index}/{sample.total}</Table.Td>
                          <Table.Td>
                            {sample.throughput === null ? '-' : sample.throughput.toFixed(3)}
                          </Table.Td>
                          <Table.Td>{formatBlerPercent(sample.bler)}</Table.Td>
                          <Table.Td>
                            <Badge size="xs" variant="light">{sample.source}</Badge>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              </>
            )}
          </Stack>
        </Paper>
      )}

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
                {resultSource?.type === 'history' && (
                  <Badge color={resultSource.structured ? 'indigo' : 'yellow'} variant="light">
                    历史记录 {new Date(resultSource.runAt).toLocaleString()}
                    {resultSource.structured ? '' : ' · 仅摘要'}
                  </Badge>
                )}
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
              {resultUxmRfAppDl && (
                <>
                  <Alert
                    color="blue"
                    icon={<IconAlertCircle size={18} />}
                    title="RF App 最大DL吞吐 · 信息性结果"
                  >
                    本序列不设置吞吐量或 BLER 通过门限。高 BLER、低吞吐和波动只记录；
                    success/failure 仅表示启动、真实采样、停止及 SCPI 错误检查是否完成。
                  </Alert>
                  <Group gap="xs" wrap="wrap">
                    <Badge color="indigo" variant="light">
                      App {String(resultUxmRfAppDl.instrument?.app_name || 'IRAT_LITE')}
                    </Badge>
                    <Badge color="blue" variant="light">
                      Cell {String(resultUxmRfAppDl.cellConfig?.cell || 'CELL1')}
                    </Badge>
                    <Badge color="cyan" variant="light">
                      Band {String(resultUxmRfAppDl.cellConfig?.band || '-')}
                    </Badge>
                    <Badge color="cyan" variant="light">
                      ARFCN {String(resultUxmRfAppDl.cellConfig?.dl_arfcn ?? '-')}
                    </Badge>
                    <Badge color="cyan" variant="light">
                      BW {String(resultUxmRfAppDl.cellConfig?.dl_bandwidth || '-')}
                    </Badge>
                    <Badge color="cyan" variant="light">
                      Power {String(resultUxmRfAppDl.cellConfig?.dl_power_dbm_per_bw ?? '-')} dBm/BW
                    </Badge>
                    <Badge
                      color={resultUxmRfAppDl.cleanup?.stopped ? 'green' : 'red'}
                      variant="light"
                    >
                      BTPut {resultUxmRfAppDl.cleanup?.stopped ? '已停止' : '停止失败/未执行'}
                    </Badge>
                  </Group>
                  <Divider label="DL 吞吐 / BLER 时间序列" labelPosition="left" />
                  {resultUxmRfAppDl.samples.length === 0 ? (
                    <Text size="sm" c="dimmed">没有保存到原始样本。</Text>
                  ) : (
                    <Table.ScrollContainer minWidth={1120}>
                      <Table striped highlightOnHover withTableBorder withColumnBorders>
                        <Table.Thead>
                          <Table.Tr>
                            <Table.Th>#</Table.Th>
                            <Table.Th>时间</Table.Th>
                            <Table.Th>DL Mbps</Table.Th>
                            <Table.Th>DL BLER</Table.Th>
                            <Table.Th>来源</Table.Th>
                            <Table.Th>Progress</Table.Th>
                            <Table.Th>TMON Peak</Table.Th>
                            <Table.Th>仪表原始返回</Table.Th>
                          </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                          {resultUxmRfAppDl.samples.map((sample) => (
                            <Table.Tr key={`${sample.sampleIndex}-${sample.timestamp}`}>
                              <Table.Td>{sample.sampleIndex}</Table.Td>
                              <Table.Td>
                                <Text size="xs" style={{ whiteSpace: 'nowrap' }}>
                                  {sample.timestamp
                                    ? new Date(sample.timestamp).toLocaleTimeString()
                                    : '-'}
                                </Text>
                              </Table.Td>
                              <Table.Td>
                                <Text size="sm" fw={600} c={sample.valid ? undefined : 'dimmed'}>
                                  {sample.throughput === null ? '-' : sample.throughput.toFixed(2)}
                                </Text>
                              </Table.Td>
                              <Table.Td>{formatBlerPercent(sample.bler)}</Table.Td>
                              <Table.Td>
                                <Badge
                                  size="xs"
                                  color={sample.source === 'btput' ? 'blue' : sample.source === 'tmonitor' ? 'cyan' : 'gray'}
                                  variant="light"
                                >
                                  {sample.source}
                                </Badge>
                              </Table.Td>
                              <Table.Td>{sample.progressCount ?? '-'}</Table.Td>
                              <Table.Td>
                                {sample.tmonitorPeak === null ? '-' : `${sample.tmonitorPeak.toFixed(2)} Mbps`}
                              </Table.Td>
                              <Table.Td>
                                <Code block style={{ fontSize: 10, minWidth: 300 }}>
                                  {`BTPut: ${sample.rawBtput || '-'}\nTMON: ${sample.rawTmonitor || '-'}`}
                                </Code>
                              </Table.Td>
                            </Table.Tr>
                          ))}
                        </Table.Tbody>
                      </Table>
                    </Table.ScrollContainer>
                  )}
                </>
              )}
              {resultFs16AddEmulation && (
                <>
                  <Divider label="FS16 add emulation" labelPosition="left" />
                  {resultFs16AddEmulationRows.length > 0 && (
                    <Table.ScrollContainer minWidth={520}>
                      <Table withTableBorder withColumnBorders striped>
                        <Table.Tbody>
                          {resultFs16AddEmulationRows.map((row) => (
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
                  )}

                  {resultFs16AddEmulationWizardSteps.length > 0 && (
                    <Stack gap={4}>
                      <Text size="xs" fw={700} c="dimmed">Wizard steps</Text>
                      {resultFs16AddEmulationWizardSteps.map((step) => (
                        <Group
                          key={`${step.step}-${step.label}`}
                          gap="xs"
                          wrap="nowrap"
                          align="flex-start"
                        >
                          <Badge
                            color={step.success ? 'green' : 'red'}
                            size="sm"
                            variant="filled"
                            style={{ flexShrink: 0 }}
                          >
                            {step.step ? `S${step.step}` : step.success ? '✓' : '✗'}
                          </Badge>
                          <Text size="xs" fw={500} style={{ flexShrink: 0 }}>
                            {step.label}
                          </Text>
                          <Text size="xs" c="dimmed" style={{ wordBreak: 'break-all' }}>
                            {step.detail}
                          </Text>
                          {step.duration_ms !== null && (
                            <Text size="xs" c="dimmed" ml="auto">{step.duration_ms} ms</Text>
                          )}
                        </Group>
                      ))}
                    </Stack>
                  )}

                  {resultFs16AddEmulationScpi.length > 0 && (
                    <>
                      <Text size="xs" fw={700} c="dimmed">Applied SCPI summary</Text>
                      <ScrollArea h={120}>
                        <Code block style={{ fontSize: 12 }}>
                          {resultFs16AddEmulationScpi.join('\n')}
                        </Code>
                      </ScrollArea>
                    </>
                  )}

                  {resultFs16AddEmulationUnsupported.length > 0 && (
                    <Alert color="yellow" icon={<IconAlertTriangle size={18} />} title="v1 boundaries">
                      <Stack gap={2}>
                        {resultFs16AddEmulationUnsupported.map((item) => (
                          <Text key={item} size="xs">{item}</Text>
                        ))}
                      </Stack>
                    </Alert>
                  )}
                </>
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
                    {resultUxmRfAppDl
                      ? '以上统计仅用于记录现场链路表现，不参与控制流程的成功判定；BLER按比例值统计，时间序列表中换算为百分比。'
                      : '当前 hybrid smoke 的终端通信性能指标来自 mock BS/DUT 或所选 BS driver 的 KPI surface；FS16 负责真实 .smu playback 控制链路。'}
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
              {resultSource?.type === 'history' && !resultSource.structured && (
                <Alert color="yellow" icon={<IconAlertTriangle size={18} />} title="旧历史记录缺少结构化明细">
                  这条记录是在完整结果持久化功能加入前生成的，只能恢复 summary / log / steps；
                  新运行的记录会保存 KPI summary、FS16 playback 和 real/mock 来源信息。
                </Alert>
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
                <UnstyledButton
                  key={r.id}
                  onClick={() => handleRestoreRecentRun(r)}
                  disabled={Boolean(restoringRunId)}
                  aria-label={`恢复历史运行 ${r.target_name}`}
                  style={{
                    width: '100%',
                    borderRadius: 6,
                    padding: '2px 4px',
                    cursor: restoringRunId ? 'wait' : 'pointer',
                  }}
                >
                  <Group gap="xs" wrap="nowrap">
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
                    {restoringRunId === r.id ? (
                      <Loader size="xs" ml="auto" />
                    ) : r.run_by ? (
                      <Text size="xs" c="dimmed" ml="auto">@ {r.run_by}</Text>
                    ) : (
                      <Text size="xs" c="dimmed" ml="auto">点击恢复</Text>
                    )}
                  </Group>
                </UnstyledButton>
              ))}
            </Stack>
          </ScrollArea>
        )}
      </Paper>
    </Stack>
  )
}
