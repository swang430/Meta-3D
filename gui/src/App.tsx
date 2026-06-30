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
import { appEventBus, type ExecutionStartEvent } from './lib/eventBus'
import {
  getTestQueue,
  startExecution as apiStartExecution,
  pauseExecution as apiPauseExecution,
  resumeExecution as apiResumeExecution,
  cancelExecution as apiCancelExecution,
  completeExecution as apiCompleteExecution,
} from './features/TestManagement/api/testManagementAPI'
import ProbeLayoutView from './components/ProbeLayoutView'
import { SystemCalibration } from './components/SystemCalibration'
import { TestManagement } from './features/TestManagement/TestManagement'
import { ReportsPage } from './features/Reports/pages/ReportsPage'
import { CommissioningSandbox } from './components/Commissioning'
import { DiagnosticsPage } from './features/Diagnostics/DiagnosticsPage'
import { DashboardCockpit } from './features/Dashboard'
import { TopologyEditor } from './features/TopologyEditor/TopologyEditor'
import { TopologyProfileEditor } from './features/TopologyProfileEditor'
import { LabProfileWizard } from './components/LabProfile/LabProfileWizard'
import { AssetProfilesPanel } from './components/AssetProfiles/AssetProfilesPanel'
import { ChannelWorkbench } from './features/ChannelWorkbench/ChannelWorkbench'
import { fetchLabProfiles } from './api/labProfileService'
import { ExecutionMetricsCard } from './features/Monitoring'
import ChartsDemoPage from './components/Charts/ChartsDemoPage'
import { ChamberConfigCard } from './components/ChamberConfigCard'
import { StandardChannelDefinitionCard } from './components/StandardChannelDefinitionCard'
import {
  appendPlanStep,
  createProbe,
  createTestPlan,
  createTestCaseFromPlan,
  createTestCase,
  deleteProbe,
  fetchDashboard,
  fetchDemoRunPlan,
  fetchMonitoringFeeds,
  fetchProbes,
  fetchChamber,
  fetchActiveChamber,
  fetchRecentTests,
  fetchReportTemplates,
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
  fetchSequenceLibrary,
  fetchTestCases,
  fetchTestPlan,
  fetchTestPlans,
  deleteTestCase,
  updateTestPlan,
  updateInstrumentCategory,
  replaceProbes,
  reorderPlanStep,
  reorderTestPlans,
  removePlanStep,
  deleteTestPlan,
  updateProbe,
} from './api/service'
import client from './api/client'
import { listDiagnosticRuns, type DiagnosticRunSummary } from './api/diagnosticService'
import type {
  DemoRunPlan,
  DemoRunResult,
  InstrumentsResponse,
  InstrumentStatus,
  MetricItem,
  SystemStatusItem,
  Probe as ProbeType,
  SequenceStep as SequenceStepType,
  TestCase,
  TestPlanDetail,
  TestPlanListResponse,
  TestPlanSummary,
  RecentTest,
  TestCasesResponse,
  UpdatePlanPayload,
  UpdateProbePayload,
  UpdateInstrumentPayload,
  ReorderSequencePayload,
  ReorderPlanQueuePayload,
} from './types/api'

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

type LiveHistoryEntry = RecentTest & {
  mode: 'mock' | 'real'
  source: 'live' | 'api'
  runName: string
  artifactPrefix: string
  reportName: string
  caseName: string
}

type RunEntry = LiveHistoryEntry & { statusLabel: string }

