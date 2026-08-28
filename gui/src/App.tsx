import {
  useMemo,
  useState,
  useEffect,
  useRef,
  useCallback,
  type Dispatch,
  type SetStateAction,
  type ChangeEvent,
  type FormEvent,
  type DragEvent,
} from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AppShell,
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Checkbox,
  Divider,
  FileButton,
  Group,
  NumberInput,
  Paper,
  Flex,
  Timeline,
  Modal,
  Drawer,
  MultiSelect,
  Select,
  ScrollArea,
  SimpleGrid,
  Grid,
  SegmentedControl,
  Slider,
  Stack,
  Switch,
  Table,
  Text,
  Tooltip,
  TextInput,
  Textarea,
  JsonInput,
  Title,
  useMantineTheme,
  UnstyledButton,
  useMantineColorScheme,
  useComputedColorScheme,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import './App.css'
import ProbeLayoutView from './components/ProbeLayoutView'
import { SystemCalibration } from './components/SystemCalibration'
import { TestManagement } from './features/TestManagement/TestManagement'
import { ReportsPage } from './features/Reports/pages/ReportsPage'
import { CommissioningSandbox } from './components/Commissioning'
import { DiagnosticsPage } from './features/Diagnostics/DiagnosticsPage'
import { DashboardCockpit } from './features/Dashboard'
import { formatBaseStationSyncTruth } from './features/Dashboard/baseStationBindingTruth'
import { TopologyEditor } from './features/TopologyEditor/TopologyEditor'
import { TopologyProfileEditor } from './features/TopologyProfileEditor'
import { LabProfileWizard } from './components/LabProfile/LabProfileWizard'
import { OperationalLabSelector, useOperationalLab } from './features/OperationalLab'
import { AssetProfilesPanel } from './components/AssetProfiles/AssetProfilesPanel'
import { ChannelWorkbench } from './features/ChannelWorkbench/ChannelWorkbench'
import {
  fetchLabProfiles,
  syncCurrentInstrumentBinding,
} from './api/labProfileService'
import { ExecutionMetricsCard } from './features/Monitoring'
import ChartsDemoPage from './components/Charts/ChartsDemoPage'
import { ChamberConfigCard } from './components/ChamberConfigCard'
import { StandardChannelDefinitionCard } from './components/StandardChannelDefinitionCard'
import {
  createProbe,
  deleteProbe,
  fetchDemoRunPlan,
  fetchProbes,
  fetchChamber,
  fetchActiveChamber,
  fetchTestCaseDetail,
  fetchInstrumentCatalog,
  fetchChannelModels,
  addChannelModel,
  removeChannelModel,
  fetchTopologyProfiles,
  selectTopologyProfile,
  deleteTopologyProfile,
  duplicateTopologyProfile,
  type TopologyProfileDetail,
  deleteTestCase,
  updateInstrumentCategory,
  certifyBaseStationSite,
  revokeBaseStationSiteCertification,
  replaceProbes,
  updateProbe,
} from './api/service'
import client from './api/client'
import { listDiagnosticRuns, type DiagnosticRunSummary } from './api/diagnosticService'
import {
  buildDiagnosticTarget,
  diagnosticErrorMessage,
} from './features/Equipment/diagnosticTarget'
import type {
  DemoRunPlan,
  DemoRunResult,
  InstrumentsResponse,
  InstrumentStatus,
  MetricItem,
  Probe as ProbeType,
  SequenceStep as SequenceStepType,
  UpdateProbePayload,
  UpdateInstrumentPayload,
} from './types/api'
import {
  buildBaseStationAdapterProfile,
  emptyBaseStationProfileDraft,
  readBaseStationProfileDraft,
  type BaseStationProfileDraft,
} from './types/baseStationManifest'

const hexToRgba = (hex: string, alpha: number) => {
  const sanitized = hex.replace('#', '')
  const parse = (value: string) => Number.parseInt(value, 16)
  if (sanitized.length === 3) {
    const r = parse(sanitized[0] + sanitized[0])
    const g = parse(sanitized[1] + sanitized[1])
    const b = parse(sanitized[2] + sanitized[2])
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  const r = parse(sanitized.slice(0, 2))
  const g = parse(sanitized.slice(2, 4))
  const b = parse(sanitized.slice(4, 6))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

type SectionKey = 'dashboard' | 'equipment' | 'probeManager' | 'topologyEditor' | 'assetProfiles' | 'channelWorkbench' | 'testManagement' | 'results' | 'systemCalibration' | 'commissioning' | 'diagnostics' | 'chartsDemo'

type ProbeFormState = Pick<ProbeType, 'ring' | 'polarization' | 'position' | 'is_active'>

// ==================== 探头坐标系工具函数 ====================

/** 环层配置：基于仰角划分 */
const RING_CONFIG = [
  { ring: 1, label: '顶层 Ring-1', minElevation: 60, maxElevation: 90, centerElevation: 75 },
  { ring: 2, label: '上层 Ring-2', minElevation: 30, maxElevation: 60, centerElevation: 45 },
  { ring: 3, label: '中层 Ring-3', minElevation: -30, maxElevation: 30, centerElevation: 0 },
  { ring: 4, label: '下层 Ring-4', minElevation: -60, maxElevation: -30, centerElevation: -45 },
  { ring: 5, label: '底层 Ring-5', minElevation: -90, maxElevation: -60, centerElevation: -75 },
] as const

/** 根据仰角自动计算环层 */
function getRingFromElevation(elevation: number): number {
  for (const config of RING_CONFIG) {
    if (elevation > config.minElevation && elevation <= config.maxElevation) {
      return config.ring
    }
  }
  // 边界情况
  if (elevation >= 60) return 1
  if (elevation <= -60) return 5
  return 3
}

/** 获取环层的中心仰角（用于快速编辑） */
function getCenterElevationForRing(ring: number): number {
  const config = RING_CONFIG.find(c => c.ring === ring)
  return config?.centerElevation ?? 0
}

/** 计算派生值：高度和水平半径 */
function calculateDerivedValues(position: { azimuth: number; elevation: number; radius: number }) {
  const elevationRad = (position.elevation * Math.PI) / 180
  const height = position.radius * Math.sin(elevationRad) // z = r * sin(φ)
  const horizontalRadius = position.radius * Math.cos(elevationRad) // ρ = r * cos(φ)
  return {
    height: Number(height.toFixed(3)),
    horizontalRadius: Number(horizontalRadius.toFixed(3)),
  }
}

/** 获取环层显示标签 */
function getRingLabel(ring: number): string {
  const config = RING_CONFIG.find(c => c.ring === ring)
  return config?.label ?? `Ring-${ring}`
}

// ==================== 日志和其他类型 ====================

type LogEntry = {
  id: string
  timestamp: string
  level: 'INFO' | 'WARN' | 'DEBUG'
  message: string
}

type LogLevel = LogEntry['level']

type RunMetadata = {
  runName: string
  artifactPrefix: string
  caseName?: string
}


type EquipmentDraft = {
  modelId: string
  endpoint: string
  controller: string
  notes: string
  connection_params?: string
  base_station_profile?: BaseStationProfileDraft
}

type EquipmentFeedback = {
  type: 'success' | 'error'
  message: string
}

type EquipmentMutationVariables = {
  categoryKey: string
  payload: UpdateInstrumentPayload
}

type DemoRunStatus = 'idle' | 'running' | 'completed' | 'paused'

type DemoRunProgress = {
  status: DemoRunStatus
  currentStepIndex: number
  eventIndex: number
  startedAt: number | null
  finishedAt: number | null
}

// P3 Phase 4: sidebar groups. Items with the same `group` cluster under one
// header in the rendered nav. `group` is omitted for the main flow so the
// default appearance stays unchanged.
type SectionGroup = '调试维护' | '其他'

const sections: Array<{
  key: SectionKey
  label: string
  description: string
  group?: SectionGroup
}> = [
  {
    key: 'dashboard',
    label: '主控台',
    description: '系统总览、实时监控、执行控制与日志——一站式操作中心。',
  },
  {
    key: 'equipment',
    label: '仪器资源配置',
    description: '统一管理基站仿真器、信道仿真器、VNA等仪表选型与连接参数。',
  },
  {
    key: 'probeManager',
    label: '探头与暗室配置',
    description: '维护探头阵列、暗室几何与校准基线，支撑软件定义静区。',
  },
  {
    key: 'topologyEditor',
    label: '射频拓扑编辑器',
    description: '通过拖拽设计和查看基于 RF Switch 的端到端信号物理链路与校准路径。',
  },
  {
    key: 'assetProfiles',
    label: 'DUT 与 SIM 卡',
    description: '统一维护被测设备 (DUT) 能力声明与测试卡池 (SIM/eSIM 身份 + 鉴权)，分 Tab 管理，供测试例选用与防插错卡预检。',
  },
  {
    key: 'channelWorkbench',
    label: '信道工作台',
    description: '统一管理多态信道资产 (ChannelAsset)：标准 3GPP / 自定义 CDL / RT 动态 / 厂商文件四源，供测试例按 source_type 引用注入。',
  },
  {
    key: 'testManagement',
    label: '测试管理',
    description: '以测试用例为基础的测试管理：用例库（配仪表参数 / 直接执行）、执行历史、虚拟路测。',
  },
  {
    key: 'results',
    label: '数据归档与报告',
    description: '浏览历史记录、对比结果，并一键生成标准化报告。',
  },
  {
    key: 'systemCalibration',
    label: '系统校准',
    description: '执行TRP/TIS校准、重复性测试、实验室间比对，管理校准证书与溯源。',
  },
  {
    key: 'commissioning',
    label: '暗室首测',
    description: '3GPP Static MIMO OTA 调试专区 - 基于 UMa CDL-C 模型与 CTIA 门限。现场调试用。',
    group: '调试维护',
  },
  {
    key: 'diagnostics',
    label: '调试序列 + 单阶段',
    description: 'SCPI 硬编码序列 + commissioning 单阶段 ad-hoc + HAL trace。workshop tier, 不进 TestPlan。',
    group: '调试维护',
  },
  {
    key: 'chartsDemo',
    label: '📊 高级图表演示',
    description: '展示 Plotly.js 交互式图表：时间序列分析、统计对比、性能基准等。',
    group: '其他',
  },
]

const instrumentStatusColor: Record<InstrumentStatus, string> = {
  available: 'green',
  reserved: 'yellow',
  maintenance: 'orange',
  offline: 'gray',
  pending_dev: 'red',
}

// Operator-facing label per status. 'pending_dev' is the only one that
// surfaces a model "exists in catalog but no HAL driver" — must read
// loud enough that no one picks it expecting real signaling.
const instrumentStatusLabel: Record<InstrumentStatus, string> = {
  available: '可用',
  reserved: '已预约',
  maintenance: '维护中',
  offline: '离线',
  pending_dev: '驱动未实现',
}

const logLevelColor: Record<LogLevel, string> = {
  INFO: 'blue',
  WARN: 'yellow',
  DEBUG: 'gray',
}

const initialLogs: LogEntry[] = [
  {
    id: 'log-1',
    timestamp: '10:30:12',
    level: 'INFO',
    message: '静区幅度波纹校验完成，结果 0.9 dB。',
  },
  {
    id: 'log-2',
    timestamp: '10:30:18',
    level: 'DEBUG',
    message: '探头#17 反馈延迟 4.1 ns，已在模型中补偿。',
  },
  {
    id: 'log-3',
    timestamp: '10:30:24',
    level: 'WARN',
    message: '放大器 A 通道温度 71°C，接近阈值。',
  },
]

const generateProbeId = (existing: ProbeType[]) => {
  const used = new Set(existing.map((item) => item.id))
  let index = existing.length + 1
  let candidate = ''
  do {
    candidate = `P-${String(index).padStart(2, '0')}`
    index += 1
  } while (used.has(candidate))
  return candidate
}

function App() {
  const theme = useMantineTheme()
  const queryClient = useQueryClient()
  const { setColorScheme } = useMantineColorScheme()
  const colorScheme = useComputedColorScheme('light', { getInitialValueInEffect: true })
  const isDark = colorScheme === 'dark'
  const toggleColorScheme = useCallback(() => {
    setColorScheme(isDark ? 'light' : 'dark')
  }, [isDark, setColorScheme])

  const [activeSection, setActiveSection] = useState<SectionKey>('dashboard')
  // P1-39: 执行历史「查看日志」→ 切到报告页并预填日志过滤。
  // ⚠ 存的是**完整 execution_id**, 不是给人看的短标签 —— 过滤要全长。
  const [pendingLogExecutionId, setPendingLogExecutionId] = useState<string | null>(null)
  const [logEntries, setLogEntries] = useState<LogEntry[]>(initialLogs)
  const [selectedResultIds, setSelectedResultIds] = useState<string[]>([])
  const timelineTimerRef = useRef<number | null>(null)
  const timelinePointerRef = useRef<number>(-1)
  const demoRunStatusRef = useRef<DemoRunStatus>('idle')
  const { data: demoRunPlanData } = useQuery({
    queryKey: ['tests', 'demo-run'],
    queryFn: fetchDemoRunPlan,
    enabled: false, // Temporarily disabled until backend endpoint is implemented
    retry: false,
  })
  const [demoRunProgress, setDemoRunProgress] = useState<DemoRunProgress>({
    status: 'idle',
    currentStepIndex: -1,
    eventIndex: -1,
    startedAt: null,
    finishedAt: null,
  })
  const [demoMetrics, setDemoMetrics] = useState<MetricItem[] | null>(null)
  const [demoResultCard, setDemoResultCard] = useState<DemoRunResult | null>(null)
  // ARCH-1 S4a: executingPlanInfo / executingPlanDetail / autoChainExecution /
  // liveHistory / syncPlanSummary / _mutatePlanStatus 六组随计划链删除。
  // 演示回放的直接入口(调试维护→监控)不依赖计划, 不受影响; 由 QueueTab 点
  // "执行"触发的那条计划链演示随 QueueTab 一并消失(有意)。
  // liveHistory 是演示时代的客户端内存历史, 它原本跟 apiEntries 合并渲染 ——
  // 去掉后历史视图只读 test_executions 权威源(ARCH-1 S2 换源), 不是损失。
  const [executingRunMeta, setExecutingRunMeta] = useState<RunMetadata | null>(null)
  const [lastRunMeta, setLastRunMeta] = useState<RunMetadata | null>(null)
  const sectionDescriptor = useMemo(
    () => sections.find((item) => item.key === activeSection),
    [activeSection],
  )

  const lastProgressStatusRef = useRef<DemoRunStatus>(demoRunProgress.status)

  // P0-2: first-run gate. If the DB has zero active LabProfiles the
  // operator can't do anything in the main UI (no lab → calibration /
  // measurement screens have nothing to operate on), so we show the
  // init wizard instead. We deliberately do NOT block on isLoading:
  // letting the rest of the app render briefly is preferable to a
  // blank loading screen on every startup; the gate kicks in as soon
  // as the query resolves.
  const labProfilesQuery = useQuery({
    queryKey: ['lab-profiles'],
    queryFn: () => fetchLabProfiles(true),
  })
  const needsLabProfileWizard =
    labProfilesQuery.data !== undefined && labProfilesQuery.data.length === 0

  const scheduleNextEvent = useCallback(() => {
    if (!demoRunPlanData?.plan) return
    if (demoRunStatusRef.current !== 'running') return
    const { timeline, steps } = demoRunPlanData.plan
    const nextIndex = timelinePointerRef.current + 1
    if (nextIndex >= timeline.length) {
      demoRunStatusRef.current = 'completed'
      setDemoRunProgress((prev) => ({
        ...prev,
        status: 'completed',
        currentStepIndex: steps.length - 1,
        eventIndex: timeline.length - 1,
        finishedAt: Date.now(),
      }))
      return
    }
    const prevOffset = nextIndex === 0 ? 0 : timeline[nextIndex - 1].offsetMs
    const delay = Math.max(timeline[nextIndex].offsetMs - prevOffset, 0)
    timelineTimerRef.current = window.setTimeout(() => {
      if (demoRunStatusRef.current !== 'running') return
      const event = timeline[nextIndex]
      timelinePointerRef.current = nextIndex
      const timestamp = new Date().toLocaleTimeString('zh-CN', { hour12: false })
      setLogEntries((prev) => {
        const entry: LogEntry = {
          id: `${event.id}-${Date.now()}`,
          timestamp,
          level: event.level,
          message: event.message,
        }
        const nextLogs = [...prev, entry]
        return nextLogs.slice(-40)
      })
      setDemoRunProgress((prev) => {
        const nextStepIndex =
          typeof event.stepIndex === 'number' ? event.stepIndex : prev.currentStepIndex
        const hasResult = Boolean(event.result)
        return {
          ...prev,
          status: hasResult ? 'completed' : prev.status,
          currentStepIndex: nextStepIndex,
          eventIndex: nextIndex,
          finishedAt: hasResult ? Date.now() : prev.finishedAt,
        }
      })
      if (event.metrics) {
        setDemoMetrics(event.metrics)
      }
      if (event.result) {
        setDemoResultCard(event.result)
        demoRunStatusRef.current = 'completed'
        return
      }
      scheduleNextEvent()
    }, delay)
  }, [demoRunPlanData, setLogEntries])

  // 常量 'mock' —— **与改动前逐位同行为**, 不是新判断。
  //
  // 原来是 `hardwareOnline && !preferMockExecution ? 'real' : 'mock'`, 而那条链
  // 整条是死的: `preferMockExecution` 初值 true, 唯一能改它的
  // `onExecutionModeChange` 只塞进了 payload、`<Monitoring/>` 的 props 从未接过它
  // ⇒ 表达式恒 false ⇒ 徽章恒 'mock'。`hardwareOnline` 取什么值都观察不到。
  // 本片删掉那条死链后按常量固定, 行为不变、不引入任何新失效面。
  //
  // ⚠️ **别顺手把它接到 readiness 上判"真仪表还是 mock"** —— 本片试过, 内审 F1
  //    否掉了: 这两个徽章挂在**演示回放播放器**上 (同卡片副标题原话:「演示回放 ——
  //    真实测试请到「测试管理 → 测试用例库」执行用例」), 它的数据源
  //    `/api/v1/tests/demo-run` 实测 404 且 query 带 `enabled:false`。按 HAL 真假
  //    去判, 现场全真部署时会把**演示脚本**标成绿色「真实执行」, 比恒 'mock' 更糟。
  //    要显示"系统当前跑真仪表还是 mock", 驾驶舱 `ZoneReadiness` 已在做。
  //    要恢复"操作员手选真/模拟"是独立功能 (先把开关接到 Monitoring), 已记 backlog。
  const executionMode: 'real' | 'mock' = 'mock'

  const handleDemoRunStart = useCallback(() => {
    if (!demoRunPlanData?.plan) return
    if (demoRunStatusRef.current === 'running') return
    if (timelineTimerRef.current !== null) {
      window.clearTimeout(timelineTimerRef.current)
      timelineTimerRef.current = null
    }
    timelinePointerRef.current = -1
    demoRunStatusRef.current = 'running'
    setDemoResultCard(null)
    setDemoMetrics(demoRunPlanData.plan.timeline[0]?.metrics ?? null)
    setLogEntries([])
    setDemoRunProgress({
      status: 'running',
      currentStepIndex: demoRunPlanData.plan.timeline[0]?.stepIndex ?? 0,
      eventIndex: -1,
      startedAt: Date.now(),
      finishedAt: null,
    })
    scheduleNextEvent()
  }, [demoRunPlanData, scheduleNextEvent])

  const handleDemoPause = useCallback(() => {
    // Stop the timer
    if (timelineTimerRef.current !== null) {
      window.clearTimeout(timelineTimerRef.current)
      timelineTimerRef.current = null
    }
    demoRunStatusRef.current = 'paused'
    setDemoRunProgress((prev) => ({ ...prev, status: 'paused' }))

  }, [])

  const handleDemoStop = useCallback(() => {
    // Stop the timer
    if (timelineTimerRef.current !== null) {
      window.clearTimeout(timelineTimerRef.current)
      timelineTimerRef.current = null
    }
    demoRunStatusRef.current = 'idle'
    setDemoRunProgress({
      status: 'idle',
      currentStepIndex: -1,
      eventIndex: -1,
      startedAt: null,
      finishedAt: Date.now(),
    })

    setExecutingRunMeta(null)
  }, [])

  // Resume a paused execution
  const handleDemoResume = useCallback(() => {
    demoRunStatusRef.current = 'running'
    setDemoRunProgress((prev) => ({ ...prev, status: 'running' }))

  }, [])

  // ARCH-1 S4a: startPlanExecution 与 execution:start 监听器随计划链删除。
  // 该事件的**唯一** emitter 是 QueueTab (本片已删); resume handler 里那处
  // emit 由 executingPlanInfo 守着, 而它只由本监听器写 —— 自环, QueueTab
  // 一删就永远进不去。演示回放的直接入口(调试维护→监控)不经过这条链。

  // ARCH-1 S4a: execution:pause / execution:stop 两个监听器同理删除 ——
  // emitter 只有 QueueTab (已删) 和 App 自己的计划分支 (已删)。

  useEffect(() => {
    if (lastProgressStatusRef.current === demoRunProgress.status) return
    lastProgressStatusRef.current = demoRunProgress.status
    if (demoRunProgress.status === 'completed') {
      // ARCH-1 S4a: 原先这里给计划打 complete、写 liveHistory、按
      // autoChainExecution 自动串下一个计划 —— 三件事都依赖 TestPlan, 随
      // 计划链删除。演示回放本身(进度/指标/结果卡)不受影响。
      if (executingRunMeta) {
        setLastRunMeta(executingRunMeta)
        setExecutingRunMeta(null)
      }
    }
    if (demoRunProgress.status === 'idle') {
      setExecutingRunMeta(null)
    }
  }, [
    demoRunProgress.status,
    demoRunProgress.finishedAt,
    executingRunMeta,
  ])

  useEffect(() => {
    return () => {
      if (timelineTimerRef.current !== null) {
        window.clearTimeout(timelineTimerRef.current)
      }
    }
  }, [])

  // ARCH-1 S4a: 这里原有一个"刷新后从执行队列回填正在跑的计划"的 effect,
  // 随计划链删除 —— 它读 /test-plans/queue, 唯一产出是 executingPlanInfo。
  // 用例执行的"正在跑"由 TestCaseLibrary 自己查 (fetchRunningExecution)。

  const sidebarBackground = isDark
    ? `linear-gradient(180deg, ${theme.colors.dark[7]} 0%, ${theme.colors.dark[8]} 100%)`
    : `linear-gradient(180deg, ${hexToRgba(theme.colors.brand[0], 0.95)} 0%, ${hexToRgba(theme.colors.brand[2], 0.6)} 100%)`
  const sidebarBorderColor = isDark ? theme.colors.dark[5] : hexToRgba(theme.colors.brand[4], 0.45)
  const headerBackground = isDark ? hexToRgba(theme.colors.dark[7], 0.85) : hexToRgba(theme.white, 0.9)
  const headerBorderColor = isDark ? theme.colors.dark[4] : hexToRgba(theme.colors.gray[3], 0.6)

  const handleResultToggle = useCallback((resultId: string) => {
    setSelectedResultIds((prev) =>
      prev.includes(resultId) ? prev.filter((id) => id !== resultId) : [...prev, resultId],
    )
  }, [])

  // P1-39: 一键跳日志。两件事一起做 —— 记下要过滤的执行、切到报告页。
  // 'results' 是报告页的 SectionKey（见 renderSection 的 case）。
  const handleViewExecutionLogs = useCallback((executionId: string) => {
    setPendingLogExecutionId(executionId)
    setActiveSection('results')
  }, [])
  // 内审 F1: **一次性交接** —— 消费完立刻清空。
  // 早前只设不清, 而 renderSection 只渲染当前 section(切走即卸载/切回即重挂),
  // 于是 effect 每次重挂都重跑: 此后整个会话里点「数据归档与报告」都会被弹到
  // 系统日志页签并重设过滤, 默认页签 'pending' 事实上再也进不去。
  const handlePendingLogConsumed = useCallback(() => setPendingLogExecutionId(null), [])

  const sectionContent = useMemo(
    () =>
      renderSection(activeSection, {
        logs: logEntries,
        setLogs: setLogEntries,
        selectedResults: selectedResultIds,
        selectedResultCount: selectedResultIds.length,
        onResultToggle: handleResultToggle,
        setActiveSection,
        pendingLogExecutionId,
        onViewExecutionLogs: handleViewExecutionLogs,
        onPendingLogConsumed: handlePendingLogConsumed,
        demoPlan: demoRunPlanData?.plan,
        demoProgress: demoRunProgress,
        onDemoStart: handleDemoRunStart,
        onDemoPause: handleDemoPause,
        onDemoResume: handleDemoResume,
        onDemoStop: handleDemoStop,
        demoMetrics,
        demoResult: demoResultCard,
        executionMode,
        executingRunMeta,
        recentRunMeta: executingRunMeta ?? lastRunMeta,
      }),
    [
      activeSection,
      logEntries,
      selectedResultIds,
      handleResultToggle,
      setActiveSection,
      pendingLogExecutionId,
      handleViewExecutionLogs,
      handlePendingLogConsumed,
      demoRunPlanData,
      demoRunProgress,
      handleDemoRunStart,
      handleDemoPause,
      handleDemoResume,
      handleDemoStop,
      demoMetrics,
      demoResultCard,
      executionMode,
      executingRunMeta,
      lastRunMeta,
    ],
  )

  // P0-2: render the wizard in place of AppShell if there are no
  // active LabProfiles. The wizard owns its own resumability state
  // and calls onComplete after a successful create OR explicit
  // cancel — both paths invalidate the gate query so this branch
  // flips automatically.
  if (needsLabProfileWizard) {
    return (
      <LabProfileWizard
        onComplete={() => {
          queryClient.invalidateQueries({ queryKey: ['lab-profiles'] })
        }}
      />
    )
  }

  return (
    <AppShell
      padding="xl"
      navbar={{
        width: 320,
        breakpoint: 'md',
      }}
      header={{ height: 84 }}
    >
      <AppShell.Navbar
        p="lg"
        style={{
          background: sidebarBackground,
          borderRight: `1px solid ${sidebarBorderColor}`,
          boxShadow: `inset -1px 0 0 ${isDark ? theme.colors.dark[6] : hexToRgba(theme.colors.brand[4], 0.18)}`,
        }}
      >
        <Stack h="100%" gap="lg">
          <Stack gap="lg" style={{ flex: 1, minHeight: 0 }}>
            <Paper
              withBorder
              radius="lg"
              p="md"
              style={{
                background: isDark ? hexToRgba(theme.white, 0.04) : hexToRgba(theme.white, 0.8),
                borderColor: isDark ? theme.colors.dark[4] : hexToRgba(theme.colors.brand[4], 0.4),
                boxShadow: theme.shadows.sm,
              }}
            >
              <Stack gap={6}>
                <Title order={4} c={isDark ? theme.white : theme.colors.brand[8]}>
                  Meta-3D
                </Title>
                <Text size="sm" c={isDark ? theme.colors.gray[4] : theme.colors.gray[7]}>
                  软件定义测试 · 虚拟路测
                </Text>
              </Stack>
            </Paper>

            <ScrollArea type="auto" style={{ flex: 1, minHeight: 0 }} scrollbarSize={12}>
              <Stack gap="sm" pt="xs" pb="sm">
                {sections.map((item, idx) => {
                  // P3 Phase 4: when entering a new sidebar group, emit a small
                  // header. Items without a `group` (default flow) skip it so
                  // the existing nav looks unchanged for the main sections.
                  const prevGroup = idx > 0 ? sections[idx - 1].group : undefined
                  const showGroupHeader = item.group !== undefined && item.group !== prevGroup
                  const active = item.key === activeSection
                  const cardBg = active
                    ? `linear-gradient(135deg, ${theme.colors.brand[5]} 0%, ${theme.colors.brand[7]} 100%)`
                    : hexToRgba(isDark ? theme.colors.dark[6] : theme.white, isDark ? 0.5 : 0.85)
                  const borderColor = active
                    ? theme.colors.brand[4]
                    : isDark
                      ? hexToRgba(theme.colors.dark[4], 0.8)
                      : hexToRgba(theme.colors.brand[4], 0.35)
                  return (
                    <Box key={item.key}>
                      {showGroupHeader && (
                        <Text
                          size="xs"
                          tt="uppercase"
                          fw={700}
                          c={isDark ? theme.colors.gray[5] : theme.colors.gray[6]}
                          mt={idx === 0 ? 0 : 'xs'}
                          mb={4}
                          style={{ letterSpacing: '0.08em', paddingLeft: 4 }}
                        >
                          {item.group}
                        </Text>
                      )}
                    <UnstyledButton
                      type="button"
                      onClick={() => setActiveSection(item.key)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          setActiveSection(item.key)
                        }
                      }}
                      role="tab"
                      aria-selected={active}
                      style={{
                        borderRadius: theme.radius.lg,
                        padding: '14px 16px',
                        background: cardBg,
                        border: `1px solid ${borderColor}`,
                        boxShadow: active ? theme.shadows.md : theme.shadows.xs,
                        color: active ? theme.white : undefined,
                        transition: 'transform 150ms ease, box-shadow 150ms ease, background 150ms ease',
                        transform: active ? 'translateY(-2px)' : 'none',
                      }}
                    >
                      <Stack gap={6}>
                        <Group gap="sm" align="center">
                          <Box
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: 999,
                              backgroundColor: active ? theme.white : theme.colors.brand[4],
                              boxShadow: active ? `0 0 8px ${hexToRgba(theme.white, 0.6)}` : 'none',
                            }}
                          />
                          <Text
                            fw={600}
                            size="sm"
                            c={active ? theme.white : isDark ? theme.colors.gray[2] : theme.colors.gray[8]}
                          >
                            {item.label}
                          </Text>
                        </Group>
                        <Text
                          size="xs"
                          c={active ? hexToRgba(theme.white, 0.75) : isDark ? theme.colors.gray[5] : theme.colors.gray[6]}
                        >
                          {item.description}
                        </Text>
                      </Stack>
                    </UnstyledButton>
                    </Box>
                  )
                })}
              </Stack>
            </ScrollArea>
          </Stack>

        </Stack>
      </AppShell.Navbar>

      <AppShell.Header
        px="xl"
        style={{
          background: headerBackground,
          backdropFilter: 'blur(12px)',
          borderBottom: `1px solid ${headerBorderColor}`,
        }}
      >
        <Group justify="space-between" h="100%">
          <Stack gap={4}>
            <Title order={2}>{sectionDescriptor?.label}</Title>
            <Text size="sm" c={isDark ? theme.colors.gray[4] : 'gray.6'}>
              {sectionDescriptor?.description}
            </Text>
          </Stack>
          <Group gap="sm">
            <OperationalLabSelector />
            <Tooltip label={isDark ? '切换至浅色模式' : '切换至深色模式'} position="bottom">
              <ActionIcon
                variant="light"
                color={isDark ? 'yellow' : 'brand'}
                radius="xl"
                size="lg"
                onClick={toggleColorScheme}
                aria-label={isDark ? '切换至浅色模式' : '切换至深色模式'}
              >
                {isDark ? '☀️' : '🌙'}
              </ActionIcon>
            </Tooltip>
            <Button variant="outline" color="gray" size="sm">
              保存草稿
            </Button>
            <Button color="brand" size="sm">
              新建任务
            </Button>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <ScrollArea h="100%">
          <Box className="workspace__content">{sectionContent}</Box>
        </ScrollArea>
      </AppShell.Main>
    </AppShell>
  )
}

type RenderPayload = {
  logs: LogEntry[]
  setLogs: Dispatch<SetStateAction<LogEntry[]>>
  selectedResults: string[]
  selectedResultCount: number
  onResultToggle: (id: string) => void
  setActiveSection: Dispatch<SetStateAction<SectionKey>>
  pendingLogExecutionId: string | null
  onViewExecutionLogs: (executionId: string) => void
  onPendingLogConsumed: () => void
  demoPlan?: DemoRunPlan
  demoProgress: DemoRunProgress
  onDemoStart: () => void
  onDemoPause: () => void
  onDemoStop: () => void
  onDemoResume: () => void
  demoMetrics: MetricItem[] | null
  demoResult: DemoRunResult | null
  executionMode: 'real' | 'mock'
  executingRunMeta: RunMetadata | null
  recentRunMeta: RunMetadata | null
}

function renderSection(section: SectionKey, payload: RenderPayload) {
  switch (section) {
    case 'dashboard':
      return (
        <DashboardCockpit
          onNavigateTestManagement={() => payload.setActiveSection('testManagement')}
        />
      )
    case 'equipment':
      return <EquipmentManager />
    case 'probeManager':
      return <ProbeManager onNavigate={payload.setActiveSection} />
    case 'topologyEditor':
      return <TopologyEditor />
    case 'assetProfiles':
      return <AssetProfilesPanel />
    case 'channelWorkbench':
      return <ChannelWorkbench />
    case 'testManagement':
      return <TestManagement onViewLogs={payload.onViewExecutionLogs} />
    case 'results':
      return (
        <ReportsPage
          pendingLogExecutionId={payload.pendingLogExecutionId}
          onPendingLogConsumed={payload.onPendingLogConsumed}
        />
      )
    case 'systemCalibration':
      return <SystemCalibration />
    case 'commissioning':
      return <CommissioningSandbox />
    case 'diagnostics':
      // P2-8: the legacy Monitoring 演示回放 player moved here from the old
      // dashboard case (developer / 调试 surface, not an operational view).
      return (
        <DiagnosticsPage
          monitoringSlot={
            <Monitoring
              logs={payload.logs}
              setLogs={payload.setLogs}
              scenarioStatus={payload.demoProgress.status}
              progress={payload.demoProgress}
              executionMode={payload.executionMode}
              demoPlan={payload.demoPlan}
              onRestart={payload.onDemoStart}
              onPause={payload.onDemoPause}
              onResume={payload.onDemoResume}
              onStop={payload.onDemoStop}
            />
          }
        />
      )
    case 'chartsDemo':
      return <ChartsDemoPage />
    default:
      return null
  }
}

// SCPI history query key — exported as a const so EquipmentManager handlers
// can invalidate the right key after each successful command send.
const scpiHistoryQueryKey = (categoryKey: string) => ['scpi-history', categoryKey] as const

function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  const now = Date.now()
  const diffSec = Math.max(0, Math.round((now - then) / 1000))
  if (diffSec < 60) return `${diffSec}秒前`
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}分钟前`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}小时前`
  return new Date(iso).toLocaleString()
}

function parseScpiHistoryRow(row: DiagnosticRunSummary, categoryKey: string): {
  command: string
  isBatch: boolean
  resultText: string
} {
  const probePrefix = `probe:${categoryKey}`
  const singlePrefix = `${categoryKey}: `
  if (row.target_name === probePrefix) {
    return {
      command: '🔍 诊断命令组 (5 条)',
      isBatch: true,
      resultText: row.success
        ? '全部通过'
        : (row.error_message ?? row.output_excerpt?.split('\n')[0] ?? '失败'),
    }
  }
  const command = row.target_name.startsWith(singlePrefix)
    ? row.target_name.slice(singlePrefix.length)
    : row.target_name
  const resultText = row.success
    ? (row.output_excerpt ?? '(OK, no response)')
    : (row.error_message ?? '失败')
  return { command, isBatch: false, resultText }
}

interface ScpiHistoryFeedProps {
  categoryKey: string
}

/**
 * Customer-facing SCPI history embedded in EquipmentManager.
 *
 * Differs from the developer-facing DiagnosticsPage audit feed: this view
 * is scoped to ONE instrument category, shows compact "command → result"
 * rows, and refreshes after each send. The customer is a field engineer
 * checking what they/colleagues have tried on this specific instrument.
 */