type EquipmentDraft = {
  modelId: string
  endpoint: string
  controller: string
  notes: string
  connection_params?: string
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
    description: '统一的测试计划管理与步骤编排系统，包含计划管理、步骤编排、执行队列和执行历史。',
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
  const [preferMockExecution, setPreferMockExecution] = useState<boolean>(true)
  const [executingPlanInfo, setExecutingPlanInfo] = useState<{ id: string; name: string } | null>(null)
  const [autoChainExecution, setAutoChainExecution] = useState<boolean>(false)
  const [executingPlanDetail, setExecutingPlanDetail] = useState<TestPlanDetail | null>(null)
  const [liveHistory, setLiveHistory] = useState<LiveHistoryEntry[]>([])
  const lastRecordedRunRef = useRef<number | null>(null)
  const executingModeRef = useRef<'mock' | 'real'>('mock')
  const [executingRunMeta, setExecutingRunMeta] = useState<RunMetadata | null>(null)
  const [lastRunMeta, setLastRunMeta] = useState<RunMetadata | null>(null)
  const syncPlanSummary = useCallback(
    (plan: TestPlanDetail) => {
      queryClient.setQueryData(['tests', 'plans', plan.id], { plan })
      queryClient.setQueryData(['tests', 'plans'], (previous: TestPlanListResponse | undefined) => {
        const summary = {
          id: plan.id,
          name: plan.name,
          caseId: plan.caseId,
          caseName: plan.caseName,
          status: plan.status,
          updatedAt: plan.updatedAt,
          owner: 'AutoLab',
        }
        if (!previous) {
          return { plans: [summary] }
        }
        const exists = previous.plans.some((item) => item.id === plan.id)
        const nextPlans = exists
          ? previous.plans.map((item) => (item.id === plan.id ? summary : item))
          : [summary, ...previous.plans]
        return { plans: nextPlans }
      })
    },
    [queryClient],
  )

  const { mutate: _mutatePlanStatus } = useMutation({
    mutationFn: ({ planId, status }: { planId: string; status: string }) =>
      updateTestPlan(planId, { status }),
    onSuccess: (result) => {
      if (!result?.plan) return
      syncPlanSummary(result.plan)
    },
  })

  const sectionDescriptor = useMemo(
    () => sections.find((item) => item.key === activeSection),
    [activeSection],
  )

  const lastProgressStatusRef = useRef<DemoRunStatus>(demoRunProgress.status)

  const { data: dashboardData, isLoading: isDashboardLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
  })

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

  const systemStatus = dashboardData?.systemStatus ?? []
  const hardwareOnline = useMemo(
    () => systemStatus.length > 0 && systemStatus.every((item) => !/离线|错误|断开/i.test(item.value)),
    [systemStatus],
  )
  const executionMode = hardwareOnline && !preferMockExecution ? 'real' : 'mock'

  useEffect(() => {
    if (!hardwareOnline && !preferMockExecution) {
      setPreferMockExecution(true)
    }
  }, [hardwareOnline, preferMockExecution])

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

  // fromEvent: if true, skip backend call and event emission (already done by caller)
  const handleDemoPause = useCallback((fromEvent = false) => {
    // Stop the timer
    if (timelineTimerRef.current !== null) {
      window.clearTimeout(timelineTimerRef.current)
      timelineTimerRef.current = null
    }
    demoRunStatusRef.current = 'paused'
    setDemoRunProgress((prev) => ({ ...prev, status: 'paused' }))

    // Update backend if there's an executing plan (skip if called from event handler)
    if (executingPlanInfo && !fromEvent) {
      // Use proper pause API
      apiPauseExecution(executingPlanInfo.id, { paused_by: '当前用户' })
        .then(() => {
          // Invalidate queries to sync UI
          queryClient.invalidateQueries({ queryKey: ['test-management', 'queue'] })
          queryClient.invalidateQueries({ queryKey: ['test-management', 'plans'] })
        })
        .catch(() => {
          // Revert on error
          demoRunStatusRef.current = 'running'
          setDemoRunProgress((prev) => ({ ...prev, status: 'running' }))
        })
      appEventBus.emit({ type: 'execution:pause', payload: { planId: executingPlanInfo.id } })
    }
  }, [executingPlanInfo, queryClient])

  // fromEvent: if true, skip backend call and event emission (already done by caller)
  const handleDemoStop = useCallback((fromEvent = false) => {
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

    // Update backend if there's an executing plan (skip if called from event handler)
    if (executingPlanInfo && !fromEvent) {
      // Use proper cancel API
      apiCancelExecution(executingPlanInfo.id, { cancelled_by: '当前用户' })
        .then(() => {
          // Invalidate queries to sync UI
          queryClient.invalidateQueries({ queryKey: ['test-management', 'queue'] })
          queryClient.invalidateQueries({ queryKey: ['test-management', 'plans'] })
        })
        .catch(() => {
          // Error handling - plan was already stopped, UI is correct
        })
      appEventBus.emit({ type: 'execution:stop', payload: { planId: executingPlanInfo.id } })
    }
    // Always clear local state
    if (fromEvent || executingPlanInfo) {
      setExecutingPlanInfo(null)
      setExecutingPlanDetail(null)
      setExecutingRunMeta(null)
    }
  }, [executingPlanInfo, queryClient])

  // Resume a paused execution
  const handleDemoResume = useCallback((fromEvent = false) => {
    demoRunStatusRef.current = 'running'
    setDemoRunProgress((prev) => ({ ...prev, status: 'running' }))

    // Update backend if there's an executing plan (skip if called from event handler)
    if (executingPlanInfo && !fromEvent) {
      apiResumeExecution(executingPlanInfo.id, { resumed_by: '当前用户' })
        .then(() => {
          queryClient.invalidateQueries({ queryKey: ['test-management', 'queue'] })
          queryClient.invalidateQueries({ queryKey: ['test-management', 'plans'] })
        })
        .catch(() => {
          // Revert on error
          demoRunStatusRef.current = 'paused'
          setDemoRunProgress((prev) => ({ ...prev, status: 'paused' }))
        })
      appEventBus.emit({ type: 'execution:start', payload: { planId: executingPlanInfo.id, planName: executingPlanInfo.name } })
    }
  }, [executingPlanInfo, queryClient])

  const handleExecutionPreferenceChange = useCallback((preferMock: boolean) => {
    setPreferMockExecution(preferMock)
  }, [])

  // fromEvent: if true, skip backend call (already done by QueueTab)
  const startPlanExecution = useCallback(
    (plan: TestPlanDetail, metadata: RunMetadata, fromEvent = false) => {
      executingModeRef.current = executionMode
      const snapshot: TestPlanDetail = { ...plan, status: 'running' }

      // Only call API if not triggered from event (to avoid duplicate calls)
      if (!fromEvent) {
        apiStartExecution(plan.id, { started_by: '当前用户' })
          .then(() => {
            // Invalidate queries to sync UI
            queryClient.invalidateQueries({ queryKey: ['test-management', 'queue'] })
            queryClient.invalidateQueries({ queryKey: ['test-management', 'plans'] })
          })
          .catch(() => {
            // Error handling
          })
      }

      syncPlanSummary(snapshot)
      setExecutingPlanInfo({ id: snapshot.id, name: metadata.runName || snapshot.name })
      setExecutingPlanDetail(snapshot)
      setExecutingRunMeta(metadata)
      setActiveSection('dashboard')

      // Set running status directly (handleDemoRunStart may return early if no demo plan)
      demoRunStatusRef.current = 'running'
      setDemoRunProgress({
        status: 'running',
        currentStepIndex: 0,
        eventIndex: -1,
        startedAt: Date.now(),
        finishedAt: null,
      })

      // Try to start demo run if data is available
      handleDemoRunStart()
    },
    [handleDemoRunStart, syncPlanSummary, executionMode, queryClient],
  )

  // Listen for execution:start events from TestManagement module
  useEffect(() => {
    const handleExecutionStart = (event: ExecutionStartEvent) => {
      const { planId, planName } = event.payload

      // Fetch plan detail and start execution
      queryClient
        .fetchQuery({
          queryKey: ['tests', 'plans', planId],
          queryFn: () => fetchTestPlan(planId),
        })
        .then((result) => {
          // Handle both { plan: ... } wrapper and direct plan object
          const plan = result?.plan ?? result
          if (plan && plan.id) {
            const metadata = {
              runName: `${planName}-${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}`,
              artifactPrefix: planName.replace(/[^A-Za-z0-9-_]+/g, '-'),
              caseName: (plan as TestPlanDetail).caseName ?? plan.name,
            }
            // fromEvent=true: QueueTab already called the backend API
            startPlanExecution(plan as TestPlanDetail, metadata, true)
          }
        })
        .catch(() => {
          // Silently fail - user will see the plan didn't start
        })
    }

    const unsubscribe = appEventBus.on('execution:start', handleExecutionStart)
    return unsubscribe
  }, [queryClient, startPlanExecution])

  // Listen for pause/stop events from TestManagement module
  useEffect(() => {
    const handlePauseEvent = () => {
      // fromEvent=true: backend already updated by QueueTab, just update local state
      handleDemoPause(true)
    }
    const handleStopEvent = () => {
      // fromEvent=true: backend already updated by QueueTab, just update local state
      handleDemoStop(true)
    }

    const unsubPause = appEventBus.on('execution:pause', handlePauseEvent)
    const unsubStop = appEventBus.on('execution:stop', handleStopEvent)

    return () => {
      unsubPause()
      unsubStop()
    }
  }, [handleDemoPause, handleDemoStop])

  useEffect(() => {
    if (lastProgressStatusRef.current === demoRunProgress.status) return
    lastProgressStatusRef.current = demoRunProgress.status
    if (demoRunProgress.status === 'completed' && executingPlanInfo) {
      const finishedPlanId = executingPlanInfo.id
      // Use proper complete API
      apiCompleteExecution(finishedPlanId)
        .then(() => {
          queryClient.invalidateQueries({ queryKey: ['test-management', 'queue'] })
          queryClient.invalidateQueries({ queryKey: ['test-management', 'plans'] })
        })
        .catch(() => {
          // Error handling
        })
      if (executingPlanDetail && executingPlanDetail.id === finishedPlanId) {
        syncPlanSummary({ ...executingPlanDetail, status: 'completed' })
      }
      setExecutingPlanDetail(null)
      if (
        demoRunProgress.finishedAt &&
        lastRecordedRunRef.current !== demoRunProgress.finishedAt &&
        executingPlanDetail &&
        executingRunMeta
      ) {
        lastRecordedRunRef.current = demoRunProgress.finishedAt
        const entry: LiveHistoryEntry = {
          id: `RUN-${demoRunProgress.finishedAt}`,
          name: executingRunMeta.runName,
          dut: executingPlanDetail.caseName ?? '未指定',
          result: demoResultCard?.verdict ?? '通过',
          date: new Date().toLocaleDateString('zh-CN'),
          mode: executingModeRef.current,
          source: 'live',
          runName: executingRunMeta.runName,
          artifactPrefix: executingRunMeta.artifactPrefix,
          reportName: `${executingRunMeta.artifactPrefix}-report.pdf`,
          caseName: executingPlanDetail.caseName ?? executingPlanDetail.name,
        }
        setLiveHistory((prev) => [entry, ...prev].slice(0, 20))
      }
      if (executingRunMeta) {
        setLastRunMeta(executingRunMeta)
        setExecutingRunMeta(null)
      }
      if (autoChainExecution) {
        const planList = queryClient.getQueryData(['tests', 'plans']) as TestPlanListResponse | undefined
        const nextSummary = planList?.plans.find(
          (plan) => plan.id !== finishedPlanId && plan.status === '待执行',
        )
        if (nextSummary) {
          queryClient
            .fetchQuery({
              queryKey: ['tests', 'plans', nextSummary.id],
              queryFn: () => fetchTestPlan(nextSummary.id),
            })
            .then((result) => {
              if (result?.plan) {
                startPlanExecution(
                  result.plan,
                  createDefaultRunMetadata(result.plan.name, result.plan.caseName ?? result.plan.name),
                )
              } else {
                setExecutingPlanInfo(null)
              }
            })
            .catch(() => {
              setExecutingPlanInfo(null)
            })
          return
        }
      }
      setExecutingPlanInfo(null)
    }
    if (demoRunProgress.status === 'idle') {
      setExecutingPlanInfo(null)
      setExecutingPlanDetail(null)
      setExecutingRunMeta(null)
    }
  }, [
    demoRunProgress.status,
    executingPlanInfo,
    autoChainExecution,
    queryClient,
    startPlanExecution,
    fetchTestPlan,
    executingPlanDetail,
    syncPlanSummary,
    demoRunProgress.finishedAt,
    demoResultCard,
    executionMode,
    executingRunMeta,
  ])

  useEffect(() => {
    return () => {
      if (timelineTimerRef.current !== null) {
        window.clearTimeout(timelineTimerRef.current)
      }
    }
  }, [])

  // Restore execution state from backend on app load
  useEffect(() => {
    const restoreExecutionState = async () => {
      try {
        const queueItems = await getTestQueue()
        // Find running or paused plan
        const activePlan = queueItems.find(
          (item) => item.test_plan.status === 'running' || item.test_plan.status === 'paused'
        )
        if (activePlan) {
          setExecutingPlanInfo({
            id: activePlan.test_plan.id,
            name: activePlan.test_plan.name,
          })
          // Set the demo run status based on plan status
          const status = activePlan.test_plan.status === 'running' ? 'running' : 'paused'
          demoRunStatusRef.current = status
          setDemoRunProgress((prev) => ({ ...prev, status }))
        }
      } catch {
        // Silently fail - not critical if we can't restore state
      }
    }
    restoreExecutionState()
  }, [])

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

  const sectionContent = useMemo(
    () =>
      renderSection(activeSection, {
        logs: logEntries,
        setLogs: setLogEntries,
        selectedResults: selectedResultIds,
        selectedResultCount: selectedResultIds.length,
        onResultToggle: handleResultToggle,
        setActiveSection,
        demoPlan: demoRunPlanData?.plan,
        demoProgress: demoRunProgress,
        onDemoStart: handleDemoRunStart,
        onDemoPause: handleDemoPause,
        onDemoResume: handleDemoResume,
        onDemoStop: handleDemoStop,
        demoMetrics,
        demoResult: demoResultCard,
        executionMode,
        hardwareOnline,
        systemStatus,
        onExecutionModeChange: handleExecutionPreferenceChange,
        onPlanExecute: startPlanExecution,
        executingPlan: executingPlanInfo,
        autoChainExecution,
        onAutoChainExecutionChange: setAutoChainExecution,
        executingPlanDetail,
        liveHistory,
        executingRunMeta,
        recentRunMeta: executingRunMeta ?? lastRunMeta,
      }),
    [
      activeSection,
      logEntries,
      selectedResultIds,
      handleResultToggle,
      setActiveSection,
      demoRunPlanData,
      demoRunProgress,
      handleDemoRunStart,
      handleDemoPause,
      handleDemoResume,
      handleDemoStop,
      demoMetrics,
      demoResultCard,
      executionMode,
      hardwareOnline,
      systemStatus,
      handleExecutionPreferenceChange,
      startPlanExecution,
      executingPlanInfo,
      autoChainExecution,
      executingPlanDetail,
      liveHistory,
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

          <Paper
            withBorder
            radius="lg"
            p="md"
            style={{
              background: isDark ? hexToRgba(theme.white, 0.035) : hexToRgba(theme.white, 0.88),
              borderColor: isDark ? theme.colors.dark[4] : hexToRgba(theme.colors.brand[4], 0.35),
              boxShadow: theme.shadows.md,
            }}
          >
            <Stack gap="sm">
              <Text fw={600} size="sm" c={isDark ? theme.colors.gray[2] : theme.colors.brand[7]}>
                系统快照
              </Text>
              <Divider color={isDark ? theme.colors.dark[4] : hexToRgba(theme.colors.brand[4], 0.4)} />
              <Stack gap={8}>
                {isDashboardLoading ? (
                  <Text size="xs" c={isDark ? theme.colors.gray[4] : theme.colors.gray[6]}>
                    数据加载中……
                  </Text>
                ) : systemStatus.length === 0 ? (
                  <Text size="xs" c={isDark ? theme.colors.gray[4] : theme.colors.gray[6]}>
                    暂无数据
                  </Text>
                ) : (
                  systemStatus.map((item) => (
                    <Paper
                      key={item.label}
                      withBorder
                      radius="md"
                      p="sm"
                      style={{
                        background: isDark
                          ? hexToRgba(theme.colors.dark[6], 0.65)
                          : hexToRgba(theme.colors.brand[0], 0.75),
                        borderColor: isDark ? theme.colors.dark[4] : hexToRgba(theme.colors.brand[3], 0.5),
                      }}
                    >
                      <Text size="xs" c={isDark ? theme.colors.gray[4] : theme.colors.gray[6]}>
                        {item.label}
                      </Text>
                      <Text fw={600} size="sm" c={isDark ? theme.white : theme.colors.brand[8]}>
                        {item.value}
                      </Text>
                      <Text size="xs" c={isDark ? theme.colors.gray[5] : theme.colors.gray[6]}>
                        {item.detail}
                      </Text>
                    </Paper>
                  ))
                )}
              </Stack>
            </Stack>
          </Paper>
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
  demoPlan?: DemoRunPlan
  demoProgress: DemoRunProgress
  onDemoStart: () => void
  onDemoPause: () => void
  onDemoStop: () => void
  onDemoResume: () => void
  demoMetrics: MetricItem[] | null
  demoResult: DemoRunResult | null
  executionMode: 'real' | 'mock'
  hardwareOnline: boolean
  systemStatus: SystemStatusItem[]
  onExecutionModeChange: (preferMock: boolean) => void
  onPlanExecute: (plan: TestPlanDetail, metadata: RunMetadata) => void
  executingPlan: { id: string; name: string } | null
  autoChainExecution: boolean
  onAutoChainExecutionChange: (value: boolean) => void
  executingPlanDetail: TestPlanDetail | null
  liveHistory: LiveHistoryEntry[]
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
      return <TestManagement />
    case 'results':
      return <ReportsPage />
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
              scenarioMetrics={payload.demoMetrics}
              scenarioStatus={payload.demoProgress.status}
              progress={payload.demoProgress}
              executionMode={payload.executionMode}
              executingPlan={payload.executingPlan}
              planDetail={payload.executingPlanDetail}
              demoPlan={payload.demoPlan}
              onRestart={payload.onDemoStart}
              onPause={payload.onDemoPause}
              onResume={payload.onDemoResume}
              onStop={payload.onDemoStop}
              onPlanExecute={payload.onPlanExecute}
              autoChainExecution={payload.autoChainExecution}
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

/**
 * 解析仪器端点字符串为 IP 和 Port
 * 支持格式:
 * - VISA: "TCPIP0::192.168.0.132::inst0::INSTR"
 * - VISA with port: "TCPIP0::192.168.0.132::5025::INSTR"
 * - IP:Port: "192.168.0.132:5025"
 * - Plain IP: "192.168.0.132"
 */
function parseEndpointToIpPort(endpoint: string): { ip?: string; port?: number } {
  const ep = endpoint.trim()
  if (!ep) return {}

  // VISA 资源字符串: TCPIP[n]::host[::port]::...::INSTR
  if (ep.toUpperCase().startsWith('TCPIP')) {
    const parts = ep.split('::')
    if (parts.length >= 2) {
      const ip = parts[1].trim()
      let port: number | undefined
      if (parts.length >= 3) {
        const p = parseInt(parts[2].trim(), 10)
        if (!isNaN(p) && p > 0 && p < 65536) port = p
      }
      return { ip, port }
    }
    return {}
  }

  // IP:Port 格式
  if (ep.includes(':')) {
    const lastColon = ep.lastIndexOf(':')
    const host = ep.slice(0, lastColon).trim()
    const p = parseInt(ep.slice(lastColon + 1).trim(), 10)
    if (!isNaN(p) && p > 0 && p < 65536) return { ip: host, port: p }
    return { ip: ep }
  }

  // 纯 IP
  return { ip: ep }
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
  const [opError, setOpError] = useState<string | null>(null)

  const addMutation = useMutation({
    mutationFn: () =>
      addChannelModel(categoryKey, {
        filename: newFilename.trim(),
        label: newLabel.trim() || undefined,
        description: newDescription.trim() || undefined,
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
              <Group justify="flex-end" gap="xs">
                <Button
                  size="xs"
                  variant="subtle"
                  onClick={() => {
                    setAddOpen(false)
                    setNewFilename('')
                    setNewLabel('')
                    setNewDescription('')
                    setOpError(null)
                  }}
                >
                  取消
                </Button>
                <Button
                  size="xs"
                  onClick={() => addMutation.mutate()}
                  loading={addMutation.isPending}
                  disabled={!newFilename.trim()}
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
  const { data, isLoading } = useQuery({
    queryKey: ['instruments', 'catalog'],
    queryFn: fetchInstrumentCatalog,
  })

  const categories = useMemo(() => data?.categories ?? [], [data])

    const [drafts, setDrafts] = useState<Record<string, EquipmentDraft>>({})
  const [editingCategoryKey, setEditingCategoryKey] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<Record<string, EquipmentFeedback>>({})
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
        next[category.key] = {
          modelId: previous?.modelId ?? (category.selectedModelId ?? ''),
          endpoint: previous?.endpoint ?? (category.connection.endpoint ?? ''),
          controller: previous?.controller ?? (category.connection.controller ?? ''),
          notes: previous?.notes ?? (category.connection.notes ?? ''),
          connection_params: previous?.connection_params ?? (category.connection.connection_params ? JSON.stringify(category.connection.connection_params, null, 2) : ''),
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
      setDrafts((prev) => ({
        ...prev,
        [updatedCategory.key]: {
          modelId: updatedCategory.selectedModelId ?? '',
          endpoint: updatedCategory.connection.endpoint ?? '',
          controller: updatedCategory.connection.controller ?? '',
          notes: updatedCategory.connection.notes ?? '',
        },
      }))
      showFeedback(variables.categoryKey, 'success', '配置已保存。')
    },
    onError: (_error, variables) => {
      showFeedback(variables.categoryKey, 'error', '保存失败，请重试。')
    },
  })

  const handleModelChange = useCallback(
    (categoryKey: string, modelId: string) => {
      setDrafts((prev) => {
        const current =
          prev[categoryKey] ?? ({ modelId: '', endpoint: '', controller: '', notes: '' } as EquipmentDraft)
        return {
          ...prev,
          [categoryKey]: { ...current, modelId },
        }
      })
      instrumentMutation.mutate({ categoryKey, payload: { modelId } })
    },
    [instrumentMutation],
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
      
      let parsedParams = undefined
      if (draft.connection_params) {
        try {
          parsedParams = JSON.parse(draft.connection_params)
        } catch (e) {
          showFeedback(categoryKey, 'error', 'JSON 配置格式无效')
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
            ...(parsedParams !== undefined ? { connection_params: parsedParams } : {})
          },
        },
      })
    },
    [drafts, instrumentMutation, showFeedback],
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
          <Text size="sm" c="gray.7">
            如果当前有测试计划正在运行，后端会拒绝并提示是否强制覆盖。
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

                <Group justify="flex-end" mt="md">
                  <Button
                    variant="outline"
                    color="teal"
                    onClick={async () => {
                      showFeedback(category.key, 'success', '正在测试连接...')
                      try {
                        const { ip: testIp, port: testPort } = parseEndpointToIpPort(draft.endpoint || '')
                        const draftProtocol = draft.controller?.trim() || ''
                        const resp = await client.post(`/instruments/${category.key}/test-connection`, {
                          ip: testIp,
                          port: testPort,
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
                      } catch (err: any) {
                        showFeedback(category.key, 'error', `测试失败: ${err.message}`)
                      }
                    }}
                  >
                    测试连接
                  </Button>
                  <Button
                    color="brand"
                    onClick={() => {
                       handleSaveConnection(category.key);
                       setEditingCategoryKey(null);
                    }}
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
                            const { ip: testIp, port: testPort } = parseEndpointToIpPort(draft.endpoint || '')
                            const resp = await client.post(`/instruments/${key}/scpi-probe`, {
                              ip: testIp, port: testPort,
                            })
                            setScpiProbeResults(p => ({ ...p, [key]: resp.data.results }))
                          } catch (err: any) {
                            showFeedback(key, 'error', `SCPI 探测失败: ${err.message}`)
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
                            const { ip: testIp, port: testPort } = parseEndpointToIpPort(draft.endpoint || '')
                            setScpiLoading(p => ({ ...p, [key]: true }))
                            try {
                              const resp = await client.post(`/instruments/${key}/scpi-command`, {
                                command: cmd, ip: testIp, port: testPort,
                              })
                              const result = resp.data as ScpiResult
                              setScpiManualResults(p => ({
                                ...p, [key]: [...(p[key] || []), result],
                              }))
                              setScpiManualCmd(p => ({ ...p, [key]: '' }))
                            } catch (err: any) {
                              setScpiManualResults(p => ({
                                ...p, [key]: [...(p[key] || []), {
                                  command: cmd, success: false, error: err.message, latency_ms: 0,
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
                          const { ip: testIp, port: testPort } = parseEndpointToIpPort(draft.endpoint || '')
                          setScpiLoading(p => ({ ...p, [key]: true }))
                          try {
                            const resp = await client.post(`/instruments/${key}/scpi-command`, {
                              command: cmd, ip: testIp, port: testPort,
                            })
                            const result = resp.data as ScpiResult
                            setScpiManualResults(p => ({
                              ...p, [key]: [...(p[key] || []), result],
                            }))
                            setScpiManualCmd(p => ({ ...p, [key]: '' }))
                          } catch (err: any) {
                            setScpiManualResults(p => ({
                              ...p, [key]: [...(p[key] || []), {
                                command: cmd, success: false, error: err.message, latency_ms: 0,
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
  // 选中/激活的暗室 (复用 ChamberConfigCard 的 ['chamber','active'] 查询: 在该卡片选暗室
  // 即激活, 这里读同一缓存 → 总览/布局/计数随之过滤)。
  // Bug 修复 (2026-06-07): 此前总览表/3D 布局/系统信息计数都用全量 probes, 选暗室不起作用
  // (列出所有暗室探头); 现按激活暗室过滤, 无激活暗室时回退全部。
  const { data: activeChamber } = useQuery({
    queryKey: ['chamber', 'active'],
    queryFn: fetchActiveChamber,
    retry: 1,
  })
  const activeChamberId = activeChamber?.id
  const displayedProbes = useMemo(
    () => (activeChamberId ? probes.filter((p) => p.chamber_config_id === activeChamberId) : probes),
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
      probes: probes.map((probe) => ({
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
              <Button variant="subtle" onClick={handleExportLayout}>
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

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="xl">
        <Card withBorder radius="md" padding="xl" style={{ display: 'flex', flexDirection: 'column' }}>
          <Stack gap="md" style={{ flex: 1, minHeight: 0 }}>
            <Group justify="space-between" align="center">
              <Title order={3}>探头阵列总览</Title>
              <Badge variant="light" color="brand">
                {activeChamber ? `${activeChamber.name} · ${displayedProbes.length} 探头` : `全部暗室 · ${displayedProbes.length} 探头`}
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
                  <strong>当前暗室:</strong> {activeChamber ? activeChamber.name : '全部暗室 (未选激活)'}
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

const sanitizeArtifactPrefix = (value: string) => value.replace(/[^A-Za-z0-9-_]+/g, '-')

const createDefaultRunMetadata = (planName: string, caseName?: string): RunMetadata => {
  const now = new Date()
  const pad = (num: number) => String(num).padStart(2, '0')
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  const runName = `${planName}-${stamp}`
  const artifactPrefix = sanitizeArtifactPrefix(runName)
  return { runName, artifactPrefix, caseName: caseName ?? planName }
}


type MonitoringProps = {
  logs: LogEntry[]
  setLogs: Dispatch<SetStateAction<LogEntry[]>>
  scenarioMetrics: MetricItem[] | null
  scenarioStatus: DemoRunStatus
  progress: DemoRunProgress
  executionMode: 'real' | 'mock'
  executingPlan: { id: string; name: string } | null
  planDetail: TestPlanDetail | null
  demoPlan?: DemoRunPlan
  onRestart: () => void
  onPause: () => void
  onResume: () => void
  onStop: () => void
  onPlanExecute: (plan: TestPlanDetail, metadata: RunMetadata) => void
  autoChainExecution: boolean
}

function Monitoring({
  logs,
  setLogs,
  scenarioMetrics,
  scenarioStatus,
  progress,
  executionMode,
  executingPlan,
  planDetail,
  demoPlan,
  onRestart,
  onPause,
  onResume,
  onStop,
  onPlanExecute,
  autoChainExecution,
}: MonitoringProps) {
  const theme = useMantineTheme()
  const { data: feedsData } = useQuery({
    queryKey: ['monitoring', 'feeds'],
    queryFn: fetchMonitoringFeeds,
  })

  const [metricFeeds, setMetricFeeds] = useState(feedsData?.feeds ?? [])
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
  const scenarioMetricsRef = useRef<MetricItem[] | null>(null)
  const controlsDisabled = scenarioStatus === 'running'
  const hasPlanLoaded = Boolean(planDetail || demoPlan)
  type TimelineRenderItem = {
    id: string
    title: string
    message: string
    offsetMs: number
    checkpoint?: { summary?: string }
  }
  const timelineItems = useMemo<TimelineRenderItem[]>(() => {
    if (planDetail && planDetail.steps && planDetail.steps.length > 0) {
      return planDetail.steps.map((step, index) => ({
        id: step.id ?? `plan-step-${index}`,
        title: `${index + 1}. ${step.title}`,
        message: step.description || step.meta || '执行该测试步骤',
        offsetMs: index * 6000,
        checkpoint: undefined,
      }))
    }
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
  }, [planDetail, demoPlan])
  const timelineActiveIndex = useMemo(() => {
    if (timelineItems.length === 0) return 0
    if (planDetail) {
      const index = progress.currentStepIndex < 0 ? 0 : Math.min(progress.currentStepIndex, timelineItems.length - 1)
      return index
    }
    const index = progress.eventIndex < 0 ? 0 : Math.min(progress.eventIndex, timelineItems.length - 1)
    return index
  }, [timelineItems.length, planDetail, progress.currentStepIndex, progress.eventIndex])
  const startedAtText = progress.startedAt
    ? new Date(progress.startedAt).toLocaleTimeString('zh-CN', { hour12: false })
    : null
  const finishedAtText = progress.finishedAt
    ? new Date(progress.finishedAt).toLocaleTimeString('zh-CN', { hour12: false })
    : null

  useEffect(() => {
    if (scenarioMetricsRef.current) return
    if (feedsData?.feeds) {
      setMetricFeeds(feedsData.feeds)
    }
  }, [feedsData])

  useEffect(() => {
    scenarioMetricsRef.current = scenarioMetrics
    if (scenarioMetrics) {
      setMetricFeeds(scenarioMetrics)
    }
  }, [scenarioMetrics])

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

    // If there's a real plan loaded and not yet started, use onPlanExecute
    if (planDetail) {
      const runName = `${planDetail.name}-${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}`
      const metadata: RunMetadata = {
        runName,
        artifactPrefix: planDetail.name.replace(/[^A-Za-z0-9-_]+/g, '-'),
        caseName: planDetail.caseName ?? planDetail.name,
      }
      onPlanExecute(planDetail, metadata)
      return
    }

    // Otherwise use demo run
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
      <ExecutionMetricsCard
        testPlanName={executingPlan?.name}
        currentStep={
          executingPlan && planDetail && planDetail.steps && planDetail.steps.length > 0
            ? {
              index: progress.currentStepIndex >= 0 ? progress.currentStepIndex : 0,
              total: planDetail.steps.length,
              title: planDetail.steps[Math.max(0, progress.currentStepIndex)]?.title,
            }
            : undefined
        }
        expectedRanges={{
          throughput: { min: 140, max: 160 },
          snr: { min: 23, max: 27 },
          quiet_zone_uniformity: { min: 0.7, max: 1.0 },
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
                    <Badge variant="light" color={autoChainExecution ? 'brand' : 'gray'}>
                      {autoChainExecution ? '自动执行已开' : '自动执行关闭'}
                    </Badge>
                  </Group>
                </Group>
                <Text size="sm" c="gray.6">
                  {executingPlan
                    ? `当前计划：${executingPlan.name}（${executingPlan.id}）`
                    : '尚未选择执行计划，请在“测试计划与编排”中触发执行。'}
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

type ResultsProps = {
  selected: string[]
  onToggle: (id: string) => void
  demoResult: DemoRunResult | null
  liveHistory: LiveHistoryEntry[]
  currentRunMeta: RunMetadata | null
  executingRunMeta: RunMetadata | null
  executingPlanDetail: TestPlanDetail | null
  currentExecutionMode: 'real' | 'mock'
}

function _Results({
  selected,
  onToggle,
  demoResult,
  liveHistory,
  currentRunMeta,
  executingRunMeta,
  executingPlanDetail,
  currentExecutionMode,
}: ResultsProps) {
  const { data: recentTestsData, isLoading: isRecentLoading } = useQuery({
    queryKey: ['tests', 'recent'],
    queryFn: fetchRecentTests,
  })
  const { data: reportTemplatesData, isLoading: isReportLoading } = useQuery({
    queryKey: ['reports', 'templates'],
    queryFn: fetchReportTemplates,
    enabled: false, // TEMP: Disabled - endpoint not implemented yet
    retry: false,
  })

  const recentTestsList = useMemo(
    () => recentTestsData?.recentTests ?? [],
    [recentTestsData],
  )
  const reportTemplates = useMemo(
    () => reportTemplatesData?.reportTemplates ?? [],
    [reportTemplatesData],
  )

  const templateOptions = useMemo(
    () => reportTemplates.map((item) => ({ label: `${item.name} (${item.format})`, value: item.id })),
    [reportTemplates],
  )

  const combinedHistory = useMemo(() => {
    const apiEntries: LiveHistoryEntry[] = recentTestsList.map((item) => ({
      ...item,
      mode: 'real',
      source: 'api',
      runName: item.name,
      artifactPrefix: sanitizeArtifactPrefix(item.name),
      reportName: `${sanitizeArtifactPrefix(item.name)}-report.pdf`,
      caseName: item.name,
    }))
    const seen = new Set<string>()
    const result: LiveHistoryEntry[] = []
      ;[...liveHistory, ...apiEntries].forEach((entry) => {
        if (seen.has(entry.id)) return
        seen.add(entry.id)
        result.push(entry)
      })
    return result
  }, [recentTestsList, liveHistory])

  const [showMock, setShowMock] = useState<boolean>(true)
  const [reportSelection, setReportSelection] = useState<Record<string, string>>({})

  const liveEntries = useMemo(
    () => combinedHistory.filter((item) => item.source === 'live'),
    [combinedHistory],
  )

  const filteredHistory = useMemo(
    () => combinedHistory.filter((item) => showMock || item.mode !== 'mock'),
    [combinedHistory, showMock],
  )

  const selectedDetails = useMemo(
    () => combinedHistory.filter((item) => selected.includes(item.id)),
    [selected, combinedHistory],
  )

  const currentAttachments = useMemo(() => {
    if (!demoResult) return []
    if (currentRunMeta) {
      return [
        { name: `${currentRunMeta.artifactPrefix}-report.pdf`, type: 'PDF', size: '—' },
        { name: `${currentRunMeta.artifactPrefix}-attachments.zip`, type: 'ZIP', size: '—' },
      ]
    }
    return demoResult.attachments
  }, [demoResult, currentRunMeta])

  const runEntries = useMemo<RunEntry[]>(() => {
    const entries: RunEntry[] = liveEntries.map((entry) => ({
      ...entry,
      statusLabel: entry.result ?? '完成',
    }))
    if (executingRunMeta && executingPlanDetail) {
      entries.unshift({
        id: `active-${executingRunMeta.runName}`,
        name: executingRunMeta.runName,
        dut: executingPlanDetail.caseName ?? executingPlanDetail.name,
        result: '执行中',
        date: new Date().toLocaleDateString('zh-CN'),
        mode: currentExecutionMode,
        source: 'live',
        runName: executingRunMeta.runName,
        artifactPrefix: executingRunMeta.artifactPrefix,
        reportName: `${executingRunMeta.artifactPrefix}-report.pdf`,
        caseName: executingRunMeta.caseName ?? executingPlanDetail.caseName ?? executingPlanDetail.name,
        statusLabel: '执行中',
      })
    }
    return entries
  }, [liveEntries, executingRunMeta, executingPlanDetail, currentExecutionMode])

  const handleReportGenerate = (testId: string) => {
    const templateId = reportSelection[testId]
    if (!templateId) return
    console.info(`生成报告：result=${testId}, template=${templateId}`)
  }

  return (
    <Stack gap="xl">
      {demoResult ? (
        <Card withBorder radius="md" padding="xl">
          <Stack gap="md">
            <Group justify="space-between" align="flex-start">
              <Stack gap={4}>
                <Title order={3}>当前测试结果</Title>
                <Text size="sm" c="gray.6">
                  {demoResult.summary}
                </Text>
                {currentRunMeta ? (
                  <Group gap="sm">
                    <Badge variant="light" color="brand">
                      执行：{currentRunMeta.runName}
                    </Badge>
                    <Badge variant="light" color="gray">
                      归档前缀：{currentRunMeta.artifactPrefix}
                    </Badge>
                  </Group>
                ) : null}
              </Stack>
              <Badge
                color={
                  demoResult.verdict === '通过'
                    ? 'green'
                    : demoResult.verdict === '失败'
                      ? 'red'
                      : 'yellow'
                }
                variant="filled"
              >
                {demoResult.verdict}
              </Badge>
            </Group>
            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
              <Stack gap="sm">
                <Text fw={600} size="sm">
                  关键指标概览
                </Text>
                <Stack gap="sm">
                  {demoResult.metrics.map((metric) => (
                    <Paper key={metric.label} withBorder radius="md" p="sm">
                      <Group justify="space-between" align="center">
                        <Text fw={600} size="sm">
                          {metric.label}
                        </Text>
                        <Badge
                          size="xs"
                          color={
                            metric.status === 'ok'
                              ? 'green'
                              : metric.status === 'warn'
                                ? 'yellow'
                                : 'red'
                          }
                          variant="light"
                        >
                          {metric.status === 'ok'
                            ? '符合'
                            : metric.status === 'warn'
                              ? '关注'
                              : '警告'}
                        </Badge>
                      </Group>
                      <Text size="xs" c="gray.6">
                        基线：{metric.baseline}
                      </Text>
                      <Text size="xs" c="gray.6">
                        实测：{metric.measured}
                      </Text>
                    </Paper>
                  ))}
                </Stack>
              </Stack>
              <Stack gap="sm">
                <Text fw={600} size="sm">
                  附件与建议
                </Text>
                <Stack gap="xs">
                  {currentAttachments.map((file) => (
                    <Badge key={file.name} variant="outline" color="brand">
                      {file.name} · {file.type} · {file.size}
                    </Badge>
                  ))}
                </Stack>
                <Stack gap="xs">
                  {demoResult.recommendations.map((item, index) => (
                    <Text key={index} size="sm" c="gray.6">
                      · {item}
                    </Text>
                  ))}
                </Stack>
                <Stack gap="sm">
                  <Text fw={600} size="sm">
                    运行测试例
                  </Text>
                  {runEntries.length === 0 ? (
                    <Text size="sm" c="gray.6">
                      暂无执行记录。
                    </Text>
                  ) : (
                    <Stack gap="xs">
                      {runEntries.map((entry) => (
                        <Paper key={entry.id} withBorder radius="md" p="sm">
                          <Group justify="space-between" align="center">
                            <Stack gap={2}>
                              <Text fw={600} size="sm">
                                {entry.runName}
                              </Text>
                              <Text size="xs" c="gray.6">
                                测试例：{entry.caseName}
                              </Text>
                            </Stack>
                            <Group gap="xs">
                              <Badge color={entry.mode === 'real' ? 'green' : 'gray'} variant="light">
                                {entry.mode === 'real' ? '真实' : '模拟'}
                              </Badge>
                              <Badge
                                color={
                                  entry.statusLabel === '执行中'
                                    ? 'yellow'
                                    : entry.statusLabel === '失败'
                                      ? 'red'
                                      : 'green'
                                }
                                variant="light"
                              >
                                {entry.statusLabel}
                              </Badge>
                            </Group>
                          </Group>
                          <Group gap="xs">
                            <Text size="xs" c="gray.6">
                              归档前缀：{entry.artifactPrefix}
                            </Text>
                            <Text size="xs" c="gray.6">
                              报告：{entry.reportName}
                            </Text>
                          </Group>
                        </Paper>
                      ))}
                    </Stack>
                  )}
                </Stack>
              </Stack>
            </SimpleGrid>
          </Stack>
        </Card>
      ) : null}

      <Card withBorder radius="md" padding="xl">
        <Stack gap="md">
          <Group justify="space-between" align="center">
            <Title order={3}>历史测试浏览</Title>
            <Group gap="md" align="center">
              <Switch
                label="显示模拟测试"
                checked={showMock}
                onChange={(event) => setShowMock(event.currentTarget.checked)}
              />
              <Text size="sm" c="gray.6">
                勾选记录以加入对比分析
              </Text>
            </Group>
          </Group>
          <ScrollArea h={360} type="auto">
            <Table highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={42} />
                  <Table.Th>编号</Table.Th>
                  <Table.Th>测试名称</Table.Th>
                  <Table.Th>DUT</Table.Th>
                  <Table.Th>状态</Table.Th>
                  <Table.Th>日期</Table.Th>
                  <Table.Th>模式</Table.Th>
                  <Table.Th>归档前缀</Table.Th>
                  <Table.Th>报告模板</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {isRecentLoading
                  ? Array.from({ length: 3 }).map((_, index) => (
                    <Table.Tr key={index}>
                      <Table.Td colSpan={9}>
                        <Text size="sm" c="gray.6">
                          加载历史记录…
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  ))
                  : filteredHistory.map((item) => (
                    <Table.Tr key={item.id}>
                      <Table.Td>
                        <Checkbox
                          aria-label={`选择 ${item.name}`}
                          checked={selected.includes(item.id)}
                          onChange={() => onToggle(item.id)}
                        />
                      </Table.Td>
                      <Table.Td>{item.runName ?? item.name}</Table.Td>
                      <Table.Td>{item.caseName ?? item.name}</Table.Td>
                      <Table.Td>{item.dut}</Table.Td>
                      <Table.Td>{item.result}</Table.Td>
                      <Table.Td>{item.date}</Table.Td>
                      <Table.Td>
                        <Badge color={item.mode === 'real' ? 'green' : 'gray'} variant="light">
                          {item.mode === 'real' ? '真实' : '模拟'}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Badge variant="outline" color="gray">
                          {item.artifactPrefix ?? item.name}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        {templateOptions.length === 0 ? (
                          <Text size="xs" c="gray.5">
                            暂无模板
                          </Text>
                        ) : (
                          <Group gap="xs">
                            <Select
                              data={templateOptions}
                              placeholder="选择模板"
                              size="xs"
                              w={160}
                              value={reportSelection[item.id] ?? null}
                              onChange={(value) =>
                                setReportSelection((prev) => ({
                                  ...prev,
                                  [item.id]: value ?? '',
                                }))
                              }
                            />
                            <Button
                              size="compact-xs"
                              variant="light"
                              disabled={!reportSelection[item.id]}
                              onClick={() => handleReportGenerate(item.id)}
                            >
                              生成
                            </Button>
                          </Group>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </Stack>
      </Card>

      <Grid gutter="xl">
        <Grid.Col span={{ base: 12, xl: 6 }}>
          <Card withBorder radius="md" padding="xl">
            <Stack gap="md">
              <Title order={3}>报告模板</Title>
              {isReportLoading ? (
                <Text size="sm" c="gray.6">
                  正在加载模板…
                </Text>
              ) : (
                <Stack gap="sm">
                  {reportTemplates.map((template) => (
                    <Paper key={template.id} withBorder radius="md" p="md">
                      <Group justify="space-between" align="flex-start">
                        <Stack gap={4}>
                          <Text fw={600}>{template.name}</Text>
                          <Text size="xs" c="gray.6">
                            #{template.id} · {template.format} · 更新于 {template.lastUpdated}
                          </Text>
                        </Stack>
                        <Button variant="subtle" size="compact-sm">
                          生成
                        </Button>
                      </Group>
                    </Paper>
                  ))}
                  {reportTemplates.length === 0 ? (
                    <Paper withBorder radius="md" p="md" c="gray.6">
                      暂无模板，请稍后添加。
                    </Paper>
                  ) : null}
                </Stack>
              )}
            </Stack>
          </Card>
        </Grid.Col>

        <Grid.Col span={{ base: 12, xl: 6 }}>
          <Card withBorder radius="md" padding="xl">
            <Stack gap="md">
              <Group justify="space-between" align="center">
                <Title order={3}>对比分析</Title>
                <Badge color="brand" variant="light">
                  已选 {selectedDetails.length}
                </Badge>
              </Group>
              {selectedDetails.length === 0 ? (
                <Paper withBorder radius="md" p="md" c="gray.6">
                  在左侧表格中至少选择两条记录以生成对比概要。
                </Paper>
              ) : (
                <Stack gap="sm">
                  {selectedDetails.map((item) => (
                    <Paper key={item.id} withBorder radius="md" p="sm">
                      <Stack gap={2}>
                        <Text fw={600}>{item.name}</Text>
                        <Group gap="sm">
                          <Badge variant="light">{item.dut}</Badge>
                          <Text size="xs" c="gray.6">
                            结果：{item.result}
                          </Text>
                        </Group>
                      </Stack>
                    </Paper>
                  ))}
                  <Group justify="flex-end" gap="sm">
                    <Button color="brand" disabled={selectedDetails.length < 2}>
                      生成对比图
                    </Button>
                    <Button variant="outline" color="gray" disabled={selectedDetails.length === 0}>
                      导出差异
                    </Button>
                  </Group>
                </Stack>
              )}
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}

export default App