function ScpiHistoryFeed({ categoryKey }: ScpiHistoryFeedProps) {
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: scpiHistoryQueryKey(categoryKey),
    queryFn: () => listDiagnosticRuns({
      kind: 'scpi_command',
      target_contains: categoryKey,
      limit: 20,
    }),
    staleTime: 10_000,
  })
  const rows = data?.items ?? []

  return (
    <Stack gap={6}>
      <Group justify="space-between" align="center">
        <Text size="sm" fw={600} c="dimmed" style={{ fontFamily: 'monospace' }}>
          📜 历史命令 (最近 20 条, 跨会话持久化)
        </Text>
        <Button
          size="compact-xs"
          variant="subtle"
          color="gray"
          loading={isFetching && !isLoading}
          onClick={() => refetch()}
        >
          刷新
        </Button>
      </Group>

      {isLoading ? (
        <Text size="xs" c="dimmed">加载中…</Text>
      ) : rows.length === 0 ? (
        <Text size="xs" c="dimmed">暂无历史 — 发送一条命令即可记录。</Text>
      ) : (
        <Card withBorder padding="xs" radius="sm" bg="dark.9" style={{ maxHeight: 240, overflowY: 'auto' }}>
          <Stack gap={4}>
            {rows.map((row) => {
              const { command, isBatch, resultText } = parseScpiHistoryRow(row, categoryKey)
              return (
                <Group
                  key={row.id}
                  gap="xs"
                  wrap="nowrap"
                  align="flex-start"
                  style={{ fontFamily: 'monospace', fontSize: 12 }}
                >
                  <Text span c="dimmed" style={{ whiteSpace: 'nowrap', minWidth: 64 }}>
                    {formatRelativeTime(row.run_at)}
                  </Text>
                  <Text
                    span
                    c={isBatch ? 'yellow.4' : 'cyan'}
                    fw={600}
                    style={{ whiteSpace: 'nowrap', minWidth: 120 }}
                  >
                    {command}
                  </Text>
                  <Text
                    span
                    c={row.success ? 'green.4' : 'red.4'}
                    style={{ wordBreak: 'break-all', flex: 1 }}
                  >
                    {row.success ? '→ ' : '✗ '}{resultText}
                  </Text>
                  {row.run_by && (
                    <Text span c="dimmed" size="xs" style={{ whiteSpace: 'nowrap' }}>
                      @{row.run_by}
                    </Text>
                  )}
                </Group>
              )
            })}
          </Stack>
        </Card>
      )}
    </Stack>
  )
}

/**
 * P2-1 Phase 1: Topology profile selector for the UXM (baseStation) binding.
 *
 * UXM has two layers: Test App (SCPI command vocabulary, auto-detected at
 * connect) and Topology profile (cell/MIMO/power/FRC config WITHIN the
 * running Test App, operator-managed).
 *
 * This card lives only in the baseStation drawer (other categories don't
 * have topology profiles today — empty list with reason='not_a_uxm').
 * Operator picks a profile; PUT persists to connection_params and, if
 * a live driver is available + compat allows, applies on the driver
 * immediately. 409 path = incompatible with detected Test App, surfaced
 * inline so operator sees the reason before re-attempting.
 */
function TopologyProfileCard({ categoryKey }: { categoryKey: string }) {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['instruments', 'topologyProfiles', categoryKey],
    queryFn: () => fetchTopologyProfiles(categoryKey),
    refetchOnWindowFocus: false,
  })

  const [opError, setOpError] = useState<string | null>(null)
  const [opMessage, setOpMessage] = useState<string | null>(null)

  // P2-1 Phase 2.2: editor modal state. `mode` distinguishes create
  // (blank form) from edit (pre-filled from initialDetail). System
  // presets open in edit mode with all inputs disabled — the modal
  // shows a banner directing the operator to duplicate first.
  const [editorOpen, setEditorOpen] = useState(false)
  const [editorMode, setEditorMode] = useState<'create' | 'edit'>('create')
  const [editorInitial, setEditorInitial] =
    useState<TopologyProfileDetail | null>(null)
  // Loading flag for the on-demand fetch when opening editor for an
  // existing profile (the list response only carries the truncated
  // entry; the editor needs full detail).
  const [editorLoading, setEditorLoading] = useState(false)

  const openCreate = () => {
    setEditorMode('create')
    setEditorInitial(null)
    setEditorOpen(true)
  }

  const openEdit = async (profileId: string) => {
    setEditorLoading(true)
    try {
      const { fetchTopologyProfile } = await import('./api/service')
      const detail = await fetchTopologyProfile(categoryKey, profileId)
      setEditorMode('edit')
      setEditorInitial(detail)
      setEditorOpen(true)
    } catch (err) {
      setOpError(
        err instanceof Error ? err.message : '加载拓扑详情失败',
      )
    } finally {
      setEditorLoading(false)
    }
  }

  const duplicateMutation = useMutation({
    mutationFn: (profileId: string) =>
      duplicateTopologyProfile(categoryKey, profileId),
    onSuccess: (copy) => {
      queryClient.invalidateQueries({
        queryKey: ['instruments', 'topologyProfiles', categoryKey],
      })
      setOpError(null)
      setOpMessage(`已复制为副本: ${copy.name}（${copy.profile_id}）`)
      // Open the new copy in edit mode so operator can immediately
      // adjust it — primary motivation for cloning a preset.
      setEditorMode('edit')
      setEditorInitial(copy)
      setEditorOpen(true)
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? '复制失败'
      setOpError(String(detail))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (profileId: string) =>
      deleteTopologyProfile(categoryKey, profileId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['instruments', 'topologyProfiles', categoryKey],
      })
      setOpError(null)
      setOpMessage('已删除')
    },
    onError: (err: unknown) => {
      // 409 on system preset surfaces refused payload; fall through
      // to .detail otherwise.
      const data = (err as { response?: { data?: any } })?.response?.data
      if (data?.refused) {
        setOpError(`无法删除：${data.detail ?? data.reason}`)
      } else {
        setOpError(String(data?.detail ?? '删除失败'))
      }
    },
  })

  const items = data?.items ?? []
  const currentTestApp = data?.current_test_app ?? null
  const selectedId = data?.selected_topology_profile_id ?? null
  const reason = data?.reason ?? null

  const selectMutation = useMutation({
    mutationFn: (profileId: string | null) =>
      selectTopologyProfile(categoryKey, profileId),
    onSuccess: (result) => {
      // Refetch to pick up the new selection + compat status (live driver
      // detected_test_app may have changed since last load).
      queryClient.invalidateQueries({
        queryKey: ['instruments', 'topologyProfiles', categoryKey],
      })
      setOpError(null)
      if (result.applied_now) {
        setOpMessage(
          `已选择并立即应用到运行中的 ${result.test_app ?? 'Test App'}`,
        )
      } else if (result.profile_id === null) {
        setOpMessage('已清除拓扑选择（HAL 重载时不会自动应用）')
      } else {
        const skip = result.apply_skipped_reason
        const skipLabel: Record<string, string> = {
          no_live_driver: 'HAL 未加载驱动，HAL 重载时生效',
          driver_does_not_support_topology_profiles: '该驱动不支持拓扑应用',
          incompatible_test_app: '驱动层兼容性拒绝（请检查 Test App）',
        }
        setOpMessage(
          `已保存（${skipLabel[skip ?? ''] ?? `apply_skipped_reason=${skip}`}）`,
        )
      }
    },
    onError: (err: unknown) => {
      // 409 from refuse arm carries `refused: true` + structured reason.
      // Surface the detail so operator sees WHY (incompatible Test App
      // is the common case).
      const data = (err as { response?: { data?: any } })?.response?.data
      if (data?.refused) {
        const compatList =
          (data.profile_compatible_with as string[] | undefined)?.join(', ') ??
          '?'
        setOpError(
          `拒绝：拓扑 ${data.profile_id} 与当前 Test App "${data.test_app}" ` +
            `不兼容（兼容范围：${compatList}）`,
        )
      } else {
        const detail =
          (err as { response?: { data?: { detail?: string } } })?.response?.data
            ?.detail ?? '选择失败'
        setOpError(String(detail))
      }
      setOpMessage(null)
    },
  })

  if (reason === 'not_a_uxm') {
    // Don't render the card on non-UXM bindings.
    return null
  }

  const selectData = items.map((item) => {
    const compatTag =
      item.compatible_with_current_test_app === false
        ? ' (不兼容当前 Test App)'
        : item.compatible_with_current_test_app === null
          ? ' (HAL 未加载)'
          : ''
    return {
      value: item.profile_id,
      label: `${item.name}${compatTag}`,
      disabled: item.compatible_with_current_test_app === false,
    }
  })

  // P2-1 Phase 2.2: action buttons need to know what the operator's
  // currently selected ROW looks like — is it a system preset
  // (Edit -> read-only banner, Duplicate is the meaningful action)
  // or operator-owned (Edit / Delete are meaningful, Duplicate is
  // still allowed). The list response carries `is_system_preset` so
  // we don't need an extra fetch just for the affordance logic.
  const selectedItem = items.find((i) => i.profile_id === selectedId) ?? null
  const selectedIsPreset = selectedItem?.is_system_preset === true

  return (
    <Card withBorder padding="md" radius="md" shadow="xs">
      <Stack gap="sm">
        <Group justify="space-between" align="center">
          <Stack gap={2}>
            <Text fw={600}>拓扑 Profile (P2-1)</Text>
            <Text size="xs" c="gray.6">
              {currentTestApp
                ? `当前 Test App: ${currentTestApp}（不兼容选项已禁用）`
                : 'HAL 未加载或 Test App 未检测到 — 选择会在下次 HAL 重载生效'}
            </Text>
          </Stack>
          <Group gap="xs">
            <Button
              size="xs"
              variant="light"
              onClick={openCreate}
              disabled={categoryKey !== 'baseStation'}
            >
              + 新建
            </Button>
            <Button
              size="xs"
              variant="subtle"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              刷新
            </Button>
          </Group>
        </Group>

        {isLoading ? (
          <Text size="sm" c="gray.6">
            加载中...
          </Text>
        ) : isError ? (
          <Text size="sm" c="red.6">
            加载失败
          </Text>
        ) : items.length === 0 ? (
          <Text size="sm" c="gray.6">
            (该 category 无可选拓扑 profile)
          </Text>
        ) : (
          <>
            <Select
              label="选择拓扑"
              placeholder="(未选择 — HAL 重载时不会自动应用)"
              data={selectData}
              value={selectedId}
              clearable
              onChange={(value) => selectMutation.mutate(value)}
              disabled={selectMutation.isPending}
            />
            {/* P2-1 Phase 2.2: row-level CRUD actions on the
                selected profile. Disabled when nothing selected,
                or (for Delete) when it's a system preset since the
                backend rejects with 409 anyway. */}
            {selectedItem ? (
              <Group gap="xs">
                <Button
                  size="xs"
                  variant="light"
                  onClick={() => openEdit(selectedItem.profile_id)}
                  loading={editorLoading}
                >
                  {selectedIsPreset ? '查看（只读）' : '编辑'}
                </Button>
                <Button
                  size="xs"
                  variant="light"
                  color="grape"
                  onClick={() =>
                    duplicateMutation.mutate(selectedItem.profile_id)
                  }
                  loading={duplicateMutation.isPending}
                >
                  复制为副本
                </Button>
                <Button
                  size="xs"
                  variant="light"
                  color="red"
                  onClick={() => {
                    if (
                      window.confirm(
                        `删除拓扑 ${selectedItem.name}？此操作不可撤销。`,
                      )
                    ) {
                      deleteMutation.mutate(selectedItem.profile_id)
                    }
                  }}
                  loading={deleteMutation.isPending}
                  disabled={selectedIsPreset}
                  title={
                    selectedIsPreset ? '系统预设不可删除（请复制后删除副本）' : ''
                  }
                >
                  删除
                </Button>
              </Group>
            ) : null}
          </>
        )}

        {opError ? (
          <Text size="xs" c="red.6">
            {opError}
          </Text>
        ) : null}
        {opMessage ? (
          <Text size="xs" c="teal.7">
            {opMessage}
          </Text>
        ) : null}
      </Stack>

      {/* P2-1 Phase 2.2: editor modal — overlays the card; closes
          back to it on save / cancel. invalidateQueries inside the
          modal's mutation hooks refreshes the list automatically. */}
      <TopologyProfileEditor
        opened={editorOpen}
        mode={editorMode}
        initialData={editorInitial}
        categoryKey={categoryKey}
        onClose={() => setEditorOpen(false)}
        onSaved={() => setEditorOpen(false)}
      />
    </Card>
  )
}


/**
 * Channel-model list card for the channelEmulator category drawer.
 *
 * Pulls the operator-curated list of selectable channel-model files
 * from the backend (driver reads it from
 * ``InstrumentConnection.connection_params['available_channel_models']``).
 *
 * Why a dedicated component: needs its own ``useQuery`` for the
 * channel-models endpoint, which can't live inside the IIFE we use for
 * channelEmulator-specific drawer fields.
 *
 * Why no inline editor today (CAICT 2026-05-13): F64's ATE Server
 * doesn't expose MMEM SCPI and FTP is closed on the chamber's F64, so
 * we can't dynamic-discover .smu files. The operator-curated list lives
 * in connection_params JSON; this card is read-only display. A future
 * iteration adds in-place add/remove UI.
 */
function ChannelModelsCard({ categoryKey }: { categoryKey: string }) {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['instruments', 'channelModels', categoryKey],
    queryFn: () => fetchChannelModels(categoryKey),
    // Don't auto-refetch on window focus — this is a config view, not
    // a live status feed; nothing changes without operator action.
    refetchOnWindowFocus: false,
  })

  const items = data?.items ?? []
  const reason = data?.reason ?? null

  // Add form state — kept local to the card so the parent's render
  // costs don't grow with this UI. Fields are intentionally minimal:
  // filename is required, label / description optional.
  const [addOpen, setAddOpen] = useState(false)
  const [newFilename, setNewFilename] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [newRadioTechnology, setNewRadioTechnology] = useState<'nr5g' | 'lte'>('nr5g')
  const [newBand, setNewBand] = useState('')
  const [newChannelNumber, setNewChannelNumber] = useState<number | string>('')
  const [opError, setOpError] = useState<string | null>(null)

  const addMutation = useMutation({
    mutationFn: () =>
      addChannelModel(categoryKey, {
        filename: newFilename.trim(),
        label: newLabel.trim() || newFilename.trim(),
        description: newDescription.trim(),
        radio_technology: newRadioTechnology,
        channel_kind: newRadioTechnology === 'lte' ? 'lte_dl_earfcn' : 'nr_arfcn',
        band: newBand.trim().toUpperCase(),
        ...(newRadioTechnology === 'lte'
          ? { lte_dl_earfcn: Number(newChannelNumber) }
          : { nr_arfcn: Number(newChannelNumber) }),
      }),
    onSuccess: (result) => {
      // Backend returns the post-add list shape (same as fetchChannelModels)
      // so we can seed the cache directly instead of refetching.
      queryClient.setQueryData(
        ['instruments', 'channelModels', categoryKey],
        result,
      )
      setNewFilename('')
      setNewLabel('')
      setNewDescription('')
      setNewRadioTechnology('nr5g')
      setNewBand('')
      setNewChannelNumber('')
      setOpError(null)
      setAddOpen(false)
    },
    onError: (err: unknown) => {
      // Surface backend 409 (duplicate) / 422 (invalid) as inline error
      // — better than a generic toast since the user is mid-input.
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? '添加失败'
      setOpError(String(detail))
    },
  })

  const removeMutation = useMutation({
    mutationFn: (filename: string) => removeChannelModel(categoryKey, filename),
    onSuccess: (result) => {
      queryClient.setQueryData(
        ['instruments', 'channelModels', categoryKey],
        result,
      )
      setOpError(null)
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? '删除失败'
      setOpError(String(detail))
    },
  })

  // Pretty status banner. Each "empty" reason has a different actionable
  // hint so the operator knows what to fix.
  const statusBanner = (() => {
    if (isLoading) return null
    if (isError) {
      return <Alert color="red" variant="light">无法加载信道模型清单 — 请重试或检查后端日志</Alert>
    }
    if (reason === 'driver_not_loaded' && items.length === 0) {
      return (
        <Alert color="yellow" variant="light">
          驱动未加载. 清单可在此处直接编辑 — 编辑完成后请点击页面顶部「↻ 重新加载驱动」.
        </Alert>
      )
    }
    if (reason === 'not_a_channel_emulator') {
      return <Alert color="gray" variant="light">该类别不支持信道模型清单功能.</Alert>
    }
    if (items.length === 0) {
      return (
        <Alert color="blue" variant="light">
          清单为空. 点击下方「+ 添加」按钮添加 .smu / .rtc / .asc 文件名
          (F64 不支持文件浏览, 由操作员手工维护清单).
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
            <Text fw={600} size="sm">可用信道模型</Text>
            <Text size="xs" c="dimmed">
              GCM 原生管线 (.smu) / Runtime 管线 (.rtc / .asc). 操作员维护清单, 测试编排从这里下拉选择.
            </Text>
          </Stack>
          <Group gap="xs">
            <Button
              variant="light"
              size="xs"
              onClick={() => {
                setAddOpen((v) => !v)
                setOpError(null)
              }}
            >
              {addOpen ? '× 关闭' : '+ 添加'}
            </Button>
            <Button
              variant="subtle"
              size="xs"
              onClick={() => refetch()}
              loading={isFetching}
            >
              ↻ 刷新
            </Button>
          </Group>
        </Group>

        {statusBanner}

        {opError ? (
          <Alert color="red" variant="light" onClose={() => setOpError(null)} withCloseButton>
            {opError}
          </Alert>
        ) : null}

        {addOpen ? (
          <Card withBorder padding="sm" radius="sm" bg="white">
            <Stack gap="xs">
              <TextInput
                size="xs"
                label="文件名 (必填, .smu / .rtc / .asc)"
                placeholder="EPA_5Hz.smu"
                value={newFilename}
                onChange={(e) => setNewFilename(e.currentTarget.value)}
              />
              <TextInput
                size="xs"
                label="显示名 (可选)"
                placeholder="EPA 5 Hz (low-speed pedestrian)"
                value={newLabel}
                onChange={(e) => setNewLabel(e.currentTarget.value)}
              />
              <TextInput
                size="xs"
                label="描述 (可选)"
                placeholder="3GPP TS 36.521-1 Table B.2.1-1"
                value={newDescription}
                onChange={(e) => setNewDescription(e.currentTarget.value)}
              />
              <Select
                size="xs"
                label="无线制式（必填）"
                data={[{ value: 'nr5g', label: '5G NR' }, { value: 'lte', label: 'LTE' }]}
                value={newRadioTechnology}
                onChange={(value) => {
                  setNewRadioTechnology(value === 'lte' ? 'lte' : 'nr5g')
                  setNewBand('')
                  setNewChannelNumber('')
                }}
                allowDeselect={false}
              />
              <Group grow>
                <TextInput size="xs" label="频段 Band（必填）" placeholder={newRadioTechnology === 'lte' ? 'B3' : 'N78'}
                  value={newBand} onChange={(event) => setNewBand(event.currentTarget.value)} />
                <NumberInput size="xs" label={newRadioTechnology === 'lte' ? 'DL EARFCN（必填）' : 'NR-ARFCN（必填）'}
                  value={newChannelNumber} onChange={setNewChannelNumber} min={0} />
              </Group>
              <Group justify="flex-end" gap="xs">
                <Button
                  size="xs"
                  variant="subtle"
                  onClick={() => {
                    setAddOpen(false)
                    setNewFilename('')
                    setNewLabel('')
                    setNewDescription('')
                    setNewRadioTechnology('nr5g')
                    setNewBand('')
                    setNewChannelNumber('')
                    setOpError(null)
                  }}
                >
                  取消
                </Button>
                <Button
                  size="xs"
                  onClick={() => addMutation.mutate()}
                  loading={addMutation.isPending}
                  disabled={!newFilename.trim() || !newBand.trim() || typeof newChannelNumber !== 'number'}
                >
                  保存
                </Button>
              </Group>
            </Stack>
          </Card>
        ) : null}

        {items.length > 0 ? (
          <Stack gap="xs">
            {items.map((item) => (
              <Group key={item.filename} justify="space-between" wrap="nowrap" align="flex-start">
                <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
                  <Group gap="xs" align="baseline">
                    <Text size="sm" fw={500} style={{ fontFamily: 'monospace' }}>
                      {item.filename}
                    </Text>
                    <Badge size="xs" variant="outline" color="brand">
                      {item.type}
                    </Badge>
                    <Badge size="xs" variant="light" color={item.radio_technology === 'legacy_unknown' ? 'yellow' : 'blue'}>
                      {item.radio_technology === 'legacy_unknown'
                        ? '历史·身份未知'
                        : `${item.radio_technology === 'lte' ? 'LTE' : 'NR'} ${item.band ?? ''} ${item.channel_kind === 'lte_dl_earfcn' ? `EARFCN ${item.lte_dl_earfcn}` : `ARFCN ${item.nr_arfcn}`}`}
                    </Badge>
                  </Group>
                  {item.label !== item.filename ? (
                    <Text size="xs" c="gray.7">{item.label}</Text>
                  ) : null}
                  {item.description ? (
                    <Text size="xs" c="dimmed">{item.description}</Text>
                  ) : null}
                </Stack>
                <ActionIcon
                  variant="subtle"
                  color="red"
                  size="sm"
                  onClick={() => {
                    if (
                      window.confirm(
                        `从清单中删除 "${item.filename}"?\n\n` +
                          `这只是从 GUI curated list 删掉, 不会动 F64 上的实际文件.`,
                      )
                    ) {
                      removeMutation.mutate(item.filename)
                    }
                  }}
                  loading={
                    removeMutation.isPending &&
                    removeMutation.variables === item.filename
                  }
                  aria-label={`删除 ${item.filename}`}
                  title="删除此条目"
                >
                  ×
                </ActionIcon>
              </Group>
            ))}
          </Stack>
        ) : null}
      </Stack>
    </Card>
  )
}

function EquipmentManager() {
  const queryClient = useQueryClient()
  const { selectedLabProfileId, selectedLabProfile } = useOperationalLab()
  const { data, isLoading } = useQuery({
    queryKey: ['instruments', 'catalog'],
    queryFn: fetchInstrumentCatalog,
  })

  const categories = useMemo(() => data?.categories ?? [], [data])

    const [drafts, setDrafts] = useState<Record<string, EquipmentDraft>>({})
  const [editingCategoryKey, setEditingCategoryKey] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<Record<string, EquipmentFeedback>>({})
  const [certificationExecutionId, setCertificationExecutionId] = useState('')
  const [certificationOperator, setCertificationOperator] = useState('')
  const [certificationReason, setCertificationReason] = useState('')
  const feedbackTimers = useRef<Record<string, number>>({})

  // SCPI 终端状态
  type ScpiResult = { command: string; response?: string | null; success: boolean; error?: string | null; latency_ms: number }
  const [scpiProbeResults, setScpiProbeResults] = useState<Record<string, ScpiResult[]>>({})
  const [scpiManualCmd, setScpiManualCmd] = useState<Record<string, string>>({})
  const [scpiManualResults, setScpiManualResults] = useState<Record<string, ScpiResult[]>>({})
  const [scpiLoading, setScpiLoading] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (categories.length === 0) {
      setDrafts({})
      return
    }
    setDrafts((prev) => {
      const next: Record<string, EquipmentDraft> = {}
      categories.forEach((category) => {
        const previous = prev[category.key]
        const selectedModel = category.models.find(
          (model) => model.id === (previous?.modelId ?? category.selectedModelId),
        )
        const manifest = selectedModel?.base_station_manifest
        next[category.key] = {
          modelId: previous?.modelId ?? (category.selectedModelId ?? ''),
          endpoint: previous?.endpoint ?? (category.connection.endpoint ?? ''),
          controller: previous?.controller ?? (category.connection.controller ?? ''),
          notes: previous?.notes ?? (category.connection.notes ?? ''),
          connection_params: previous?.connection_params ?? (category.connection.connection_params ? JSON.stringify(category.connection.connection_params, null, 2) : ''),
          base_station_profile: previous?.base_station_profile ?? (
            manifest
              ? readBaseStationProfileDraft(
                  manifest,
                  category.connection.connection_params?.base_station_adapter_profile,
                )
              : undefined
          ),
        }
      })
      return next
    })
  }, [categories])

  useEffect(() => {
    return () => {
      Object.values(feedbackTimers.current).forEach((timer) => window.clearTimeout(timer))
    }
  }, [])

  const showFeedback = useCallback((categoryKey: string, type: 'success' | 'error', message: string) => {
    const activeTimer = feedbackTimers.current[categoryKey]
    if (activeTimer) {
      window.clearTimeout(activeTimer)
    }
    setFeedback((prev) => ({ ...prev, [categoryKey]: { type, message } }))
    feedbackTimers.current[categoryKey] = window.setTimeout(() => {
      setFeedback((prev) => {
        const { [categoryKey]: _removed, ...rest } = prev
        return rest
      })
      delete feedbackTimers.current[categoryKey]
    }, 2000)
  }, [])

  const diagnosticTargetFor = useCallback((
    categoryKey: string,
    draftEndpoint: string,
    savedEndpoint: string,
  ) => {
    const target = buildDiagnosticTarget(categoryKey, draftEndpoint, savedEndpoint)
    if (target.error) {
      showFeedback(categoryKey, 'error', target.error)
      return null
    }
    return target.payload ?? {}
  }, [showFeedback])

  const instrumentMutation = useMutation({
    mutationFn: ({ categoryKey, payload }: EquipmentMutationVariables) =>
      updateInstrumentCategory(categoryKey, payload),
    onSuccess: (updatedCategory, variables) => {
      queryClient.setQueryData(
        ['instruments', 'catalog'],
        (previous: InstrumentsResponse | undefined): InstrumentsResponse => {
          if (!previous) return { categories: [updatedCategory] }
          return {
            categories: previous.categories.map((item) =>
              item.key === updatedCategory.key ? updatedCategory : item,
            ),
          }
        },
      )
      setDrafts((prev) => {
        const selectedModel = updatedCategory.models.find(
          (model) => model.id === updatedCategory.selectedModelId,
        )
        const manifest = selectedModel?.base_station_manifest
        return {
          ...prev,
          [updatedCategory.key]: {
          modelId: updatedCategory.selectedModelId ?? '',
          endpoint: updatedCategory.connection.endpoint ?? '',
          controller: updatedCategory.connection.controller ?? '',
          notes: updatedCategory.connection.notes ?? '',
          connection_params: updatedCategory.connection.connection_params
            ? JSON.stringify(updatedCategory.connection.connection_params, null, 2)
            : '',
            base_station_profile: manifest
              ? readBaseStationProfileDraft(
                  manifest,
                  updatedCategory.connection.connection_params?.base_station_adapter_profile,
                )
              : undefined,
          },
        }
      })
      const needsHALReload =
        updatedCategory.key === 'baseStation' || updatedCategory.key === 'channelEmulator'
      showFeedback(
        variables.categoryKey,
        'success',
        needsHALReload
          ? '配置已保存；请重新加载 HAL 后再进行连接测试或 SCPI 操作。'
          : '配置已保存。',
      )
    },
    onError: (error: unknown, variables) => {
      showFeedback(
        variables.categoryKey,
        'error',
        `保存失败: ${diagnosticErrorMessage(error)}`,
      )
    },
  })

  const siteCertificationMutation = useMutation({
    mutationFn: async ({ connectionId, revoke }: { connectionId: string; revoke: boolean }) => (
      revoke
        ? revokeBaseStationSiteCertification(connectionId, {
            revoked_by: certificationOperator.trim(),
            reason: certificationReason.trim(),
          })
        : certifyBaseStationSite(connectionId, {
            source_execution_id: certificationExecutionId.trim(),
            certified_by: certificationOperator.trim(),
            reason: certificationReason.trim(),
          })
    ),
    onSuccess: (certification) => {
      queryClient.invalidateQueries({ queryKey: ['instruments', 'catalog'] })
      queryClient.invalidateQueries({ queryKey: ['cmw500-lte-2x2-readiness'] })
      queryClient.invalidateQueries({ queryKey: ['cockpit', 'readiness'] })
      showFeedback(
        'baseStation',
        'success',
        certification.status === 'active'
          ? 'BaseStation 现场认证已从服务端执行证据激活，仅影响后续执行。'
          : 'BaseStation 现场认证已撤销，仅影响后续执行。',
      )
    },
    onError: (error: unknown) => {
      showFeedback(
        'baseStation',
        'error',
        `BaseStation 现场认证更新失败: ${diagnosticErrorMessage(error)}`,
      )
    },
  })

  const syncLabBindingMutation = useMutation({
    mutationFn: (categoryKey: string) => {
      if (!selectedLabProfileId) {
        throw new Error('请先在顶部选择 LabProfile')
      }
      return syncCurrentInstrumentBinding(selectedLabProfileId, categoryKey)
    },
    onSuccess: (syncResult, categoryKey) => {
      queryClient.invalidateQueries({ queryKey: ['lab-profiles'] })
      queryClient.invalidateQueries({ queryKey: ['cmw500-lte-2x2-readiness'] })
      queryClient.invalidateQueries({ queryKey: ['cockpit', 'readiness'] })
      showFeedback(
        categoryKey,
        'success',
        categoryKey === 'baseStation'
          ? `已同步到 ${selectedLabProfile?.name ?? '当前 LabProfile'}：${formatBaseStationSyncTruth(syncResult.resolved)}`
          : `已同步到 ${selectedLabProfile?.name ?? '当前 LabProfile'}。`,
      )
    },
    onError: (error: unknown, categoryKey) => {
      showFeedback(
        categoryKey,
        'error',
        `同步 LabProfile 失败: ${diagnosticErrorMessage(error)}`,
      )
    },
  })

  const handleModelChange = useCallback(
    (categoryKey: string, modelId: string) => {
      setDrafts((prev) => {
        const current =
          prev[categoryKey] ?? ({ modelId: '', endpoint: '', controller: '', notes: '' } as EquipmentDraft)
        const category = categories.find((item) => item.key === categoryKey)
        const manifest = category?.models.find(
          (model) => model.id === modelId,
        )?.base_station_manifest
        return {
          ...prev,
          [categoryKey]: {
            ...current,
            modelId,
            base_station_profile: manifest
              ? readBaseStationProfileDraft(
                  manifest,
                  category?.connection.connection_params?.base_station_adapter_profile,
                )
              : undefined,
          },
        }
      })
      const selectedManifest = categories.find(
        (item) => item.key === categoryKey,
      )?.models.find((model) => model.id === modelId)?.base_station_manifest
      instrumentMutation.mutate({
        categoryKey,
        payload: {
          modelId,
          ...(selectedManifest?.profile_requirement === 'not_applicable'
            ? { connection: { base_station_adapter_profile: null } }
            : {}),
        },
      })
    },
    [categories, instrumentMutation],
  )

  const handleFieldChange = useCallback(
    (categoryKey: string, field: keyof EquipmentDraft) =>
      (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        const value = event.target.value
        setDrafts((prev) => {
          const current =
            prev[categoryKey] ?? ({ modelId: '', endpoint: '', controller: '', notes: '' } as EquipmentDraft)
          return {
            ...prev,
            [categoryKey]: { ...current, [field]: value },
          }
        })
      },
    [],
  )

  const handleSaveConnection = useCallback(
    (categoryKey: string) => {
      const draft = drafts[categoryKey]
      if (!draft) return
      
      let parsedParams: Record<string, unknown> | undefined
      if (draft.connection_params) {
        try {
          parsedParams = JSON.parse(draft.connection_params)
          if (
            parsedParams === null
            || typeof parsedParams !== 'object'
            || Array.isArray(parsedParams)
          ) throw new Error('connection_params must be an object')
          delete parsedParams.base_station_adapter_profile
        } catch (e) {
          showFeedback(categoryKey, 'error', 'JSON 配置格式无效')
          return
        }
      }

      const category = categories.find((item) => item.key === categoryKey)
      const selectedModel = category?.models.find((model) => model.id === draft.modelId)
      const manifest = selectedModel?.base_station_manifest
      let baseStationProfile: Record<string, unknown> | null | undefined
      if (categoryKey === 'baseStation' && manifest) {
        try {
          baseStationProfile = buildBaseStationAdapterProfile(
            manifest,
            draft.base_station_profile ?? emptyBaseStationProfileDraft(manifest),
          )
        } catch (error) {
          showFeedback(
            categoryKey,
            'error',
            error instanceof Error ? error.message : 'BaseStation adapter profile 配置无效',
          )
          return
        }
      }

      instrumentMutation.mutate({
        categoryKey,
        payload: {
          connection: {
            endpoint: draft.endpoint || undefined,
            controller: draft.controller || undefined,
            notes: draft.notes || undefined,
            ...(parsedParams !== undefined ? { connection_params: parsedParams } : {}),
            ...(baseStationProfile !== undefined
              ? { base_station_adapter_profile: baseStationProfile }
              : {}),
          },
        },
      })
    },
    [categories, drafts, instrumentMutation, showFeedback],
  )

  const modelSelectData = useMemo(() => {
    const map: Record<string, { value: string; label: string }[]> = {}
    categories.forEach((category) => {
      map[category.key] = category.models.map((model) => ({
        value: model.id,
        label: `${model.vendor} ${model.model}`,
      }))
    })
    return map
  }, [categories])

  // HAL 模式管理
  const { data: halStatus, refetch: refetchHAL } = useQuery({
    queryKey: ['instruments', 'hal', 'status'],
    queryFn: async () => {
      const resp = await client.get('/instruments/hal/status')
      return resp.data as { mode: string; driver_count: number; active_drivers: string[] }
    },
  })
  const [halSwitching, setHalSwitching] = useState(false)

  const handleHALSwitch = useCallback(async (newMode: string) => {
    setHalSwitching(true)
    try {
      const resp = await client.post('/instruments/hal/switch', { mode: newMode })
      const result = resp.data as { success: boolean; message: string }
      if (result.success) {
        showFeedback('__hal__', 'success', `✅ ${result.message}`)
      } else {
        showFeedback('__hal__', 'error', `❌ ${result.message}`)
      }
      refetchHAL()
    } catch (err: any) {
      showFeedback('__hal__', 'error', `切换失败: ${err.message}`)
    } finally {
      setHalSwitching(false)
    }
  }, [refetchHAL, showFeedback])

  const [halReloading, setHalReloading] = useState(false)
  // P3-1: two-stage confirm flow. Reload tears down every VISA/SOCKET
  // session — if it happens mid-test, the in-flight diagnostic dies
  // with a closed-session error after a ~30s timeout. Stage 1 is the
  // accidental-click guard (always shown); stage 2 only appears if
  // the backend's P2-5 refuse-while-in-flight policy returned HTTP 409
  // with a blockers list, and asks the operator to take responsibility
  // for the abort by force-overriding.
  const performHALReload = useCallback(
    async (force: boolean) => {
      setHalReloading(true)
      try {
        const url = force ? '/instruments/hal/reload?force=true' : '/instruments/hal/reload'
        const resp = await client.post(url)
        const result = resp.data as {
          drivers_loaded: number
          drivers: string[]
          duration_ms: number
          forced?: boolean
        }
        const prefix = result.forced ? '⚠️ 已强制重新加载' : '✅ 已重新加载'
        showFeedback(
          '__hal__',
          'success',
          `${prefix} ${result.drivers_loaded} 个驱动 (${result.duration_ms}ms): ${result.drivers.join(', ')}`,
        )
        refetchHAL()
        // Channel-models endpoint is driver-bound; invalidate the cache so
        // any open dropdown refetches against the freshly-loaded driver.
        queryClient.invalidateQueries({ queryKey: ['instruments', 'channelModels'] })
      } catch (err: any) {
        // P2-5 refuse path: 409 + structured HalReloadRefusedResult body.
        // Stage-2 confirm offers a force-override; on accept we re-POST
        // with force=true. Any other error (network, 5xx, unexpected
        // shape) falls through to the generic feedback.
        const refused = err?.response?.status === 409 ? err.response.data : null
        if (refused?.refused && Array.isArray(refused.blockers)) {
          modals.openConfirmModal({
            title: '⚠️ 强制重新加载？',
            centered: true,
            children: (
              <Stack gap="sm">
                <Text size="sm">
                  HAL 拒绝重新加载，因为有 <strong>{refused.blockers.length}</strong> 个正在进行的任务：
                </Text>
                <Stack gap={4} pl="md">
                  {refused.blockers.map((b: { id: string; name: string; status: string }) => (
                    <Text key={b.id} size="sm" c="gray.7">
                      • {b.name} <Text component="span" size="xs" c="gray.5">({b.status})</Text>
                    </Text>
                  ))}
                </Stack>
                <Text size="sm" c="red.7">
                  强制重新加载将中断这些任务（VISA 会话会被关闭，结果可能丢失）。操作员需自行处理后续清理。
                </Text>
              </Stack>
            ),
            labels: { confirm: '强制重新加载', cancel: '取消' },
            confirmProps: { color: 'red' },
            onConfirm: () => {
              void performHALReload(true)
            },
          })
        } else {
          showFeedback('__hal__', 'error', `❌ 重新加载失败: ${err.message}`)
        }
      } finally {
        setHalReloading(false)
      }
    },
    [queryClient, refetchHAL, showFeedback],
  )
  const handleHALReload = useCallback(() => {
    // POST /instruments/hal/reload — needed after editing endpoint /
    // selectedModel / driver_mode for the change to take effect without
    // restarting the backend (HAL init runs once at FastAPI lifespan
    // startup). 10s+ duration is normal — driver.connect() runs once
    // per category, with full VISA / SOCKET dial timeouts.
    modals.openConfirmModal({
      title: '确认重新加载驱动',
      centered: true,
      children: (
        <Stack gap="sm">
          <Text size="sm">
            将会断开并重新初始化所有仪器驱动，过程通常需要 10 秒以上。
          </Text>
          {/* 判据的真值源是 hal_reload_policy.find_reload_blockers (端点调的
              就是这个复合入口, 将来加第二个 blocker 源也加在那儿) — 改判据
              必须同步改这句。ARCH-1 S4c 拆掉计划那半截后只剩执行行。
              ⚠️ 别把独立跑的「诊断序列」写进这句: 它跑在请求线程上、不建行,
              闸门探测不到 (hal_reload_policy 模块 docstring 已明确) */}
          <Text size="sm" c="gray.7">
            如果有执行正占着驱动 —— 在跑的测试用例 / 暗室首测 / 单相位诊断，或
            <strong>暂停中的</strong>传导 / OTA 虚拟路测（暂停不释放硬件）——
            后端会拒绝并提示是否强制覆盖。
          </Text>
        </Stack>
      ),
      labels: { confirm: '重新加载', cancel: '取消' },
      confirmProps: { color: 'brand' },
      onConfirm: () => {
        void performHALReload(false)
      },
    })
  }, [performHALReload])

  return (
    <Stack gap="xl">
      <Drawer
        opened={!!editingCategoryKey}
        onClose={() => setEditingCategoryKey(null)}
        title={<Title order={4}>参数配置</Title>}
        position="right"
        size="lg"
        padding="xl"
      >
        {(() => {
          const category = categories.find((c) => c.key === editingCategoryKey)
          if (!category) return null
          const draft = drafts[category.key]
          if (!draft) return null
          const drawerSelectedModel = category.models.find((model) => model.id === draft.modelId) ?? null

          return (
            <Stack gap="xl">
              <Group gap="sm" align="center">
                <Title order={3}>{category.label}</Title>
              </Group>

              <Stack gap="md">
                <Select
                  label="选择型号"
                  placeholder="请选择仪器型号"
                  data={modelSelectData[category.key] ?? []}
                  value={draft.modelId}
                  onChange={(value) => handleModelChange(category.key, value ?? '')}
                  disabled={instrumentMutation.isPending}
                />
                <Card withBorder padding="md" radius="md" shadow="xs" bg="gray.0">
                  {drawerSelectedModel ? (
                    <Stack gap="sm">
                      <Group justify="space-between" align="flex-start">
                        <Stack gap={2}>
                          <Text fw={600}>
                            {drawerSelectedModel.vendor} {drawerSelectedModel.model}
                          </Text>
                          <Text size="sm" c="gray.6">
                            {drawerSelectedModel.summary}
                          </Text>
                        </Stack>
                        <Badge color={instrumentStatusColor[drawerSelectedModel.status]} variant="light">
                          {instrumentStatusLabel[drawerSelectedModel.status]}
                        </Badge>
                      </Group>
                      <Group gap="sm" c="gray.6" wrap="wrap">
                        {drawerSelectedModel.channels ? <Text size="xs">通道: {drawerSelectedModel.channels}</Text> : null}
                        {drawerSelectedModel.bandwidth ? <Text size="xs">带宽: {drawerSelectedModel.bandwidth}</Text> : null}
                        <Text size="xs">接口: {drawerSelectedModel.interfaces.join(' / ')}</Text>
                      </Group>
                      <Group gap="xs" wrap="wrap">
                        {drawerSelectedModel.capabilities.map((capability) => (
                          <Badge key={capability} variant="outline" color="brand">
                            {capability}
                          </Badge>
                        ))}
                      </Group>
                      {/* P3-3: canonical capability tokens from
                          DriverClass.model_capabilities (P2-3). Distinct
                          from the freeform datasheet badges above —
                          these are what plan-level pre-flight actually
                          checks. Hide when empty so an unregistered
                          model doesn't show a misleading "Declared:
                          (none)" row (the catalog status badge above
                          already conveys pending_dev vs available). */}
                      {(drawerSelectedModel.model_capabilities ?? []).length > 0 && (
                        <Stack gap={4}>
                          <Text size="xs" c="gray.6">
                            声明能力 (catalog 中 driver 类的 model_capabilities)
                          </Text>
                          <Group gap="xs" wrap="wrap">
                            {(drawerSelectedModel.model_capabilities ?? []).map((token) => (
                              <Badge
                                key={token}
                                variant="light"
                                color="blue"
                                size="sm"
                              >
                                {token}
                              </Badge>
                            ))}
                          </Group>
                        </Stack>
                      )}
                    </Stack>
                  ) : (
                    <Stack align="center" py="xl" c="gray.6">
                      <Text size="sm">请选择型号以查看能力说明</Text>
                    </Stack>
                  )}
                </Card>
              </Stack>

              <Stack gap="md">
                <TextInput
                  label="控制端点"
                  placeholder="例: 192.168.100.21:5025"
                  value={draft.endpoint}
                  onChange={handleFieldChange(category.key, 'endpoint')}
                />
                <TextInput
                  label="控制方式"
                  placeholder="LAN/SCPI"
                  value={draft.controller}
                  onChange={handleFieldChange(category.key, 'controller')}
                />
                <Textarea
                  label="备注"
                  placeholder="记录登录凭证、联机说明或版本信息"
                  minRows={3}
                  value={draft.notes}
                  onChange={handleFieldChange(category.key, 'notes')}
                />
                
                {category.key === 'rfSwitch' && (
                  <JsonInput
                    label="端口映射配置 (Option B)"
                    description="设置业务逻辑侧 Probe/天线 到物理继电器的路由。"
                    placeholder={'{\n  "port_maps": {\n    "Probe_V_1": {"switch_id": "1:EXT_RELAY_A", "position": 1}\n  }\n}'}
                    validationError="无效的 JSON 格式"
                    formatOnBlur
                    autosize
                    minRows={4}
                    value={draft.connection_params || ''}
                    onChange={(val) => setDrafts(prev => ({
                      ...prev,
                      [category.key]: { ...prev[category.key], connection_params: val }
                    }))}
                  />
                )}

                {category.key === 'channelEmulator' && (() => {
                  // Read/write alignment_name as a single field while keeping
                  // the underlying connection_params JSON the source of truth
                  // (handleSaveConnection already serializes it to the API).
                  let parsedParams: Record<string, unknown> = {}
                  try {
                    parsedParams = draft.connection_params
                      ? JSON.parse(draft.connection_params)
                      : {}
                  } catch {
                    // If existing JSON is malformed, surface that to the
                    // operator instead of silently swallowing — they need
                    // to fix it before we can edit alignment_name cleanly.
                  }
                  const currentAlignment = typeof parsedParams.alignment_name === 'string'
                    ? parsedParams.alignment_name
                    : ''
                  return (
                    <>
                      <TextInput
                        label="F64 User Alignment 文件名"
                        description="在 F64 上预存的 user alignment 文件名（§17.5: 仪器重启后驱动 connect() 自动 SYST:CALIB:USER:SET 重新激活该名）。留空 = 使用 F64 当前已加载的 alignment（如有）。"
                        placeholder="例: CAICT_5G_3500MHz"
                        value={currentAlignment}
                        onChange={(e) => {
                          const newName = e.currentTarget.value
                          const next = { ...parsedParams }
                          if (newName.trim()) {
                            next.alignment_name = newName.trim()
                          } else {
                            delete next.alignment_name
                          }
                          const serialized = Object.keys(next).length > 0
                            ? JSON.stringify(next, null, 2)
                            : ''
                          setDrafts(prev => ({
                            ...prev,
                            [category.key]: { ...prev[category.key], connection_params: serialized },
                          }))
                        }}
                      />
                      <ChannelModelsCard categoryKey={category.key} />
                      {category.connection?.id && (
                        <StandardChannelDefinitionCard connectionId={category.connection.id} />
                      )}
                    </>
                  )
                })()}

                {category.key === 'baseStation' && (
                  // P2-1: UXM topology profile picker. Component itself
                  // bails (returns null) if backend says reason='not_a_uxm'
                  // — safe to render unconditionally for baseStation.
                  <TopologyProfileCard categoryKey={category.key} />
                )}

                {category.key === 'baseStation'
                  && drawerSelectedModel?.base_station_manifest
                  && (
                    drawerSelectedModel.base_station_manifest.profile_requirement === 'required'
                    || drawerSelectedModel.base_station_manifest.formal_gate === 'site_certification'
                  )
                  && (
                  <Card withBorder padding="md" radius="md">
                    <Stack gap="sm">
                      <Stack gap={2}>
                        <Text fw={600} size="sm">
                          {drawerSelectedModel.base_station_manifest.vendor}{' '}
                          {drawerSelectedModel.base_station_manifest.model_name} Adapter Profile
                        </Text>
                        <Text size="xs" c="dimmed">
                          仅填写该 adapter manifest 声明的持久化字段；仪器命令与正式资格仍由后端权威门判定。
                        </Text>
                      </Stack>
                      {drawerSelectedModel.base_station_manifest.formal_gate === 'site_certification' && (
                        <Alert
                          color={category.connection.base_station_site_certification?.status === 'active' ? 'green' : 'yellow'}
                          variant="light"
                        >
                          当前现场认证：{category.connection.base_station_site_certification?.status === 'active'
                            ? `已认证 · ${category.connection.base_station_site_certification.certified_at}`
                            : '未认证或已撤销，仅可诊断'}。服务器认证变化仅影响后续执行。
                        </Alert>
                      )}
                      {drawerSelectedModel.base_station_manifest.formal_gate === 'site_certification' && (
                        <Stack gap="xs">
                          <TextInput
                            label="来源执行 ID"
                            description="服务端只接受当前 binding 下已完成的真实执行；客户端不提交 identity/proof。"
                            value={certificationExecutionId}
                            onChange={(event) => setCertificationExecutionId(event.currentTarget.value)}
                          />
                          <SimpleGrid cols={{ base: 1, sm: 2 }}>
                            <TextInput label="操作人" value={certificationOperator} onChange={(event) => setCertificationOperator(event.currentTarget.value)} />
                            <TextInput label="认证/撤销原因" value={certificationReason} onChange={(event) => setCertificationReason(event.currentTarget.value)} />
                          </SimpleGrid>
                          <Group>
                            <Button
                              size="xs"
                              color="yellow"
                              loading={siteCertificationMutation.isPending}
                              disabled={!category.connection.id || !certificationExecutionId.trim() || !certificationOperator.trim() || !certificationReason.trim()}
                              onClick={() => category.connection.id && siteCertificationMutation.mutate({ connectionId: category.connection.id, revoke: false })}
                            >
                              从执行证据认证现场
                            </Button>
                            <Button
                              size="xs"
                              color="red"
                              variant="outline"
                              loading={siteCertificationMutation.isPending}
                              disabled={!category.connection.id || !certificationOperator.trim() || !certificationReason.trim() || category.connection.base_station_site_certification?.status !== 'active'}
                              onClick={() => category.connection.id && siteCertificationMutation.mutate({ connectionId: category.connection.id, revoke: true })}
                            >
                              撤销现场认证
                            </Button>
                          </Group>
                        </Stack>
                      )}
                      {drawerSelectedModel.base_station_manifest.profile_requirement === 'required' && (
                        <SimpleGrid cols={{ base: 1, sm: 2 }}>
                        {drawerSelectedModel.base_station_manifest.profile_fields.map((field) => (
                          <TextInput
                            key={field.path}
                            label={field.label}
                            description={field.description}
                            required={field.required}
                            placeholder={field.placeholder}
                            value={(draft.base_station_profile
                              ?? emptyBaseStationProfileDraft(
                                drawerSelectedModel.base_station_manifest!,
                              ))[field.path] ?? ''}
                            onChange={(event) => {
                              const value = event.currentTarget.value
                              setDrafts((prev) => ({
                                ...prev,
                                [category.key]: {
                                  ...prev[category.key],
                                  base_station_profile: {
                                    ...(prev[category.key]?.base_station_profile
                                      ?? emptyBaseStationProfileDraft(
                                        drawerSelectedModel.base_station_manifest!,
                                      )),
                                    [field.path]: value,
                                  },
                                },
                              }))
                            }}
                          />
                        ))}
                        </SimpleGrid>
                      )}
                    </Stack>
                  </Card>
                )}

                <Group justify="flex-end" mt="md">
                  <Button
                    variant="light"
                    color="indigo"
                    disabled={
                      !selectedLabProfileId
                      || !category.selectedModelId
                      || !category.connection.endpoint
                      || instrumentMutation.isPending
                    }
                    loading={syncLabBindingMutation.isPending}
                    onClick={() => {
                      if (!selectedLabProfileId) return
                      syncLabBindingMutation.mutate(category.key)
                    }}
                    title="同步的是已保存的型号、控制端点和驱动模式"
                  >
                    同步已保存配置到 {selectedLabProfile?.name ?? '当前 LabProfile'}
                  </Button>
                  <Button
                    variant="outline"
                    color="teal"
                    onClick={async () => {
                      showFeedback(category.key, 'success', '正在测试连接...')
                      try {
                        const target = diagnosticTargetFor(
                          category.key,
                          draft.endpoint || '',
                          category.connection.endpoint || '',
                        )
                        if (!target) return
                        const draftProtocol = draft.controller?.trim() || ''
                        const resp = await client.post(`/instruments/${category.key}/test-connection`, {
                          ...target,
                          protocol: draftProtocol || undefined,
                        })
                        const result = resp.data as { success: boolean; message: string; idn?: string; latency_ms?: number }
                        if (result.success) {
                          const extra = result.idn ? ` | IDN: ${result.idn}` : ''
                          const latency = result.latency_ms ? ` (${result.latency_ms}ms)` : ''
                          showFeedback(category.key, 'success', `✅ ${result.message}${latency}${extra}`)
                        } else {
                          showFeedback(category.key, 'error', `❌ ${result.message}`)
                        }
                      } catch (err: unknown) {
                        showFeedback(category.key, 'error', `测试失败: ${diagnosticErrorMessage(err)}`)
                      }
                    }}
                  >
                    测试连接
                  </Button>
                  <Button
                    color="brand"
                    onClick={() => handleSaveConnection(category.key)}
                    loading={instrumentMutation.isPending}
                  >
                    保存配置
                  </Button>
                </Group>
                {feedback[category.key] ? (
                  <Alert
                    color={feedback[category.key].type === 'error' ? 'red' : 'green'}
                    variant="light"
                    radius="md"
                  >
                    {feedback[category.key].message}
                  </Alert>
                ) : null}

                {/* ─── SCPI 命令终端 ─── */}
                <Card withBorder radius="md" padding="md" mt="sm" bg="dark.8" style={{ border: '1px solid var(--mantine-color-dark-4)' }}>
                  <Stack gap="sm">
                    <Group justify="space-between" align="center">
                      <Text size="sm" fw={600} c="dimmed" style={{ fontFamily: 'monospace' }}>
                        ⌨ SCPI 命令终端
                      </Text>
                      <Button
                        size="xs"
                        variant="light"
                        color="cyan"
                        loading={scpiLoading[category.key]}
                        onClick={async () => {
                          const key = category.key
                          setScpiLoading(p => ({ ...p, [key]: true }))
                          try {
                            const target = diagnosticTargetFor(
                              key,
                              draft.endpoint || '',
                              category.connection.endpoint || '',
                            )
                            if (!target) return
                            const resp = await client.post(`/instruments/${key}/scpi-probe`, {
                              ...target,
                            })
                            setScpiProbeResults(p => ({ ...p, [key]: resp.data.results }))
                          } catch (err: unknown) {
                            showFeedback(key, 'error', `SCPI 探测失败: ${diagnosticErrorMessage(err)}`)
                          } finally {
                            setScpiLoading(p => ({ ...p, [key]: false }))
                            queryClient.invalidateQueries({ queryKey: scpiHistoryQueryKey(key) })
                          }
                        }}
                      >
                        🔍 运行诊断命令
                      </Button>
                    </Group>

                    {/* 诊断结果表格 */}
                    {scpiProbeResults[category.key]?.length ? (
                      <Table
                        striped
                        highlightOnHover
                        withTableBorder
                        fz="xs"
                        style={{ fontFamily: 'monospace' }}
                      >
                        <Table.Thead>
                          <Table.Tr>
                            <Table.Th w={140}>命令</Table.Th>
                            <Table.Th>响应</Table.Th>
                            <Table.Th w={70} ta="right">耗时</Table.Th>
                            <Table.Th w={50} ta="center">状态</Table.Th>
                          </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                          {scpiProbeResults[category.key].map((r, i) => (
                            <Table.Tr key={i}>
                              <Table.Td fw={600} c="cyan">{r.command}</Table.Td>
                              <Table.Td c={r.success ? undefined : 'red'} style={{ wordBreak: 'break-all' }}>
                                {r.success ? r.response : r.error}
                              </Table.Td>
                              <Table.Td ta="right" c="dimmed">{r.latency_ms}ms</Table.Td>
                              <Table.Td ta="center">{r.success ? '✅' : '❌'}</Table.Td>
                            </Table.Tr>
                          ))}
                        </Table.Tbody>
                      </Table>
                    ) : null}

                    {/* 手动命令输入 */}
                    <Group gap="xs" align="flex-end">
                      <TextInput
                        placeholder="输入 SCPI 命令, 如: *IDN? 或 SYST:ERR?"
                        style={{ flex: 1, fontFamily: 'monospace' }}
                        size="xs"
                        value={scpiManualCmd[category.key] || ''}
                        onChange={(e) => setScpiManualCmd(p => ({ ...p, [category.key]: e.target.value }))}
                        onKeyDown={async (e) => {
                          if (e.key === 'Enter') {
                            const cmd = scpiManualCmd[category.key]?.trim()
                            if (!cmd) return
                            const key = category.key
                            const target = diagnosticTargetFor(
                              key,
                              draft.endpoint || '',
                              category.connection.endpoint || '',
                            )
                            if (!target) return
                            setScpiLoading(p => ({ ...p, [key]: true }))
                            try {
                              const resp = await client.post(`/instruments/${key}/scpi-command`, {
                                command: cmd, ...target,
                              })
                              const result = resp.data as ScpiResult
                              setScpiManualResults(p => ({
                                ...p, [key]: [...(p[key] || []), result],
                              }))
                              setScpiManualCmd(p => ({ ...p, [key]: '' }))
                            } catch (err: unknown) {
                              setScpiManualResults(p => ({
                                ...p, [key]: [...(p[key] || []), {
                                  command: cmd, success: false, error: diagnosticErrorMessage(err), latency_ms: 0,
                                }],
                              }))
                            } finally {
                              setScpiLoading(p => ({ ...p, [key]: false }))
                              queryClient.invalidateQueries({ queryKey: scpiHistoryQueryKey(key) })
                            }
                          }
                        }}
                      />
                      <Button
                        size="xs"
                        variant="filled"
                        color="cyan"
                        loading={scpiLoading[category.key]}
                        onClick={async () => {
                          const cmd = scpiManualCmd[category.key]?.trim()
                          if (!cmd) return
                          const key = category.key
                          const target = diagnosticTargetFor(
                            key,
                            draft.endpoint || '',
                            category.connection.endpoint || '',
                          )
                          if (!target) return
                          setScpiLoading(p => ({ ...p, [key]: true }))
                          try {
                            const resp = await client.post(`/instruments/${key}/scpi-command`, {
                              command: cmd, ...target,
                            })
                            const result = resp.data as ScpiResult
                            setScpiManualResults(p => ({
                              ...p, [key]: [...(p[key] || []), result],
                            }))
                            setScpiManualCmd(p => ({ ...p, [key]: '' }))
                          } catch (err: unknown) {
                            setScpiManualResults(p => ({
                              ...p, [key]: [...(p[key] || []), {
                                command: cmd, success: false, error: diagnosticErrorMessage(err), latency_ms: 0,
                              }],
                            }))
                          } finally {
                            setScpiLoading(p => ({ ...p, [key]: false }))
                            queryClient.invalidateQueries({ queryKey: scpiHistoryQueryKey(key) })
                          }
                        }}
                      >
                        发送
                      </Button>
                      {(scpiManualResults[category.key]?.length ?? 0) > 0 && (
                        <Button
                          size="xs"
                          variant="subtle"
                          color="gray"
                          onClick={() => setScpiManualResults(p => ({ ...p, [category.key]: [] }))}
                        >
                          清空
                        </Button>
                      )}
                    </Group>

                    {/* 手动命令历史 (本会话) */}
                    {(scpiManualResults[category.key]?.length ?? 0) > 0 && (
                      <Card withBorder padding="xs" radius="sm" bg="dark.9" style={{ maxHeight: 200, overflowY: 'auto' }}>
                        <Stack gap={4}>
                          {scpiManualResults[category.key].map((r, i) => (
                            <Group key={i} gap="xs" wrap="nowrap" style={{ fontFamily: 'monospace', fontSize: '12px' }}>
                              <Text span c="cyan" fw={600} style={{ whiteSpace: 'nowrap' }}>{'>'} {r.command}</Text>
                              <Text span c={r.success ? 'green.4' : 'red.4'} style={{ wordBreak: 'break-all' }}>
                                → {r.success ? (r.response ?? '(OK, no response)') : `ERROR: ${r.error}`}
                              </Text>
                              <Text span c="dimmed" style={{ whiteSpace: 'nowrap' }}>{r.latency_ms}ms</Text>
                            </Group>
                          ))}
                        </Stack>
                      </Card>
                    )}

                    <Divider my={4} />

                    {/* 跨会话持久化历史 (来自 diagnostic_runs) */}
                    <ScpiHistoryFeed categoryKey={category.key} />
                  </Stack>
                </Card>
              </Stack>
            </Stack>
          )
        })()}
      </Drawer>

      {/* HAL 模式切换器 */}
      <Card withBorder radius="md" padding="lg">
        <Group justify="space-between" align="center">
          <Stack gap={4}>
            <Group gap="sm" align="center">
              <Title order={4}>驱动模式</Title>
              <Badge
                color={halStatus?.mode === 'real' ? 'teal' : 'blue'}
                variant="light"
                size="lg"
              >
                {halStatus?.mode === 'real' ? '🔌 硬件连接' : '🧪 仿真模拟'}
              </Badge>
            </Group>
            <Text size="xs" c="dimmed">
              Mock 模式使用软件仿真驱动（开发调试）；Real 模式从数据库读取配置连接真实硬件。
              已激活 {halStatus?.driver_count ?? 0} 个驱动
              {halStatus?.active_drivers?.length ? `（${halStatus.active_drivers.join(', ')}）` : ''}
            </Text>
          </Stack>
          <Group gap="md" align="center">
            <SegmentedControl
              value={halStatus?.mode ?? 'mock'}
              onChange={handleHALSwitch}
              disabled={halSwitching}
              data={[
                { label: '🧪 Mock', value: 'mock' },
                { label: '🔌 Real', value: 'real' },
              ]}
            />
            <Button
              variant="light"
              color="brand"
              onClick={handleHALReload}
              loading={halReloading}
              title="重新初始化所有驱动 (改完仪器配置后必须点这个,新配置才生效)"
            >
              ↻ 重新加载驱动
            </Button>
          </Group>
        </Group>
        {feedback['__hal__'] ? (
          <Alert
            color={feedback['__hal__'].type === 'error' ? 'red' : 'green'}
            variant="light"
            radius="md"
            mt="sm"
          >
            {feedback['__hal__'].message}
          </Alert>
        ) : null}
      </Card>

      {isLoading && categories.length === 0 ? (
        <Card withBorder radius="md" padding="xl">
          <Text size="sm" c="gray.6">
            正在加载仪器配置...
          </Text>
        </Card>
      ) : null}
      {!isLoading && categories.length === 0 ? (
        <Card withBorder radius="md" padding="xl">
          <Text size="sm" c="gray.6">
            暂无仪器信息，请在后端添加型号。
          </Text>
        </Card>
      ) : null}
      {categories.map((category) => {
        const selectedModelInfo = category.models.find((model) => model.id === category.selectedModelId) ?? null

        return (
          <Card key={category.key} withBorder radius="md" padding="lg" style={{
            opacity: category.isActive === false ? 0.5 : 1,
            transition: 'opacity 0.3s ease',
            borderLeft: `4px solid ${category.isActive === false ? '#dee2e6' : '#2c77f5'}`
          }}>
            <Stack gap="md">
              <Group justify="space-between" align="center">
                <Group gap="sm" align="center">
                  <Title order={4}>{category.label}</Title>
                  {(category as any).usagePhase?.map((phase: string) => (
                    <Badge
                      key={phase}
                      size="sm"
                      variant="dot"
                      color={phase === 'calibration' ? 'orange' : 'teal'}
                    >
                      {phase === 'calibration' ? '校准' : '测试'}
                    </Badge>
                  ))}
                  <Badge variant="light" color={selectedModelInfo ? "indigo" : "gray"}>
                    {selectedModelInfo ? "已分配型号" : "槽位闲置"}
                  </Badge>
                </Group>
                
                <Group gap="md">
                  <Tooltip label={`Auto = 跟随全局 (当前: ${halStatus?.mode?.toUpperCase() || 'MOCK'})`} position="bottom">
                    <SegmentedControl
                      size="xs"
                      value={(category as any).driverMode || 'auto'}
                      onChange={async (val) => {
                        try {
                          await client.patch(`/instruments/${category.key}/driver-mode`, { mode: val })
                          queryClient.invalidateQueries({ queryKey: ['instruments', 'catalog'] })
                          const modeLabels: Record<string, string> = { auto: 'Auto', mock: 'Mock', real: 'Real' }
                          showFeedback(category.key, 'success', `✅ 驱动模式 → ${modeLabels[val] || val}`)
                        } catch (err: any) {
                          showFeedback(category.key, 'error', `切换失败: ${err.message}`)
                        }
                      }}
                      data={[
                        { label: '⚙️ Auto', value: 'auto' },
                        { label: '🧪 Mock', value: 'mock' },
                        { label: '🔌 Real', value: 'real' },
                      ]}
                      color={
                        (category as any).driverMode === 'real' ? 'teal'
                          : (category as any).driverMode === 'mock' ? 'orange'
                          : 'blue'
                      }
                      disabled={category.isActive === false}
                    />
                  </Tooltip>
                  <Switch
                    checked={category.isActive !== false}
                    color="teal"
                    onChange={async (e) => {
                      const newActive = e.currentTarget.checked
                      try {
                        await client.patch(`/instruments/${category.key}/active`, { isActive: newActive })
                        queryClient.invalidateQueries({ queryKey: ['instruments', 'catalog'] })
                        showFeedback(category.key, 'success', `✅ 已${newActive ? '启用' : '停用'} ${category.label}`)
                      } catch (err: any) {
                        showFeedback(category.key, 'error', `操作失败: ${err.message}`)
                      }
                    }}
                  />
                  <Button variant="light" size="sm" onClick={() => setEditingCategoryKey(category.key)}>
                    替换 / 配置实装
                  </Button>
                </Group>
              </Group>

              {/* View Display Area */}
              <Card withBorder radius="sm" padding="sm" bg="gray.0">
                {selectedModelInfo ? (
                  <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
                    <Stack gap={4}>
                      <Group justify="space-between">
                         <Text size="sm" c="dimmed">型号</Text>
                         <Badge color={instrumentStatusColor[selectedModelInfo.status]} variant="dot" size="xs">
                            {instrumentStatusLabel[selectedModelInfo.status]}
                         </Badge>
                      </Group>
                      <Text fw={600}>{selectedModelInfo.vendor} {selectedModelInfo.model}</Text>
                      <Text size="xs" c="gray.6">{selectedModelInfo.summary}</Text>
                    </Stack>
                    
                    <Stack gap={4}>
                      <Text size="sm" c="dimmed">互联</Text>
                      <Group gap="xs">
                        <Badge size="xs" variant="outline">{category.connection?.controller || 'Unknown'}</Badge>
                        <Text fw={500} size="sm">{category.connection?.endpoint || '未配置IP'}</Text>
                      </Group>
                      <Text size="xs" c="gray.6" truncate>{category.connection?.notes || '无备注'}</Text>
                    </Stack>
                  </SimpleGrid>
                ) : (
                  <Group justify="center" py="md">
                    <Text size="sm" c="dimmed">该槽位当前为空。请点击“配置实装”进行连接。</Text>
                  </Group>
                )}
              </Card>
            </Stack>
          </Card>
        )
      })}
    </Stack>
  )
}

type ProbeManagerProps = {
  onNavigate: (section: SectionKey) => void
}

function ProbeManager({ onNavigate }: ProbeManagerProps) {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['probes'],
    queryFn: fetchProbes,
    retry: 2,
    retryDelay: 1000,
  })

  const probes = useMemo(() => data?.probes ?? [], [data])
  // P1-57：LabProfile 选择收敛到全局上下文（header 唯一选择器），
  // 本页只读 —— 原来这里的页面级 selectedLabProfileId 是三套平行真值之一。
  const { selectedLabProfileId } = useOperationalLab()

  // 暗室 id→name 映射: probe_number 按 chamber 局部编号 (1..N), 全局标识 = 暗室名 + #探头号。
  // 只精确拉取 probes 实际引用的 chamber (按 id), 不受暗室总数/分页 (默认 limit 20) 影响。
  const referencedChamberIds = useMemo(
    () => [...new Set(probes.map((p) => p.chamber_config_id).filter((x): x is string => !!x))],
    [probes],
  )
  const chamberQueries = useQueries({
    queries: referencedChamberIds.map((id) => ({
      queryKey: ['chamber', id],
      queryFn: () => fetchChamber(id),
      staleTime: 5 * 60 * 1000,
    })),
  })
  const chamberNameById = useMemo(
    () => Object.fromEntries(
      chamberQueries
        .map((q) => q.data)
        .filter((c): c is NonNullable<typeof c> => !!c)
        .map((c) => [c.id, c.name] as [string, string]),
    ),
    [chamberQueries],
  )
  // 所选 LabProfile 绑定的当前暗室（与 ChamberConfigCard 共用精确到 lab id 的缓存键）。
  // Bug 修复 (2026-06-07): 此前总览表/3D 布局/系统信息计数都用全量 probes, 选暗室不起作用
  // (列出所有暗室探头); 现按 lab 绑定暗室过滤，未选/解析失败时关闭数据与写入口。
  const {
    data: activeChamberData,
    isLoading: isActiveChamberLoading,
    isError: isActiveChamberError,
    error: activeChamberError,
  } = useQuery({
    queryKey: ['chamber', 'active', selectedLabProfileId],
    queryFn: () => fetchActiveChamber(selectedLabProfileId ?? undefined),
    enabled: !!selectedLabProfileId,
    retry: 1,
  })
  const activeChamber = (
    selectedLabProfileId && !isActiveChamberLoading && !isActiveChamberError
      ? activeChamberData
      : undefined
  )
  const activeChamberId = activeChamber?.id
  const displayedProbes = useMemo(
    () => (activeChamberId ? probes.filter((p) => p.chamber_config_id === activeChamberId) : []),
    [probes, activeChamberId],
  )

  const probeLabel = (probe: typeof probes[number]): string => {
    const cn = probe.chamber_config_id ? chamberNameById[probe.chamber_config_id] : undefined
    return cn ? `${cn} #${probe.probe_number}` : `#${probe.probe_number} ${probe.name ?? ''}`
  }

  // Helper functions to format probe data for display
  const formatRing = (ring: number): string => {
    const ringNames: Record<number, string> = { 1: '内层 Ring-1', 2: '中层 Ring-2', 3: '外层 Ring-3', 4: '顶层 Ring-4' }
    return ringNames[ring] || `Ring-${ring}`
  }

  const formatPosition = (pos: { azimuth: number; elevation: number; radius: number }): string => {
    return `Az:${pos.azimuth}° El:${pos.elevation}° R:${pos.radius}m`
  }

  const [selectedId, setSelectedId] = useState<string>('')
  const [formState, setFormState] = useState<ProbeFormState>({
    ring: 1,
    polarization: 'V',
    position: { azimuth: 0, elevation: 0, radius: 1.5 },
    is_active: true,
  })
  const [feedback, setFeedback] = useState<string>('')
  const [fileError, setFileError] = useState<string>('')
  const feedbackTimerRef = useRef<number | null>(null)
  const [newProbe, setNewProbe] = useState<Partial<ProbeType>>({
    id: generateProbeId(probes),
    probe_number: probes.length + 1,
    name: `Probe ${probes.length + 1}`,
    ring: 2,
    polarization: 'V/H',
    position: { azimuth: 0, elevation: 0, radius: 1.5 },
    is_active: true,
    is_connected: false,
    status: 'idle',
  })

  useEffect(() => {
    if (displayedProbes.length === 0) {
      setSelectedId('')
      return
    }
    if (!selectedId || !displayedProbes.some((probe) => probe.id === selectedId)) {
      setSelectedId(displayedProbes[0].id)
    }
  }, [displayedProbes, selectedId])

  const selectedProbe = displayedProbes.find((probe) => probe.id === selectedId) ?? null

  useEffect(() => {
    if (selectedProbe) {
      setFormState({
        ring: selectedProbe.ring,
        polarization: selectedProbe.polarization,
        position: selectedProbe.position,
        is_active: selectedProbe.is_active,
      })
    }
  }, [selectedProbe])

  useEffect(() => {
    return () => {
      if (feedbackTimerRef.current !== null) {
        window.clearTimeout(feedbackTimerRef.current)
      }
    }
  }, [])

  useEffect(() => {
    setNewProbe((prev) => {
      if (!probes.some((probe) => probe.id === prev.id)) return prev
      return {
        ...prev,
        id: generateProbeId(probes),
      }
    })
  }, [probes])

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<UpdateProbePayload> }) =>
      updateProbe(id, payload as UpdateProbePayload),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        ['probes'],
        (previous: { probes: ProbeType[] } | undefined): { probes: ProbeType[] } => {
          if (!previous) return { probes: [updated] }
          return {
            probes: previous.probes.map((probe) => (probe.id === updated.id ? updated : probe)),
          }
        },
      )
      setFeedback('变更已保存至本地状态。')
      if (feedbackTimerRef.current !== null) {
        window.clearTimeout(feedbackTimerRef.current)
      }
      feedbackTimerRef.current = window.setTimeout(() => setFeedback(''), 2000)
    },
    onError: () => {
      setFeedback('更新失败，请重试。')
      if (feedbackTimerRef.current !== null) {
        window.clearTimeout(feedbackTimerRef.current)
      }
      feedbackTimerRef.current = window.setTimeout(() => setFeedback(''), 2500)
    },
  })

  const createMutation = useMutation({
    mutationFn: createProbe,
    onSuccess: (created) => {
      queryClient.setQueryData(
        ['probes'],
        (previous: { probes: ProbeType[] } | undefined): { probes: ProbeType[] } => {
          if (!previous) return { probes: [created] }
          const filtered = previous.probes.filter((probe) => probe.id !== created.id)
          return { probes: [...filtered, created] }
        },
      )
      setSelectedId(created.id)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteProbe,
    onSuccess: (_, deletedId) => {
      let updatedList: ProbeType[] = []
      queryClient.setQueryData(
        ['probes'],
        (previous: { probes: ProbeType[] } | undefined): { probes: ProbeType[] } => {
          if (!previous) {
            updatedList = []
            return { probes: [] }
          }
          updatedList = previous.probes.filter((probe) => probe.id !== deletedId)
          return { probes: updatedList }
        },
      )
      setSelectedId((prev) => {
        if (updatedList.length === 0) return ''
        if (prev && updatedList.some((probe) => probe.id === prev)) return prev
        return updatedList[0].id
      })
    },
  })

  const replaceMutation = useMutation({
    // 批量替换按**当前激活暗室**作用域 (后端要求 chamber_config_id, 不再全局清空)。
    mutationFn: (incoming: Parameters<typeof replaceProbes>[0]) =>
      replaceProbes(incoming, activeChamberId as string),
    onSuccess: (result) => {
      // 作用域替换只返回该暗室的新探头; 全量 ['probes'] 列表需 refetch, 不能用局部结果覆盖
      queryClient.invalidateQueries({ queryKey: ['probes'] })
      const firstId = result.probes[0]?.id ?? ''
      setSelectedId(firstId)
      setFileError('')
    },
    onError: () => {
      setFileError('导入失败：请检查文件结构是否包含有效的 probes 数组。')
    },
  })

  const handleInputChange = (field: keyof ProbeFormState) => (event: ChangeEvent<HTMLInputElement>) => {
    const { value } = event.target
    setFormState((prev) => ({ ...prev, [field]: value }))
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!selectedProbe) return
    // 保存时自动根据仰角更新ring
    const calculatedRing = getRingFromElevation(formState.position.elevation)
    await updateMutation.mutateAsync({
      id: selectedProbe.id,
      payload: { ...formState, ring: calculatedRing },
    })
  }

  const handleReset = () => {
    if (!selectedProbe) return
    setFormState({
      ring: selectedProbe.ring,
      polarization: selectedProbe.polarization,
      position: selectedProbe.position,
      is_active: selectedProbe.is_active,
    })
  }

  const handleNewProbeChange =
    (field: keyof ProbeType) => (event: ChangeEvent<HTMLInputElement>) => {
      const { value } = event.target
      setNewProbe((prev) => ({ ...prev, [field]: value }))
    }

  const handleNewProbeSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!newProbe.id || !newProbe.id.trim()) return
    // Skip creating - these handlers are not used in current UI
    // await createMutation.mutateAsync(newProbe as ProbeType)
    setNewProbe({
      id: generateProbeId([...probes, newProbe as ProbeType]),
      probe_number: probes.length + 2,
      name: `Probe ${probes.length + 2}`,
      ring: 2,
      polarization: 'V/H',
      position: { azimuth: 0, elevation: 0, radius: 1.5 },
      is_active: true,
      is_connected: false,
      status: 'idle',
    })
  }

  const handleRemove = async (id: string) => {
    await deleteMutation.mutateAsync(id)
  }

  const handleExportLayout = () => {
    const payload = {
      version: '1.0',
      generatedAt: new Date().toISOString(),
      probes: displayedProbes.map((probe) => ({
        probe_number: probe.probe_number,
        name: probe.name,
        ring: probe.ring,
        polarization: probe.polarization,
        position: probe.position,
        is_active: probe.is_active,
        hardware_id: probe.hardware_id,
        channel_port: probe.channel_port,
        frequency_range_mhz: probe.frequency_range_mhz,
        max_power_dbm: probe.max_power_dbm,
        gain_db: probe.gain_db,
        notes: probe.notes,
      })),
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `probe-layout-${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const handleImportFile = async (file: File | null) => {
    if (!file) return
    if (!activeChamberId) {
      setFileError('请先在上方「当前激活配置」选择一个暗室，再导入布局（导入只替换该暗室的探头）。')
      return
    }
    try {
      const text = await file.text()
      const parsed = JSON.parse(text)
      const imported = Array.isArray(parsed?.probes) ? parsed.probes : parsed
      if (!Array.isArray(imported)) {
        throw new Error('无效的文件结构')
      }
      await replaceMutation.mutateAsync(imported)
    } catch {
      setFileError('导入失败：请确认JSON包含 { "probes": [...] } 结构。')
    }
  }

  const handleLoadDefault = async () => {
    if (!activeChamberId) {
      setFileError('请先在上方「当前激活配置」选择一个暗室，再加载默认布局（只替换该暗室的探头）。')
      return
    }
    try {
      const response = await fetch('/config/probes/default.json')
      if (!response.ok) throw new Error('请求失败')
      const data = await response.json()
      const imported = Array.isArray(data?.probes) ? data.probes : data
      if (!Array.isArray(imported)) {
        throw new Error('文件缺少有效 probes')
      }
      await replaceMutation.mutateAsync(imported)
    } catch {
      setFileError('加载默认布局失败，请稍后重试。')
    }
  }

  if (isLoading) {
    return (
      <Card withBorder radius="md" padding="xl">
        <Text size="sm" c="gray.6">
          正在加载探头数据…
        </Text>
      </Card>
    )
  }

  if (isError) {
    return (
      <Card withBorder radius="md" padding="xl">
        <Alert color="red" variant="light" title="加载探头数据失败">
          <Text size="sm">
            {error instanceof Error ? error.message : '未知错误'}
          </Text>
          <Text size="xs" c="dimmed" mt="sm">
            请检查后端服务是否正常运行，或刷新页面重试。
          </Text>
        </Alert>
      </Card>
    )
  }

  const calibrationTasks: Array<{
    title: string
    status: string
    description: string
    action: string
    target: SectionKey
  }> = [
      {
        title: '路径损耗校准',
        status: '待执行 · 预计耗时 35 分钟',
        description: '使用VNA逐通道测量S21，生成幅度/相位补偿矩阵。',
        action: '开始',
        target: 'systemCalibration',
      },
      {
        title: '静区均匀性验证',
        status: '计划中 · 截止 2024-10-21',
        description: '扫描网格 41×41 点，目标幅度波纹 ≤ 1 dB、相位 ≤ 10°。',
        action: '排程',
        target: 'systemCalibration',
      },
      {
        title: '功率放大器线性化',
        status: '进行中 · 62%',
        description: '校准功放增益与相位响应，生成数字预失真系数。',
        action: '查看',
        target: 'systemCalibration',
      },
      {
        title: '探头互耦补偿',
        status: '已完成 · 2024-10-15',
        description: '已更新互耦矩阵版本 v1.3，用于虚拟路测权重修正。',
        action: '报告',
        target: 'results',
      },
    ]

  return (
    <Stack gap="xl">
      {/* 暗室配置卡片 - CAL-00.1 新增 */}
      <ChamberConfigCard onNavigate={(s) => onNavigate(s as SectionKey)} />

      <Card withBorder radius="md" padding="xl">
        <Stack gap="md">
          <Group justify="space-between" align="flex-start">
            <Stack gap={2}>
              <Title order={3}>探头配置文件</Title>
              <Text size="xs" c="dimmed">
                导入/加载默认只替换当前暗室
                {activeChamber ? `「${activeChamber.name}」` : '（未选）'}
                的探头，不影响其它暗室
              </Text>
            </Stack>
            <Group gap="sm">
              <Button variant="subtle" onClick={handleExportLayout} disabled={!activeChamberId}>
                导出当前布局
              </Button>
              <FileButton onChange={handleImportFile} accept="application/json">
                {(props) => (
                  <Button variant="subtle" {...props} loading={replaceMutation.isPending} disabled={!activeChamberId}>
                    导入布局到当前暗室
                  </Button>
                )}
              </FileButton>
              <Button
                color="brand"
                onClick={handleLoadDefault}
                loading={replaceMutation.isPending}
                disabled={!activeChamberId}
              >
                加载默认布局到当前暗室
              </Button>
            </Group>
          </Group>
          {fileError ? (
            <Alert color="red" variant="light" radius="md">
              {fileError}
            </Alert>
          ) : null}
        </Stack>
      </Card>

      {!selectedLabProfileId ? (
        <Alert color="yellow" title="请先选择 LabProfile">
          未解析出当前暗室时不展示跨暗室探头，也不允许修改。
        </Alert>
      ) : isActiveChamberLoading ? (
        <Alert color="blue">正在解析该 LabProfile 绑定的当前暗室…</Alert>
      ) : isActiveChamberError || !activeChamber ? (
        <Alert color="red" title="当前暗室不可用">
          {activeChamberError instanceof Error
            ? activeChamberError.message
            : '请先为该 LabProfile 绑定有效暗室。'}
        </Alert>
      ) : null}

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="xl">
        <Card withBorder radius="md" padding="xl" style={{ display: 'flex', flexDirection: 'column' }}>
          <Stack gap="md" style={{ flex: 1, minHeight: 0 }}>
            <Group justify="space-between" align="center">
              <Title order={3}>探头阵列总览</Title>
              <Badge variant="light" color="brand">
                {activeChamber ? `${activeChamber.name} · ${displayedProbes.length} 探头` : '未解析当前暗室'}
              </Badge>
            </Group>
            <Box style={{ flex: 1, overflow: 'auto', minHeight: 200 }}>
              <Table highlightOnHover withTableBorder stickyHeader>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>ID</Table.Th>
                    <Table.Th>环层</Table.Th>
                    <Table.Th>极化</Table.Th>
                    <Table.Th>坐标</Table.Th>
                    <Table.Th w={80}>操作</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {displayedProbes.map((probe) => (
                    <Table.Tr
                      key={probe.id}
                      bg={probe.id === selectedId ? 'brand.0' : undefined}
                      onClick={() => setSelectedId(probe.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <Table.Td>{probeLabel(probe)}</Table.Td>
                      <Table.Td>{formatRing(probe.ring)}</Table.Td>
                      <Table.Td>{probe.polarization}</Table.Td>
                      <Table.Td>{formatPosition(probe.position)}</Table.Td>
                      <Table.Td>
                        <Button
                          variant="subtle"
                          color="brand"
                          size="compact-sm"
                          onClick={(e) => {
                            e.stopPropagation()
                            setSelectedId(probe.id)
                          }}
                        >
                          查看
                        </Button>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Box>
          </Stack>
        </Card>

        <Stack gap="xl" style={{ alignSelf: 'stretch' }}>
          <Card withBorder radius="md" padding="xl" style={{ flex: 1 }}>
            <Stack gap="md">
              <Title order={3}>探头详细信息</Title>
              {selectedProbe ? (
                <Stack gap="sm">
                  <TextInput label="探头编号" value={probeLabel(selectedProbe)} readOnly />
                  <TextInput
                    label="探头名称"
                    value={formState.ring ? selectedProbe.name || '' : ''}
                    onChange={(e) => {
                      // Name is not in formState, handled separately
                    }}
                    readOnly
                  />
                  <Select
                    label="环层（快速编辑：选择后自动设置仰角）"
                    description={`当前仰角 ${formState.position.elevation}° → 自动归属 ${getRingLabel(getRingFromElevation(formState.position.elevation))}`}
                    value={String(getRingFromElevation(formState.position.elevation))}
                    onChange={(val) => {
                      const ring = Number(val) || 3
                      const centerElevation = getCenterElevationForRing(ring)
                      setFormState((prev) => ({
                        ...prev,
                        ring,
                        position: { ...prev.position, elevation: centerElevation },
                      }))
                    }}
                    data={RING_CONFIG.map(c => ({
                      value: String(c.ring),
                      label: `${c.label} (${c.minElevation}° ~ ${c.maxElevation}°)`,
                    }))}
                  />
                  <Select
                    label="极化"
                    value={formState.polarization}
                    onChange={(val) => setFormState((prev) => ({ ...prev, polarization: val || 'V' }))}
                    data={[
                      { value: 'V', label: '垂直极化 (V)' },
                      { value: 'H', label: '水平极化 (H)' },
                      { value: 'V/H', label: '双极化 (V/H)' },
                      { value: 'RHCP', label: '右旋圆极化 (RHCP)' },
                      { value: 'LHCP', label: '左旋圆极化 (LHCP)' },
                    ]}
                  />
                  <SimpleGrid cols={3}>
                    <NumberInput
                      label="方位角 (°)"
                      value={formState.position.azimuth}
                      onChange={(val) =>
                        setFormState((prev) => ({
                          ...prev,
                          position: { ...prev.position, azimuth: Number(val) || 0 },
                        }))
                      }
                      min={0}
                      max={360}
                    />
                    <NumberInput
                      label="仰角 (°)"
                      value={formState.position.elevation}
                      onChange={(val) =>
                        setFormState((prev) => ({
                          ...prev,
                          position: { ...prev.position, elevation: Number(val) || 0 },
                        }))
                      }
                      min={-90}
                      max={90}
                    />
                    <NumberInput
                      label="半径 (m)"
                      value={formState.position.radius}
                      onChange={(val) =>
                        setFormState((prev) => ({
                          ...prev,
                          position: { ...prev.position, radius: Number(val) || 1.5 },
                        }))
                      }
                      min={0.5}
                      max={5}
                      step={0.1}
                      decimalScale={2}
                    />
                  </SimpleGrid>
                  {/* 派生值显示 */}
                  <Paper withBorder p="sm" radius="sm" bg="gray.0">
                    <Text size="xs" c="dimmed" mb="xs">自动计算的派生值</Text>
                    <SimpleGrid cols={2}>
                      <TextInput
                        label="高度 z (m)"
                        description="r × sin(仰角)"
                        value={calculateDerivedValues(formState.position).height.toFixed(3)}
                        readOnly
                        size="sm"
                      />
                      <TextInput
                        label="水平半径 ρ (m)"
                        description="r × cos(仰角)"
                        value={calculateDerivedValues(formState.position).horizontalRadius.toFixed(3)}
                        readOnly
                        size="sm"
                      />
                    </SimpleGrid>
                  </Paper>
                  <TextInput label="状态" value={selectedProbe.status} readOnly />
                  <TextInput label="校准状态" value={selectedProbe.calibration_status} readOnly />
                  <Switch
                    label="是否激活"
                    checked={formState.is_active}
                    onChange={(event) => {
                      const checked = event.currentTarget.checked
                      setFormState((prev) => ({ ...prev, is_active: checked }))
                      
                      // 自动保存开关状态（不用单独点击底部的保存）
                      const calculatedRing = getRingFromElevation(formState.position.elevation)
                      updateMutation.mutate({
                        id: selectedProbe.id,
                        payload: { ...formState, ring: calculatedRing, is_active: checked },
                      })
                    }}
                  />
                  <Group justify="flex-end" mt="md">
                    <Button
                      variant="subtle"
                      onClick={() => {
                        setFormState({
                          ring: selectedProbe.ring,
                          polarization: selectedProbe.polarization,
                          position: selectedProbe.position,
                          is_active: selectedProbe.is_active,
                        })
                      }}
                    >
                      重置
                    </Button>
                    <Button
                      color="brand"
                      onClick={() => {
                        // 保存时自动根据仰角更新ring
                        const calculatedRing = getRingFromElevation(formState.position.elevation)
                        updateMutation.mutate({
                          id: selectedProbe.id,
                          payload: { ...formState, ring: calculatedRing },
                        })
                      }}
                      loading={updateMutation.isPending}
                    >
                      保存修改
                    </Button>
                  </Group>
                  {feedback && (
                    <Alert color="green" variant="light">
                      {feedback}
                    </Alert>
                  )}
                </Stack>
              ) : (
                <Text size="sm" c="gray.6">
                  请选择左侧列表中的探头以查看详细信息
                </Text>
              )}
            </Stack>
          </Card>

          <Card withBorder radius="md" padding="xl">
            <Stack gap="md">
              <Title order={3}>系统信息</Title>
              <Stack gap="sm">
                <Text size="sm" c="gray.7">
                  <strong>当前暗室:</strong> {activeChamber ? activeChamber.name : '未解析（已禁止跨暗室操作）'}
                </Text>
                <Text size="sm" c="gray.7">
                  <strong>探头总数:</strong> {displayedProbes.length} 个
                </Text>
                <Text size="sm" c="gray.7">
                  <strong>活动探头:</strong> {displayedProbes.filter(p => p.is_active).length} 个
                </Text>
                <Text size="sm" c="gray.7">
                  <strong>已校准:</strong>{' '}
                  {displayedProbes.filter(p => p.calibration_status === 'valid').length} 个
                </Text>
                <Alert color="yellow" variant="light" mt="md">
                  探头配置由后端初始化脚本管理。如需添加或修改探头配置，请联系系统管理员。
                </Alert>
              </Stack>
            </Stack>
          </Card>
        </Stack>
      </SimpleGrid>

      <Grid gutter="xl">
        <Grid.Col span={{ base: 12, xl: 7 }}>
          <Card withBorder radius="md" padding="xl" style={{ height: '100%' }}>
            <Stack gap="md">
              <Title order={3}>探头空间布局</Title>
              <ProbeLayoutView probes={displayedProbes} selectedId={selectedId} onSelect={setSelectedId} />
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, xl: 5 }}>
          <Card withBorder radius="md" padding="xl" style={{ height: '100%' }}>
            <Stack gap="md">
              <Title order={3}>校准任务队列</Title>
              <Stack gap="sm">
                {calibrationTasks.map((task) => (
                  <Paper key={task.title} withBorder radius="md" p="md">
                    <Group justify="space-between" align="flex-start">
                      <Stack gap={4} style={{ flex: 1 }}>
                        <Text fw={600}>{task.title}</Text>
                        <Text size="xs" c="gray.6">
                          {task.status}
                        </Text>
                        <Text size="sm" c="gray.6">
                          {task.description}
                        </Text>
                      </Stack>
                      <Button
                        variant="subtle"
                        size="compact-sm"
                        onClick={() => onNavigate(task.target)}
                      >
                        {task.action}
                      </Button>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}

type CaseFormState = {
  name: string
  category: string
  dut: string
  tags: string
  caseId: string
  description: string
}

type NewCaseFormState = {
  name: string
  category: string
  dut: string
  tags: string
  description: string
  blueprint: string[]
}

function createWaveSamples(length: number): number[] {
  const baseFrequency = 0.3 + Math.random() * 0.2
  const amplitude = 0.6 + Math.random() * 0.3
  return Array.from({ length }, (_, index) => {
    const phase = index * baseFrequency
    const noise = (Math.random() - 0.5) * 0.2
    return Math.sin(phase) * amplitude + noise
  })
}


type MonitoringProps = {
  logs: LogEntry[]
  setLogs: Dispatch<SetStateAction<LogEntry[]>>
  scenarioStatus: DemoRunStatus
  progress: DemoRunProgress
  executionMode: 'real' | 'mock'
  demoPlan?: DemoRunPlan
  onRestart: () => void
  onPause: () => void
  onResume: () => void
  onStop: () => void
}

function Monitoring({
  logs,
  setLogs,
  scenarioStatus,
  progress,
  executionMode,
  demoPlan,
  onRestart,
  onPause,
  onResume,
  onStop,
}: MonitoringProps) {
  const theme = useMantineTheme()
  const [waveform, setWaveform] = useState<number[]>(() => createWaveSamples(60))
  const [execStatus, setExecStatus] = useState<'running' | 'paused' | 'idle'>('running')
  const [powerLevel, setPowerLevel] = useState<number>(-20)
  const [interferenceMode, setInterferenceMode] = useState<'off' | 'awgn' | 'co-channel'>('off')
  const [wsConnected, setWsConnected] = useState<boolean>(false)
  const [isStreaming, setIsStreaming] = useState<boolean>(true)
  const [enabledLevels, setEnabledLevels] = useState<Record<LogLevel, boolean>>({
    INFO: true,
    WARN: true,
    DEBUG: true,
  })
  const [keyword, setKeyword] = useState<string>('')
  const [autoScroll, setAutoScroll] = useState<boolean>(true)
  const logFeedRef = useRef<HTMLDivElement | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const controlsDisabled = scenarioStatus === 'running'
  // ARCH-1 S4a: 时间线原先优先用 TestPlan 的步骤, 无计划才回落到演示夹具。
  // 计划链拆除后只剩演示夹具这一路。
  const hasPlanLoaded = Boolean(demoPlan)
  type TimelineRenderItem = {
    id: string
    title: string
    message: string
    offsetMs: number
    checkpoint?: { summary?: string }
  }
  const timelineItems = useMemo<TimelineRenderItem[]>(() => {
    if (demoPlan) {
      return demoPlan.timeline.map((event, index) => {
        const linkedStep =
          typeof event.stepIndex === 'number' && demoPlan.steps[event.stepIndex]
            ? demoPlan.steps[event.stepIndex]
            : null
        return {
          id: event.id ?? `timeline-${index}`,
          title: linkedStep ? `${event.stepIndex + 1}. ${linkedStep.title}` : `事件 ${index + 1}`,
          message: event.message,
          offsetMs: event.offsetMs,
          checkpoint: event.checkpoint,
        }
      })
    }
    return []
  }, [demoPlan])
  const timelineActiveIndex = useMemo(() => {
    if (timelineItems.length === 0) return 0
    // ARCH-1 S4a: 计划来源的时间线没了, 进度只按演示夹具的事件序号走。
    const index = progress.eventIndex < 0 ? 0 : Math.min(progress.eventIndex, timelineItems.length - 1)
    return index
  }, [timelineItems.length, progress.eventIndex])
  const startedAtText = progress.startedAt
    ? new Date(progress.startedAt).toLocaleTimeString('zh-CN', { hour12: false })
    : null
  const finishedAtText = progress.finishedAt
    ? new Date(progress.finishedAt).toLocaleTimeString('zh-CN', { hour12: false })
    : null

  useEffect(() => {
    if (scenarioStatus === 'running') {
      setExecStatus('running')
      setIsStreaming(true)
    } else if (scenarioStatus === 'paused') {
      setExecStatus('paused')
      setIsStreaming(false)
    } else if (scenarioStatus === 'completed') {
      setExecStatus('idle')
      setIsStreaming(false)
    } else if (scenarioStatus === 'idle') {
      setExecStatus('idle')
      setIsStreaming(false)
    }
  }, [scenarioStatus])

  useEffect(() => {
    /* 
    // WebSocket logic moved to useMonitoringWebSocket hook.
    // Temporarily disabled in App.tsx to prevent duplicate connections and conflicts.
    
    let wsUrl = `${window.location.origin.replace(/^http/, 'ws')}/api/v1/ws/monitoring`
    
    // Direct connection for localhost development to bypass Vite proxy issues
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      wsUrl = 'ws://192.168.77.10:8000/api/v1/ws/monitoring'
    }
 
    let isActive = true
 
    const connect = () => {
      if (!isActive) return
      const socket = new WebSocket(wsUrl)
      socketRef.current = socket
      // ... (rest of the logic commented out)
    }
    // connect() 
    */

    // Minimal cleanup to satisfy hooks rules if needed, or just empty effect
    return () => {
      // isActive = false
      // if (socketRef.current) socketRef.current.close()
    }
  }, [scenarioStatus])
  useEffect(() => {
    if (wsConnected && socketRef.current) {
      const payload = execStatus === 'running' ? { action: 'resume' } : { action: 'pause' }
      socketRef.current.send(JSON.stringify(payload))
    }
  }, [execStatus, wsConnected])

  useEffect(() => {
    if (!isStreaming || wsConnected) return undefined
    const timer = window.setInterval(() => {
      const sampleMessages = [
        '信道仿真器刷新多径权重。',
        'DUT 回传 ACK 丢失，准备重传。',
        '静区探测器返回幅度波纹 1.1 dB。',
        '转台保持 45°，等待下一步指令。',
        'PWG 平面波模式保持稳定。',
      ]
      const sampleLevels: Array<LogEntry['level']> = ['INFO', 'DEBUG', 'WARN']
      const now = new Date()
      const newLog: LogEntry = {
        id: `log-${Date.now()}`,
        timestamp: now.toLocaleTimeString('zh-CN', { hour12: false }),
        level: sampleLevels[Math.floor(Math.random() * sampleLevels.length)],
        message: sampleMessages[Math.floor(Math.random() * sampleMessages.length)],
      }
      setLogs((prev) => {
        const next = [...prev, newLog]
        return next.slice(-40)
      })
    }, 4000)
    return () => window.clearInterval(timer)
  }, [isStreaming, setLogs])

  useEffect(() => {
    if (!autoScroll) return
    const raf = window.requestAnimationFrame(() => {
      if (logFeedRef.current) {
        logFeedRef.current.scrollTop = logFeedRef.current.scrollHeight
      }
    })
    return () => window.cancelAnimationFrame(raf)
  }, [logs, autoScroll])

  useEffect(() => {
    setIsStreaming(execStatus === 'running')
  }, [execStatus])

  const handleClearLogs = () => {
    setLogs([])
  }

  const handleToggleLevel = (level: LogLevel) => {
    setEnabledLevels((prev) => ({ ...prev, [level]: !prev[level] }))
  }

  useEffect(() => {
    if (execStatus !== 'running' || wsConnected) return undefined
    const timer = window.setInterval(() => {
      setWaveform((prev) => {
        const next = [...prev.slice(3), ...createWaveSamples(3)]
        return next
      })
    }, 1200)
    return () => window.clearInterval(timer)
  }, [execStatus, wsConnected])

  const filteredLogs = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase()
    return logs.filter((log) => {
      if (!enabledLevels[log.level]) return false
      if (!normalizedKeyword) return true
      return (
        log.message.toLowerCase().includes(normalizedKeyword) ||
        log.timestamp.toLowerCase().includes(normalizedKeyword) ||
        log.level.toLowerCase().includes(normalizedKeyword)
      )
    })
  }, [enabledLevels, keyword, logs])
  const waveformPath = useMemo(() => {
    if (waveform.length === 0) return ''
    const width = 600
    const height = 200
    return waveform
      .map((value, index) => {
        const x = (index / (waveform.length - 1)) * width
        const y = height / 2 - value * (height / 2.2)
        return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
      })
      .join(' ')
  }, [waveform])

  const handleTaskStart = () => {
    if (!hasPlanLoaded) return
    if (execStatus === 'running') return

    // If currently paused, resume execution
    if (execStatus === 'paused') {
      setExecStatus('running')
      setIsStreaming(true)
      onResume()
      return
    }

    // ARCH-1 S4a: 原先若有计划则走 onPlanExecute 真执行, 否则演示回放。
    // 计划链拆除后这里只做演示回放; 真执行的正门在测试用例库 (S1)。
    setExecStatus('running')
    setIsStreaming(true)
    onRestart()
  }

  const handlePause = () => {
    if (!hasPlanLoaded) return
    setExecStatus('paused')
    setIsStreaming(false)
    onPause()
  }

  const handleStop = () => {
    if (!hasPlanLoaded) return
    setExecStatus('idle')
    setIsStreaming(false)
    onStop()
  }

  const handleResumeLogs = () => {
    if (!hasPlanLoaded) return
    setExecStatus('running')
    setIsStreaming(true)
  }

  return (
    <Stack gap="xl">
      {/* Phase 2.7: 差异化的测试执行监控 - 始终显示 */}
      {/* ARCH-1 S4a: 计划名与"第几步/共几步"来自 TestPlan, 随计划链删除。
          这个卡片本身(实时指标)不依赖计划, 保留。 */}
      <ExecutionMetricsCard
        expectedRanges={{
          throughput: { min: 140, max: 160 },
          snr: { min: 23, max: 27 },
          eirp: { min: 43, max: 47 },
          temperature: { min: 20, max: 25 },
        }}
      />

      <Grid gutter="xl">
        <Grid.Col span={12}>
          <Card withBorder radius="md" padding="xl">
            <Stack gap="lg">
              <Stack gap="xs">
                <Group justify="space-between" align="center">
                  <Title order={3}>执行控制</Title>
                  <Group gap="xs">
                    <Badge variant="light" color={executionMode === 'real' ? 'green' : 'gray'}>
                      {executionMode === 'real' ? '真实执行' : '模拟执行'}
                    </Badge>
                    <Badge
                      variant="light"
                      color={execStatus === 'running' ? 'green' : execStatus === 'paused' ? 'yellow' : 'gray'}
                    >
                      {execStatus === 'running' ? '运行中' : execStatus === 'paused' ? '已暂停' : '待命'}
                    </Badge>
                  </Group>
                </Group>
                <Text size="sm" c="gray.6">
                  演示回放 —— 真实测试请到「测试管理 → 测试用例库」执行用例。
                </Text>
                {startedAtText || finishedAtText ? (
                  <Group gap="sm" wrap="wrap">
                    {startedAtText ? (
                      <Text size="xs" c="gray.6">
                        开始时间：{startedAtText}
                      </Text>
                    ) : null}
                    {finishedAtText ? (
                      <Text size="xs" c="gray.6">
                        结束时间：{finishedAtText}
                      </Text>
                    ) : null}
                  </Group>
                ) : null}
              </Stack>
              <Stack gap="xs">
                <Text fw={600}>任务控制</Text>
                <Group gap="sm">
                  <Button
                    color="brand"
                    onClick={handleTaskStart}
                    disabled={execStatus === 'running' || !hasPlanLoaded}
                  >
                    开始
                  </Button>
                  <Button
                    variant="outline"
                    color="gray"
                    onClick={handlePause}
                    disabled={execStatus !== 'running' || !hasPlanLoaded}
                  >
                    暂停
                  </Button>
                  <Button
                    variant="outline"
                    color="red"
                    onClick={handleStop}
                    disabled={execStatus === 'idle' || !hasPlanLoaded}
                  >
                    停止
                  </Button>
                </Group>
              </Stack>
              <Stack gap="xs">
                <Text fw={600}>输出功率</Text>
                <Slider
                  value={powerLevel}
                  onChange={setPowerLevel}
                  min={-60}
                  max={20}
                  step={1}
                  disabled={controlsDisabled}
                />
                <Group justify="space-between">
                  <Text size="xs" c="gray.6">
                    范围 -60 dBm ~ 20 dBm
                  </Text>
                  <Text fw={600}>{powerLevel.toFixed(0)} dBm</Text>
                </Group>
              </Stack>
              <Stack gap="xs">
                <Text fw={600}>干扰注入</Text>
                <SegmentedControl
                  value={interferenceMode}
                  onChange={(value) => setInterferenceMode(value as typeof interferenceMode)}
                  data={[
                    { label: '关闭', value: 'off' },
                    { label: 'AWGN', value: 'awgn' },
                    { label: '同频干扰', value: 'co-channel' },
                  ]}
                  disabled={controlsDisabled}
                />
              </Stack>
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>
      <Grid gutter="xl">
        <Grid.Col span={{ base: 12, xl: 6 }}>
          <Card withBorder radius="md" padding="xl">
            <Stack gap="md">
              <Group justify="space-between" align="center">
                <Title order={3}>实时波形</Title>
                <Text size="sm" c="gray.6">
                  干扰模式：{interferenceMode === 'off' ? '关闭' : interferenceMode.toUpperCase()}
                </Text>
              </Group>
              <Box
                style={{
                  borderRadius: theme.radius.md,
                  border: `1px solid ${theme.colors.dark[4]}`,
                  backgroundColor: theme.colors.dark[6],
                  overflow: 'hidden',
                }}
              >
                <svg width="100%" height="200" viewBox="0 0 600 200" preserveAspectRatio="none">
                  <rect x="0" y="0" width="600" height="200" fill={theme.colors.dark[7]} />
                  <path d={waveformPath} fill="none" stroke={theme.colors.brand[5]} strokeWidth={2} />
                </svg>
              </Box>
              <Group gap="lg">
                <Text size="sm" c="gray.6">
                  执行状态：{execStatus === 'running' ? '运行中' : execStatus === 'paused' ? '已暂停' : '待命'}
                </Text>
                <Text size="sm" c="gray.6">
                  功率设定：{powerLevel.toFixed(0)} dBm
                </Text>
              </Group>
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, xl: 6 }}>
          <Card withBorder radius="md" padding="xl">
            <Stack gap="md">
              <Group justify="space-between" align="center">
                <Title order={3}>执行日志</Title>
                <Group gap="sm">
                  <Button
                    variant="outline"
                    size="compact-sm"
                    onClick={handlePause}
                    disabled={execStatus !== 'running' || !hasPlanLoaded}
                  >
                    暂停日志
                  </Button>
                  <Button
                    variant="outline"
                    size="compact-sm"
                    onClick={handleResumeLogs}
                    disabled={execStatus === 'running' || !hasPlanLoaded}
                  >
                    恢复
                  </Button>
                  <Button variant="outline" size="compact-sm" color="red" onClick={handleClearLogs}>
                    清空
                  </Button>
                </Group>
              </Group>
              <Group gap="md" wrap="wrap">
                <Group gap="xs">
                  {(['INFO', 'DEBUG', 'WARN'] as LogLevel[]).map((level) => (
                    <Checkbox
                      key={level}
                      label={level}
                      checked={enabledLevels[level]}
                      onChange={() => handleToggleLevel(level)}
                      size="xs"
                    />
                  ))}
                </Group>
                <TextInput
                  placeholder="搜索日志…"
                  value={keyword}
                  onChange={(event) => setKeyword(event.currentTarget.value)}
                  w={200}
                />
                <Switch
                  label="自动滚动"
                  checked={autoScroll}
                  onChange={(event) => setAutoScroll(event.currentTarget.checked)}
                />
              </Group>
              <ScrollArea h={260} type="auto" viewportRef={logFeedRef}>
                {filteredLogs.length === 0 ? (
                  <Paper withBorder radius="md" p="md" c="gray.6">
                    暂无日志，等待新数据…
                  </Paper>
                ) : (
                  <Stack gap="sm">
                    {filteredLogs.map((log) => (
                      <Paper
                        key={log.id}
                        withBorder
                        radius="md"
                        p="sm"
                        bg={theme.colors[logLevelColor[log.level]][0]}
                      >
                        <Group justify="space-between" align="center">
                          <Group gap="xs">
                            <Badge color={logLevelColor[log.level]} variant="filled" size="sm">
                              {log.level}
                            </Badge>
                            <Text size="xs" c="gray.7">
                              {log.timestamp}
                            </Text>
                          </Group>
                        </Group>
                        <Text size="sm" mt={4}>
                          {log.message}
                        </Text>
                      </Paper>
                    ))}
                  </Stack>
                )}
              </ScrollArea>
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>
      <Card withBorder radius="md" padding="xl">
        <Stack gap="md">
          <Group justify="space-between" align="center">
            <Title order={3}>执行时间线</Title>
            <Group gap="xs">
              <Badge variant="light" color={executionMode === 'real' ? 'green' : 'gray'}>
                {executionMode === 'real' ? '真实执行' : '模拟执行'}
              </Badge>
              <Badge
                variant="light"
                color={
                  progress.status === 'running'
                    ? 'green'
                    : progress.status === 'completed'
                      ? 'blue'
                      : 'gray'
                }
              >
                {progress.status === 'running'
                  ? '运行中'
                  : progress.status === 'completed'
                    ? '已完成'
                    : '待命'}
              </Badge>
            </Group>
          </Group>
          {!hasPlanLoaded || timelineItems.length === 0 ? (
            <Text size="sm" c="gray.6">
              尚未加载执行时间线，请先在“测试计划与编排”中启动一次执行。
            </Text>
          ) : (
            <Timeline active={timelineActiveIndex} bulletSize={16} lineWidth={2}>
              {timelineItems.map((event, index) => (
                <Timeline.Item
                  key={event.id ?? `timeline-${index}`}
                  title={event.title}
                  bullet={<Badge size="xs">{index + 1}</Badge>}
                >
                  <Text size="sm" c="gray.7">
                    {event.message}
                  </Text>
                  <Text size="xs" c="gray.5">
                    预计触发：{(event.offsetMs / 1000).toFixed(1)} 秒
                  </Text>
                  {event.checkpoint?.summary ? (
                    <Text size="xs" c="gray.5" mt={4}>
                      {event.checkpoint.summary}
                    </Text>
                  ) : null}
                </Timeline.Item>
              ))}
            </Timeline>
          )}
        </Stack>
      </Card>
    </Stack>
  )
}

// ARCH-1 S4a: 这里原有一个 `_Results` 组件 (零渲染死代码, 与 CLAUDE.md 记的
// `_TestConfig` 同类)。它引用 TestPlanDetail, 随计划链一并删除 —— 真正在用的
// 结果视图是 features/Reports/。

export default App
