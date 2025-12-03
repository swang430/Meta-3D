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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
  Title,
  useMantineTheme,
  UnstyledButton,
  useMantineColorScheme,
  useComputedColorScheme,
} from '@mantine/core'
import './App.css'
import ProbeLayoutView from './components/ProbeLayoutView'
import { VirtualRoadTest } from './components/VirtualRoadTest'
import { SystemCalibration } from './components/SystemCalibration'
import { TestManagement } from './features/TestManagement/TestManagement'
import { ReportsPage } from './features/Reports/pages/ReportsPage'
import { RealtimeMetricsCard } from './components/RealtimeMetricsCard'
import { ExecutionMetricsCard } from './features/Monitoring'
import { useMonitoringWebSocket } from './hooks/useMonitoringWebSocket'
import ChartsDemoPage from './components/Charts/ChartsDemoPage'
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
  fetchRecentTests,
  fetchReportTemplates,
  fetchTestCaseDetail,
  fetchInstrumentCatalog,
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
import type {
  AlertItem,
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

type SectionKey = 'dashboard' | 'equipment' | 'probeManager' | 'testManagement' | 'monitoring' | 'results' | 'virtualRoadTest' | 'systemCalibration' | 'chartsDemo'

type ProbeFormState = Pick<ProbeType, 'ring' | 'polarization' | 'position'>

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
}

type EquipmentFeedback = {
  type: 'success' | 'error'
  message: string
}

type EquipmentMutationVariables = {
  categoryKey: string
  payload: UpdateInstrumentPayload
}

type DemoRunStatus = 'idle' | 'running' | 'completed'

type DemoRunProgress = {
  status: DemoRunStatus
  currentStepIndex: number
  eventIndex: number
  startedAt: number | null
  finishedAt: number | null
}

const sections: Array<{ key: SectionKey; label: string; description: string }> = [
  {
    key: 'dashboard',
    label: '主仪表板',
    description: '查看集成系统状态、运行中任务与关键告警概览。',
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
    key: 'testManagement',
    label: '测试管理',
    description: '统一的测试计划管理与步骤编排系统，包含计划管理、步骤编排、执行队列和执行历史。',
  },
  {
    key: 'monitoring',
    label: '实时监控',
    description: '在执行期间监控吞吐量、SNR、静区指标与执行日志。',
  },
  {
    key: 'results',
    label: '数据归档与报告',
    description: '浏览历史记录、对比结果，并一键生成标准化报告。',
  },
  {
    key: 'virtualRoadTest',
    label: '虚拟路测',
    description: '支持数字孪生、传导测试与OTA辐射测试的统一平台。',
  },
  {
    key: 'systemCalibration',
    label: '系统校准',
    description: '执行TRP/TIS校准、重复性测试、实验室间比对，管理校准证书与溯源。',
  },
  {
    key: 'chartsDemo',
    label: '📊 高级图表演示',
    description: '展示 Plotly.js 交互式图表：时间序列分析、统计对比、性能基准等。',
  },
]

const instrumentStatusColor: Record<InstrumentStatus, string> = {
  available: 'green',
  reserved: 'yellow',
  maintenance: 'orange',
  offline: 'gray',
}

const severityBadgeColor: Record<AlertItem['severity'], string> = {
  info: 'blue',
  warning: 'yellow',
  critical: 'red',
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

  const { mutate: mutatePlanStatus } = useMutation({
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

  const handleExecutionPreferenceChange = useCallback((preferMock: boolean) => {
    setPreferMockExecution(preferMock)
  }, [])

  const startPlanExecution = useCallback(
    (plan: TestPlanDetail, metadata: RunMetadata) => {
      executingModeRef.current = executionMode
      const snapshot: TestPlanDetail = { ...plan, status: '执行中' }
      mutatePlanStatus({ planId: plan.id, status: '执行中' })
      syncPlanSummary(snapshot)
      setExecutingPlanInfo({ id: snapshot.id, name: metadata.runName || snapshot.name })
      setExecutingPlanDetail(snapshot)
      setExecutingRunMeta(metadata)
      setActiveSection('monitoring')
      handleDemoRunStart()
    },
    [mutatePlanStatus, handleDemoRunStart, syncPlanSummary, executionMode],
  )

  useEffect(() => {
    if (lastProgressStatusRef.current === demoRunProgress.status) return
    lastProgressStatusRef.current = demoRunProgress.status
    if (demoRunProgress.status === 'completed' && executingPlanInfo) {
      const finishedPlanId = executingPlanInfo.id
      mutatePlanStatus({ planId: finishedPlanId, status: '已完成' })
      if (executingPlanDetail && executingPlanDetail.id === finishedPlanId) {
        syncPlanSummary({ ...executingPlanDetail, status: '已完成' })
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
    mutatePlanStatus,
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
        demoPlan: demoRunPlanData?.plan,
        demoProgress: demoRunProgress,
        onDemoStart: handleDemoRunStart,
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
      demoRunPlanData,
      demoRunProgress,
      handleDemoRunStart,
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
                <Group gap="xs" align="center">
                  <Title order={4} c={isDark ? theme.white : theme.colors.brand[8]}>
                    MIMO-OTA
                  </Title>
                  <Badge color="brand" radius="xl" variant="filled">
                    Meta-3D
                  </Badge>
                </Group>
                <Text size="sm" c={isDark ? theme.colors.gray[4] : theme.colors.gray[7]}>
                  软件定义静区 · 车规级实验室
                </Text>
              </Stack>
            </Paper>

            <ScrollArea type="auto" style={{ flex: 1, minHeight: 0 }} scrollbarSize={12}>
              <Stack gap="sm" pt="xs" pb="sm">
                {sections.map((item) => {
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
                    <UnstyledButton
                      key={item.key}
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
  demoPlan?: DemoRunPlan
  demoProgress: DemoRunProgress
  onDemoStart: () => void
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
      return <Dashboard selectedResultCount={payload.selectedResultCount} />
    case 'equipment':
      return <EquipmentManager />
    case 'probeManager':
      return <ProbeManager />
    case 'testManagement':
      return <TestManagement />
    case 'monitoring':
      return (
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
          autoChainExecution={payload.autoChainExecution}
        />
      )
    case 'results':
      return <ReportsPage />
    case 'virtualRoadTest':
      return <VirtualRoadTest />
    case 'systemCalibration':
      return <SystemCalibration />
    case 'chartsDemo':
      return <ChartsDemoPage />
    default:
      return null
  }
}

type DashboardProps = {
  selectedResultCount: number
}

function Dashboard({ selectedResultCount }: DashboardProps) {
  const { data: dashboardData, isLoading: isDashboardLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
  })
  const { data: probesData } = useQuery({
    queryKey: ['probes'],
    queryFn: fetchProbes,
  })
  const { data: testPlansSummary } = useQuery({
    queryKey: ['tests', 'plans'],
    queryFn: fetchTestPlans,
    enabled: false, // TEMP: Disabled until API path mismatch is fixed (/tests/plans vs /test-plans)
    retry: false,
  })
  const { data: recentTestsData, isLoading: isRecentLoading } = useQuery({
    queryKey: ['tests', 'recent'],
    queryFn: fetchRecentTests,
    enabled: false, // TEMP: Disabled - endpoint not implemented yet
    retry: false,
  })

  const liveMetrics = dashboardData?.liveMetrics ?? []
  const activeAlerts = dashboardData?.activeAlerts ?? []
  const probesCount = probesData?.probes.length ?? 0
  const planCount = testPlansSummary?.plans.length ?? 0
  const recentTestsList = useMemo(
    () => recentTestsData?.recentTests ?? [],
    [recentTestsData],
  )

  const summaryItems = [
    { label: '探头数量', value: probesCount.toString() },
    { label: '活动测试计划', value: planCount.toString() },
    { label: '活动告警', value: activeAlerts.length.toString() },
    { label: '已选对比', value: selectedResultCount.toString() },
  ]

  const quickActions = [
    { label: '新建测试计划', note: '基于模板快速创建完整序列' },
    { label: '执行静区校准', note: '触发自动路径/相位校准流程' },
    { label: '导出最新报告', note: '选择历史结果并生成PDF/HTML' },
  ]

  return (
    <Stack gap="xl">
      <Card withBorder radius="md" padding="lg">
        <Stack gap="sm">
          <Group justify="space-between">
            <Title order={3}>系统总览</Title>
            <Badge color="brand" variant="light">
              概览
            </Badge>
          </Group>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
            {summaryItems.map((item) => (
              <Stack key={item.label} gap={4}>
                <Text size="xs" c="gray.6">
                  {item.label}
                </Text>
                <Text fw={700} fz={28}>
                  {item.value}
                </Text>
              </Stack>
            ))}
          </SimpleGrid>
        </Stack>
      </Card>

      <Card withBorder radius="md" padding="lg">
        <Stack gap="md">
          <Title order={3}>运行中任务</Title>
          {isDashboardLoading ? (
            <Text size="sm" c="gray.6">
              数据加载中……
            </Text>
          ) : (
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
              {liveMetrics.map((metric) => (
                <Paper key={metric.label} p="md" radius="md" withBorder>
                  <Stack gap={4}>
                    <Text size="xs" c="gray.6">
                      {metric.label}
                    </Text>
                    <Group gap="xs">
                      <Text fw={700} fz="lg">
                        {metric.value}
                      </Text>
                      {metric.trend ? (
                        <Badge color="brand" variant="light" radius="sm">
                          {metric.trend}
                        </Badge>
                      ) : null}
                    </Group>
                  </Stack>
                </Paper>
              ))}
            </SimpleGrid>
          )}
        </Stack>
      </Card>

      <RealtimeMetricsCard debug={false} />

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="xl">
        <Card withBorder radius="md" padding="lg">
          <Stack gap="md">
            <Title order={3}>活动告警</Title>
            {isDashboardLoading && activeAlerts.length === 0 ? (
              <Text size="sm" c="gray.6">
                数据加载中……
              </Text>
            ) : activeAlerts.length === 0 ? (
              <Paper p="md" radius="md" withBorder>
                <Text fw={600}>暂无告警</Text>
                <Text size="sm" c="gray.6">
                  系统运行正常
                </Text>
              </Paper>
            ) : (
              <Stack gap="sm">
                {activeAlerts.map((alert) => (
                  <Paper key={alert.id} p="md" radius="md" withBorder>
                    <Group justify="space-between" align="flex-start">
                      <div>
                        <Text fw={600}>{alert.title}</Text>
                        <Text size="xs" c="gray.6">
                          #{alert.id} · {alert.timestamp}
                        </Text>
                      </div>
                      <Badge color={severityBadgeColor[alert.severity]} variant="light">
                        {alert.severity.toUpperCase()}
                      </Badge>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            )}
          </Stack>
        </Card>

        <Card withBorder radius="md" padding="lg">
          <Stack gap="md">
            <Title order={3}>快速操作</Title>
            <Stack gap="sm">
              {quickActions.map((action) => (
                <Button key={action.label} variant="light" color="brand" justify="space-between">
                  <Text fw={600}>{action.label}</Text>
                  <Text size="xs" c="gray.6">
                    {action.note}
                  </Text>
                </Button>
              ))}
            </Stack>
          </Stack>
        </Card>
      </SimpleGrid>

      <Card withBorder radius="md" padding="lg">
        <Stack gap="md">
          <Title order={3}>最近测试记录</Title>
          {isRecentLoading ? (
            <Text size="sm" c="gray.6">
              数据加载中……
            </Text>
          ) : (
            <Table striped highlightOnHover withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>执行</Table.Th>
                  <Table.Th>测试例</Table.Th>
                  <Table.Th>DUT</Table.Th>
                  <Table.Th>状态</Table.Th>
                  <Table.Th>日期</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {recentTestsList.map((item) => (
                  <Table.Tr key={item.id}>
                    <Table.Td>{item.id}</Table.Td>
                    <Table.Td>{item.name}</Table.Td>
                    <Table.Td>{item.dut}</Table.Td>
                    <Table.Td>{item.result}</Table.Td>
                    <Table.Td>{item.date}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Stack>
      </Card>
    </Stack>
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
  const [feedback, setFeedback] = useState<Record<string, EquipmentFeedback>>({})
  const feedbackTimers = useRef<Record<string, number>>({})

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
      instrumentMutation.mutate({
        categoryKey,
        payload: {
          connection: {
            endpoint: draft.endpoint || undefined,
            controller: draft.controller || undefined,
            notes: draft.notes || undefined,
          },
        },
      })
    },
    [drafts, instrumentMutation],
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

  return (
    <Stack gap="xl">
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
        const draft = drafts[category.key] ?? {
          modelId: category.selectedModelId ?? '',
          endpoint: category.connection.endpoint ?? '',
          controller: category.connection.controller ?? '',
          notes: category.connection.notes ?? '',
        }
        const selectedModel = category.models.find((model) => model.id === draft.modelId) ?? null

        return (
          <Card key={category.key} withBorder radius="md" padding="xl">
            <Stack gap="xl">
              <Group justify="space-between" align="flex-start">
                <Stack gap={6} style={{ flex: 1 }}>
                  <Title order={3}>{category.label}</Title>
                  <Text size="sm" c="gray.6">
                    {category.description}
                  </Text>
                </Stack>
                {category.tags && category.tags.length > 0 ? (
                  <Group gap="xs">
                    {category.tags.map((tag) => (
                      <Badge key={tag} color="brand" variant="light">
                        {tag}
                      </Badge>
                    ))}
                  </Group>
                ) : null}
              </Group>

              <SimpleGrid cols={{ base: 1, md: 2 }} spacing="xl">
                <Stack gap="md">
                  <Select
                    label="选择型号"
                    placeholder="请选择仪器型号"
                    data={modelSelectData[category.key] ?? []}
                    value={draft.modelId}
                    onChange={(value) => handleModelChange(category.key, value ?? '')}
                    disabled={instrumentMutation.isPending}
                  />
                  <Card withBorder padding="md" radius="md" shadow="xs">
                    {selectedModel ? (
                      <Stack gap="sm">
                        <Group justify="space-between" align="flex-start">
                          <Stack gap={2}>
                            <Text fw={600}>
                              {selectedModel.vendor} {selectedModel.model}
                            </Text>
                            <Text size="sm" c="gray.6">
                              {selectedModel.summary}
                            </Text>
                          </Stack>
                          <Badge color={instrumentStatusColor[selectedModel.status]} variant="light">
                            {selectedModel.status.toUpperCase()}
                          </Badge>
                        </Group>
                        <Group gap="sm" c="gray.6" wrap="wrap">
                          {selectedModel.channels ? <Text size="xs">通道: {selectedModel.channels}</Text> : null}
                          {selectedModel.bandwidth ? <Text size="xs">带宽: {selectedModel.bandwidth}</Text> : null}
                          <Text size="xs">接口: {selectedModel.interfaces.join(' / ')}</Text>
                        </Group>
                        <Group gap="xs" wrap="wrap">
                          {selectedModel.capabilities.map((capability) => (
                            <Badge key={capability} variant="outline" color="brand">
                              {capability}
                            </Badge>
                          ))}
                        </Group>
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
                  <Group justify="flex-end">
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
                </Stack>
              </SimpleGrid>
            </Stack>
          </Card>
        )
      })}
      </Stack>
  )
}

function ProbeManager() {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['probes'],
    queryFn: fetchProbes,
    retry: 2,
    retryDelay: 1000,
  })

  const probes = useMemo(() => data?.probes ?? [], [data])

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
    if (probes.length === 0) {
      setSelectedId('')
      return
    }
    if (!selectedId || !probes.some((probe) => probe.id === selectedId)) {
      setSelectedId(probes[0].id)
    }
  }, [probes, selectedId])

  const selectedProbe = probes.find((probe) => probe.id === selectedId) ?? null

  useEffect(() => {
    if (selectedProbe) {
      setFormState({
        ring: selectedProbe.ring,
        polarization: selectedProbe.polarization,
        position: selectedProbe.position,
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
    mutationFn: ({ id, payload }: { id: string; payload: UpdateProbePayload }) =>
      updateProbe(id, payload),
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
    mutationFn: replaceProbes,
    onSuccess: (result) => {
      queryClient.setQueryData(['probes'], result)
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
    await updateMutation.mutateAsync({ id: selectedProbe.id, payload: formState })
  }

  const handleReset = () => {
    if (!selectedProbe) return
    setFormState({
      ring: selectedProbe.ring,
      polarization: selectedProbe.polarization,
      position: selectedProbe.position,
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
        id: probe.id,
        ring: probe.ring,
        polarization: probe.polarization,
        position: probe.position,
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

  const calibrationTasks = [
    {
      title: '路径损耗校准',
      status: '待执行 · 预计耗时 35 分钟',
      description: '使用VNA逐通道测量S21，生成幅度/相位补偿矩阵。',
      action: '开始',
    },
    {
      title: '静区均匀性验证',
      status: '计划中 · 截止 2024-10-21',
      description: '扫描网格 41×41 点，目标幅度波纹 ≤ 1 dB、相位 ≤ 10°。',
      action: '排程',
    },
    {
      title: '功率放大器线性化',
      status: '进行中 · 62%',
      description: '校准功放增益与相位响应，生成数字预失真系数。',
      action: '查看',
    },
    {
      title: '探头互耦补偿',
      status: '已完成 · 2024-10-15',
      description: '已更新互耦矩阵版本 v1.3，用于虚拟路测权重修正。',
      action: '报告',
    },
  ]

  return (
    <Stack gap="xl">
      <Card withBorder radius="md" padding="xl">
        <Stack gap="md">
          <Group justify="space-between">
            <Title order={3}>探头配置文件</Title>
            <Group gap="sm">
              <Button variant="subtle" onClick={handleExportLayout}>
                导出当前布局
              </Button>
              <FileButton onChange={handleImportFile} accept="application/json">
                {(props) => (
                  <Button variant="subtle" {...props} loading={replaceMutation.isPending}>
                    导入自定义布局
                  </Button>
                )}
              </FileButton>
              <Button
                color="brand"
                onClick={handleLoadDefault}
                loading={replaceMutation.isPending}
              >
                加载默认布局
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
        <Card withBorder radius="md" padding="xl">
          <Stack gap="md">
            <Title order={3}>探头阵列总览</Title>
            <ScrollArea h={360} type="auto">
              <Table highlightOnHover withTableBorder>
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
                  {probes.map((probe) => (
                    <Table.Tr
                      key={probe.id}
                      bg={probe.id === selectedId ? 'brand.0' : undefined}
                      onClick={() => setSelectedId(probe.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <Table.Td>#{probe.probe_number} {probe.name || ''}</Table.Td>
                      <Table.Td>{formatRing(probe.ring)}</Table.Td>
                      <Table.Td>{probe.polarization}</Table.Td>
                      <Table.Td>{formatPosition(probe.position)}</Table.Td>
                      <Table.Td>
                        <Button
                          variant="subtle"
                          color="gray"
                          size="compact-sm"
                          disabled
                          title="编辑功能开发中"
                        >
                          查看
                        </Button>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          </Stack>
        </Card>

        <Stack gap="xl">
          <Card withBorder radius="md" padding="xl">
            <Stack gap="md">
              <Title order={3}>探头详细信息</Title>
              {selectedProbe ? (
                <Stack gap="sm">
                  <Alert color="blue" variant="light">
                    探头编辑功能正在重构中，当前仅支持查看。
                  </Alert>
                  <TextInput label="探头编号" value={`#${selectedProbe.probe_number}`} readOnly />
                  <TextInput label="探头名称" value={selectedProbe.name || 'N/A'} readOnly />
                  <TextInput label="环层" value={formatRing(selectedProbe.ring)} readOnly />
                  <TextInput label="极化" value={selectedProbe.polarization} readOnly />
                  <TextInput label="坐标" value={formatPosition(selectedProbe.position)} readOnly />
                  <TextInput label="状态" value={selectedProbe.status} readOnly />
                  <TextInput
                    label="校准状态"
                    value={selectedProbe.calibration_status}
                    readOnly
                  />
                  <TextInput
                    label="是否激活"
                    value={selectedProbe.is_active ? '是' : '否'}
                    readOnly
                  />
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
                  <strong>探头总数:</strong> {probes.length} 个
                </Text>
                <Text size="sm" c="gray.7">
                  <strong>活动探头:</strong> {probes.filter(p => p.is_active).length} 个
                </Text>
                <Text size="sm" c="gray.7">
                  <strong>已校准:</strong>{' '}
                  {probes.filter(p => p.calibration_status === 'valid').length} 个
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
              <ProbeLayoutView probes={probes} selectedId={selectedId} onSelect={setSelectedId} />
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
                      <Button variant="subtle" size="compact-sm">
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

type StepParameter = Record<string, string>

type StepFieldNumber = {
  key: string
  label: string
  type: 'number'
  min?: number
  max?: number
  step?: number
  description?: string
}

type StepFieldSelect = {
  key: string
  label: string
  type: 'select'
  options: Array<{ value: string; label: string }>
  description?: string
}

type StepFieldText = {
  key: string
  label: string
  type: 'text'
  placeholder?: string
  description?: string
}

type StepFieldTextarea = {
  key: string
  label: string
  type: 'textarea'
  minRows?: number
  placeholder?: string
  description?: string
}

type StepFieldDefinition = StepFieldNumber | StepFieldSelect | StepFieldText | StepFieldTextarea

type StepTemplateDefinition = {
  displayName: string
  summary?: string
  defaults: StepParameter
  fields: StepFieldDefinition[]
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

const stepTemplateDefinitions: Record<string, StepTemplateDefinition> = {
  'lib-setup-frequency': {
    displayName: '设置频率',
    summary: '配置载频、带宽与输出功率，为后续步骤提供基准。',
    defaults: {
      frequencyMHz: '3500',
      bandwidthMHz: '100',
      powerDbm: '-3',
      referenceLevel: '仪表默认',
    },
    fields: [
      { key: 'frequencyMHz', label: '载频 (MHz)', type: 'number', min: 0, description: '信道仿真器输出的中心频率。' },
      { key: 'bandwidthMHz', label: '带宽 (MHz)', type: 'number', min: 5, description: '信号占用带宽或数据信道带宽。' },
      { key: 'powerDbm', label: '输出功率 (dBm)', type: 'number', description: '仿真器端口射频功率基线。' },
      { key: 'referenceLevel', label: '功率参考说明', type: 'text', placeholder: '例如：依据功放线性区调整', description: '记录设定依据或校准结果。' },
    ],
  },
  'lib-comm-standard': {
    displayName: '通讯制式编辑',
    summary: '选择空口协议与上下行业务配置，建立DUT通信上下文。',
    defaults: {
      standard: 'nr',
      uplinkProfile: 'NR-FR1-eMBB-UL',
      downlinkProfile: 'NR-FR1-eMBB-DL',
      coreNetwork: '5GC SA',
    },
    fields: [
      {
        key: 'standard',
        label: '制式',
        type: 'select',
        options: [
          { value: 'nr', label: '5G NR' },
          { value: 'lte', label: 'LTE-A' },
          { value: 'cv2x', label: 'C-V2X PC5' },
          { value: 'wifi7', label: 'Wi-Fi 7' },
        ],
        description: '选择本次执行的空口协议。',
      },
      { key: 'uplinkProfile', label: '上行业务配置', type: 'text', placeholder: '例如：UL Throughput 80 Mbps' },
      { key: 'downlinkProfile', label: '下行业务配置', type: 'text', placeholder: '例如：DL Throughput 500 Mbps' },
      { key: 'coreNetwork', label: '核心网模式', type: 'text', placeholder: '5GC SA / EPC NSA' },
    ],
  },
  'lib-load-channel': {
    displayName: '载入信道模型',
    summary: '选择场景模型与校准配置，生成探头激励权重。',
    defaults: {
      channelModel: '3GPP_CDL-C',
      dopplerProfile: '城市UMi',
      quietZoneTarget: '1.0 dB / 10°',
      calibrationProfile: '校准矩阵 v1.3',
    },
    fields: [
      {
        key: 'channelModel',
        label: '信道模型',
        type: 'select',
        options: [
          { value: '3GPP_CDL-C', label: '3GPP CDL-C' },
          { value: '3GPP_TDL-A', label: '3GPP TDL-A' },
          { value: 'ITU_VehA', label: 'ITU VehA' },
          { value: 'custom', label: '自定义波场' },
        ],
      },
      { key: 'dopplerProfile', label: '多普勒/轨迹', type: 'text', placeholder: '例如：UMi 30 km/h' },
      { key: 'quietZoneTarget', label: '静区目标', type: 'text', placeholder: '幅度/相位指标' },
      { key: 'calibrationProfile', label: '校准档案', type: 'text', placeholder: '引用的校准矩阵或版本' },
    ],
  },
  'lib-rotate': {
    displayName: '执行转台扫描',
    summary: '控制转台或阵列完成空间扫描，采集姿态数据。',
    defaults: {
      axis: 'azimuth',
      startAngleDeg: '0',
      stopAngleDeg: '360',
      stepAngleDeg: '15',
      dwellTimeSec: '1',
      postureSync: '启用',
    },
    fields: [
      {
        key: 'axis',
        label: '扫描轴',
        type: 'select',
        options: [
          { value: 'azimuth', label: '方位轴' },
          { value: 'elevation', label: '俯仰轴' },
          { value: 'dual', label: '双轴联动' },
        ],
      },
      { key: 'startAngleDeg', label: '起始角 (°)', type: 'number', description: '扫描起点。' },
      { key: 'stopAngleDeg', label: '终止角 (°)', type: 'number', description: '扫描终点。' },
      { key: 'stepAngleDeg', label: '步进 (°)', type: 'number', min: 1, description: '角度分辨率。' },
      { key: 'dwellTimeSec', label: '停留时间 (s)', type: 'number', min: 0, description: '每个测点停留时间。' },
      {
        key: 'postureSync',
        label: '姿态同步',
        type: 'select',
        options: [
          { value: '启用', label: '启用' },
          { value: '禁用', label: '禁用' },
        ],
      },
    ],
  },
  'lib-measure-kpi': {
    displayName: '采集性能指标',
    summary: '统计吞吐量、BLER、RSSI 等关键指标。',
    defaults: {
      averageCount: '5',
      sampleIntervalMs: '200',
      targetMetrics: '吞吐量, BLER, RSSI',
      storeRawTrace: '是',
    },
    fields: [
      { key: 'averageCount', label: '平均次数', type: 'number', min: 1, description: '每个测点采样次数。' },
      { key: 'sampleIntervalMs', label: '采样间隔 (ms)', type: 'number', min: 50 },
      { key: 'targetMetrics', label: '指标列表', type: 'text', placeholder: '逗号分隔，例如：吞吐量, SNR' },
      {
        key: 'storeRawTrace',
        label: '保存原始波形',
        type: 'select',
        options: [
          { value: '是', label: '是' },
          { value: '否', label: '否' },
        ],
      },
    ],
  },
  'lib-power-scan': {
    displayName: '功率扫描设置',
    summary: '定义功率步进与保护阈值，执行灵敏度/阻塞测试。',
    defaults: {
      startPowerDbm: '-30',
      stopPowerDbm: '10',
      stepPowerDb: '1',
      protectionThresholdDbm: '15',
    },
    fields: [
      { key: 'startPowerDbm', label: '起始功率 (dBm)', type: 'number' },
      { key: 'stopPowerDbm', label: '终止功率 (dBm)', type: 'number' },
      { key: 'stepPowerDb', label: '步进 (dB)', type: 'number', min: 0.1, description: '每次调节的功率步进。' },
      { key: 'protectionThresholdDbm', label: '保护阈值 (dBm)', type: 'number', description: '超过此功率自动停止。' },
    ],
  },
  'lib-antenna-pattern': {
    displayName: '天线Pattern',
    summary: '采集3D方向图数据，分析增益/极化特性。',
    defaults: {
      azimuthRange: '±180°',
      elevationRange: '±60°',
      resolutionDeg: '5',
      polarizationMode: 'V/H',
      referencePlane: '车顶坐标系',
    },
    fields: [
      { key: 'azimuthRange', label: '方位范围', type: 'text', placeholder: '例如：±180°' },
      { key: 'elevationRange', label: '俯仰范围', type: 'text', placeholder: '例如：±60°' },
      { key: 'resolutionDeg', label: '角度分辨率 (°)', type: 'number', min: 0.5 },
      {
        key: 'polarizationMode',
        label: '极化模式',
        type: 'select',
        options: [
          { value: 'V/H', label: '垂直/水平' },
          { value: '+/-45', label: '±45° 斜极化' },
          { value: 'RHCP/LHCP', label: '右旋/左旋圆极化' },
        ],
      },
      { key: 'referencePlane', label: '参考平面', type: 'text', placeholder: '测量坐标系说明' },
    ],
  },
  'lib-export': {
    displayName: '生成报告',
    summary: '整理执行结果并生成报告、附档。',
    defaults: {
      reportFormat: 'pdf',
      includeAttachments: '是',
      fileNamePrefix: 'OTA-Report',
      recipients: 'qa@lab.example',
    },
    fields: [
      {
        key: 'reportFormat',
        label: '输出格式',
        type: 'select',
        options: [
          { value: 'pdf', label: 'PDF' },
          { value: 'html', label: 'HTML' },
          { value: 'json', label: 'JSON' },
        ],
      },
      {
        key: 'includeAttachments',
        label: '附加原始数据',
        type: 'select',
        options: [
          { value: '是', label: '是' },
          { value: '否', label: '否' },
        ],
      },
      { key: 'fileNamePrefix', label: '文件名前缀', type: 'text', placeholder: '例如：CTIA_RUN_2025' },
      { key: 'recipients', label: '通知名单', type: 'textarea', minRows: 2, placeholder: '多个邮件用逗号分隔' },
    ],
  },
}

type TestConfigProps = {
  executionMode: 'real' | 'mock'
  hardwareOnline: boolean
  systemStatus: SystemStatusItem[]
  onExecutionModeChange: (preferMock: boolean) => void
  onPlanExecute: (plan: TestPlanDetail, metadata: RunMetadata) => void
  autoChainExecution: boolean
  onAutoChainExecutionChange: (value: boolean) => void
  executingPlanId: string
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

const getTemplateDefaults = (templateId: string): StepParameter =>
  stepTemplateDefinitions[templateId]?.defaults ?? {}

function buildInitialParameters(step: SequenceStepType): StepParameter {
  const templateId = step.templateId ?? step.id
  const defaults = getTemplateDefaults(templateId)
  return {
    ...defaults,
    ...(step.parameters ?? {}),
  }
}

function TestConfig({
  executionMode,
  hardwareOnline,
  systemStatus,
  onExecutionModeChange,
  onPlanExecute,
  autoChainExecution,
  onAutoChainExecutionChange,
  executingPlanId,
}: TestConfigProps) {
  const theme = useMantineTheme()
  const queryClient = useQueryClient()

  const { data: casesData, isLoading: isCasesLoading } = useQuery({
    queryKey: ['tests', 'cases'],
    queryFn: fetchTestCases,
    enabled: false, // TEMP: Disabled until API path mismatch is fixed (/tests/cases vs /test-plans/cases)
    retry: false,
  })
  const { data: plansData, isLoading: isPlansLoading } = useQuery({
    queryKey: ['tests', 'plans'],
    queryFn: fetchTestPlans,
    enabled: false, // TEMP: Disabled until API path mismatch is fixed (/tests/plans vs /test-plans)
    retry: false,
  })
  const { data: libraryData, isLoading: isLibraryLoading } = useQuery({
    queryKey: ['sequence', 'library'],
    queryFn: fetchSequenceLibrary,
    enabled: false, // TEMP: Disabled until API path mismatch is fixed (/sequence/library vs /test-sequences)
    retry: false,
  })

  const cases = casesData?.cases ?? []
  const plans = plansData?.plans ?? []
  const library = libraryData?.library ?? []
  const caseCategoryOptions = useMemo(() => {
    const presets = new Set(['标准认证', '虚拟路测', '性能验证', '车联网', '定制场景'])
    cases.forEach((item) => {
      if (item.category) presets.add(item.category)
    })
    return Array.from(presets).map((value) => ({ value, label: value }))
  }, [cases])
  const categorySuggestionText = useMemo(
    () => caseCategoryOptions.slice(0, 5).map((item) => item.label).join(' / '),
    [caseCategoryOptions],
  )
  const blueprintOptions = useMemo(
    () => library.map((item) => ({ value: item.id, label: item.title })),
    [library],
  )

  const [selectedPlanId, setSelectedPlanId] = useState<string>('')
  const [planNameDraft, setPlanNameDraft] = useState<string>('')
  const [activeStepId, setActiveStepId] = useState<string>('')
  const [parameterState, setParameterState] = useState<Record<string, StepParameter>>({})
  const [paramFeedback, setParamFeedback] = useState<string>('')
  const [paramFeedbackColor, setParamFeedbackColor] = useState<'green' | 'red'>('green')
  const [saveCaseOpened, setSaveCaseOpened] = useState<boolean>(false)
  const [caseModalError, setCaseModalError] = useState<string>('')
  const [caseForm, setCaseForm] = useState<CaseFormState>({
    name: '',
    category: '定制场景',
    dut: '',
    tags: '',
    caseId: '',
    description: '',
  })
  const [createCaseOpened, setCreateCaseOpened] = useState<boolean>(false)
  const [createCaseError, setCreateCaseError] = useState<string>('')
  const [createCaseForm, setCreateCaseForm] = useState<NewCaseFormState>({
    name: '',
    category: '定制场景',
    dut: '',
    tags: '',
    description: '',
    blueprint: [],
  })
  const [previewCaseId, setPreviewCaseId] = useState<string>('')
  const [deleteCaseTarget, setDeleteCaseTarget] = useState<TestCase | null>(null)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [executionNotice, setExecutionNotice] = useState<string>('')
  const [deletePlanTarget, setDeletePlanTarget] = useState<TestPlanSummary | null>(null)
  const [runModalOpen, setRunModalOpen] = useState<boolean>(false)
  const [runModalError, setRunModalError] = useState<string>('')
  const [runDraft, setRunDraft] = useState<RunMetadata>({ runName: '', artifactPrefix: '', caseName: '' })

  const {
    data: previewCaseData,
    isFetching: isPreviewCaseLoading,
  } = useQuery({
    queryKey: ['tests', 'cases', 'detail', previewCaseId],
    queryFn: () => fetchTestCaseDetail(previewCaseId),
    enabled: Boolean(previewCaseId),
  })
  const previewCase = previewCaseData?.testCase ?? null

  useEffect(() => {
    if (plans.length === 0) {
      setSelectedPlanId('')
      return
    }
    if (!selectedPlanId || !plans.some((plan) => plan.id === selectedPlanId)) {
      setSelectedPlanId(plans[0].id)
    }
  }, [plans, selectedPlanId])

  const {
    data: planDetailData,
    isFetching: isPlanFetching,
  } = useQuery({
    queryKey: ['tests', 'plans', selectedPlanId],
    queryFn: () => fetchTestPlan(selectedPlanId),
    enabled: Boolean(selectedPlanId),
  })

  const activePlan = planDetailData?.plan ?? null
  const steps = activePlan?.steps ?? []
  const canExecute = Boolean(activePlan && steps.length > 0)
  const isExecutingPlan = Boolean(activePlan && activePlan.id === executingPlanId)

  useEffect(() => {
    if (activePlan) {
      setPlanNameDraft(activePlan.name)
    } else {
      setPlanNameDraft('')
    }
    setExecutionNotice('')
  }, [activePlan?.id])

  useEffect(() => {
    if (!activePlan) {
      setActiveStepId('')
      setParameterState({})
      return
    }
    setParameterState((prev) => {
      const next: Record<string, StepParameter> = {}
      steps.forEach((step) => {
        next[step.id] = prev[step.id] ?? buildInitialParameters(step)
      })
      return next
    })
    if (steps.length === 0) {
      setActiveStepId('')
    } else if (!steps.some((step) => step.id === activeStepId)) {
      setActiveStepId(steps[0].id)
    }
  }, [activePlan, steps, activeStepId])

  const currentParams = activeStepId ? parameterState[activeStepId] : undefined
  const activeStep = steps.find((step) => step.id === activeStepId) ?? null
  const activeTemplateId = activeStep?.templateId ?? activeStep?.id ?? ''
  const templateDefinition = activeTemplateId ? stepTemplateDefinitions[activeTemplateId] : undefined

  const buildPlanStepPayload = useCallback(
    (plan: TestPlanDetail) =>
      plan.steps.map((step) => {
        const templateId = step.templateId ?? step.id
        const base = buildInitialParameters(step)
        const current = parameterState[step.id]
        const parameters = current ? { ...base, ...current } : base
        return {
          id: step.id,
          templateId,
          title: step.title,
          meta: step.meta,
          description: step.description,
          parameters,
        }
      }),
    [parameterState],
  )

  const renderField = (field: StepFieldDefinition) => {
    const baseValue = currentParams?.[field.key] ?? templateDefinition?.defaults[field.key] ?? ''
    switch (field.type) {
      case 'number':
        return (
          <NumberInput
            key={field.key}
            label={field.label}
            value={baseValue === '' ? undefined : Number.parseFloat(baseValue)}
            min={field.min}
            max={field.max}
            step={field.step}
            description={field.description}
            onChange={(value) =>
              handleParameterChange(field.key, value === null ? '' : typeof value === 'number' ? value.toString() : value)
            }
          />
        )
      case 'select':
        return (
          <Select
            key={field.key}
            label={field.label}
            data={field.options}
            value={baseValue || null}
            onChange={(value) => handleParameterChange(field.key, value ?? '')}
            description={field.description}
          />
        )
      case 'textarea':
        return (
          <Textarea
            key={field.key}
            label={field.label}
            minRows={field.minRows ?? 3}
            placeholder={field.placeholder}
            value={baseValue}
            description={field.description}
            onChange={(event) => handleParameterChange(field.key, event.currentTarget.value)}
          />
        )
      case 'text':
      default:
        return (
          <TextInput
            key={field.key}
            label={field.label}
            placeholder={field.placeholder}
            value={baseValue}
            description={field.description}
            onChange={(event) => handleParameterChange(field.key, event.currentTarget.value)}
          />
        )
    }
  }

  const syncPlanCaches = useCallback(
    (planId: string, plan: TestPlanDetail) => {
      queryClient.setQueryData(['tests', 'plans', planId], { plan })
      queryClient.setQueryData(['tests', 'plans'], (previous: TestPlanListResponse | undefined) => {
        if (!previous) {
          return {
            plans: [
              {
                id: plan.id,
                name: plan.name,
                caseId: plan.caseId,
                caseName: plan.caseName,
                status: plan.status,
                updatedAt: plan.updatedAt,
              },
            ],
          }
        }
        const exists = previous.plans.some((summary) => summary.id === planId)
        const nextPlans = exists
          ? previous.plans.map((summary) =>
              summary.id === planId
                ? { ...summary, name: plan.name, status: plan.status, updatedAt: plan.updatedAt }
                : summary,
            )
          : [
              {
                id: plan.id,
                name: plan.name,
                caseId: plan.caseId,
                caseName: plan.caseName,
                status: plan.status,
                updatedAt: plan.updatedAt,
              },
              ...previous.plans,
            ]
        return { plans: nextPlans }
      })
    },
    [queryClient],
  )

  const createPlanMutation = useMutation({
    mutationFn: createTestPlan,
    onSuccess: (result) => {
      if (!result?.plan) return
      syncPlanCaches(result.plan.id, result.plan)
      setSelectedPlanId(result.plan.id)
    },
  })

  const updatePlanMutation = useMutation({
    mutationFn: ({ planId, payload }: { planId: string; payload: UpdatePlanPayload }) =>
      updateTestPlan(planId, payload),
    onSuccess: (result) => {
      if (!result?.plan) return
      syncPlanCaches(result.plan.id, result.plan)
      setPlanNameDraft(result.plan.name)
    },
  })

  const setPlanStatusMutation = useMutation({
    mutationFn: ({ planId, status }: { planId: string; status: string }) =>
      updateTestPlan(planId, { status }),
    onSuccess: (result) => {
      if (!result?.plan) return
      syncPlanCaches(result.plan.id, result.plan)
    },
  })

  const reorderPlanQueueMutation = useMutation({
    mutationFn: (payload: ReorderPlanQueuePayload) => reorderTestPlans(payload),
    onSuccess: (result) => {
      if (!result?.plans) return
      queryClient.setQueryData(['tests', 'plans'], result)
    },
  })

  const persistStepsMutation = useMutation({
    mutationFn: ({ planId, steps }: { planId: string; steps: SequenceStepType[] }) =>
      updateTestPlan(planId, { steps }),
    onSuccess: (result) => {
      if (!result?.plan) return
      syncPlanCaches(result.plan.id, result.plan)
      setParamFeedbackColor('green')
      setParamFeedback('计划已保存。')
      setParameterState(() => {
        const next: Record<string, StepParameter> = {}
        result.plan.steps.forEach((step) => {
          next[step.id] = buildInitialParameters(step)
        })
        return next
      })
      window.setTimeout(() => setParamFeedback(''), 2400)
    },
    onError: () => {
      setParamFeedbackColor('red')
      setParamFeedback('保存失败，请稍后重试。')
      window.setTimeout(() => setParamFeedback(''), 2600)
    },
  })

  const appendStepMutation = useMutation({
    mutationFn: ({ planId, libraryId }: { planId: string; libraryId: string }) =>
      appendPlanStep(planId, { libraryId }),
    onSuccess: (result, variables) => {
      if (!result?.plan) return
      syncPlanCaches(variables.planId, result.plan)
      setActiveStepId(result.plan.steps[result.plan.steps.length - 1]?.id ?? '')
    },
  })

  const reorderStepMutation = useMutation({
    mutationFn: ({ planId, payload }: { planId: string; payload: ReorderSequencePayload }) =>
      reorderPlanStep(planId, payload),
    onSuccess: (result, variables) => {
      if (!result?.plan) return
      syncPlanCaches(variables.planId, result.plan)
    },
  })

  const removeStepMutation = useMutation({
    mutationFn: ({ planId, stepId }: { planId: string; stepId: string }) =>
      removePlanStep(planId, stepId),
    onSuccess: (result, variables) => {
      if (!result?.plan) return
      syncPlanCaches(variables.planId, result.plan)
      if (!result.plan.steps.some((step) => step.id === activeStepId)) {
        setActiveStepId(result.plan.steps[0]?.id ?? '')
      }
    },
  })

  const saveCaseMutation = useMutation({
    mutationFn: createTestCaseFromPlan,
    onSuccess: (result) => {
      if (!result?.testCase) return
      queryClient.invalidateQueries({ queryKey: ['tests', 'cases'] })
      setSaveCaseOpened(false)
      setCaseModalError('')
      setParamFeedbackColor('green')
      setParamFeedback(`已另存为测试例：${result.testCase.name} (${result.testCase.id})`)
      window.setTimeout(() => setParamFeedback(''), 2800)
    },
    onError: () => {
      setCaseModalError('保存测试例失败，请检查字段后重试。')
    },
  })

  const createCaseMutation = useMutation({
    mutationFn: createTestCase,
    onSuccess: (result) => {
      if (!result?.testCase) return
      const summaryCase = {
        id: result.testCase.id,
        name: result.testCase.name,
        dut: result.testCase.dut,
        createdAt: result.testCase.createdAt,
        category: result.testCase.category,
        tags: result.testCase.tags,
        description: result.testCase.description,
      }
      queryClient.setQueryData(
        ['tests', 'cases'],
        (previous: TestCasesResponse | undefined): TestCasesResponse => {
          if (!previous) {
            return { cases: [summaryCase] }
          }
          const filtered = previous.cases.filter((item) => item.id !== summaryCase.id)
          return { cases: [summaryCase, ...filtered] }
        },
      )
      queryClient.invalidateQueries({ queryKey: ['tests', 'cases'] })
      queryClient.invalidateQueries({ queryKey: ['tests', 'cases'] })
      setCreateCaseOpened(false)
      setCreateCaseError('')
      setParamFeedbackColor('green')
      setParamFeedback(`已创建测试例：${result.testCase.name}`)
      setPreviewCaseId(result.testCase.id)
      window.setTimeout(() => setParamFeedback(''), 2800)
    },
    onError: () => {
      setCreateCaseError('创建测试例失败，请检查字段后重试。')
    },
  })

  const deleteCaseMutation = useMutation({
    mutationFn: ({ caseId }: { caseId: string; name: string }) => deleteTestCase(caseId),
    onSuccess: (_response, variables) => {
      const { caseId, name } = variables
      queryClient.setQueryData(
        ['tests', 'cases'],
        (previous: TestCasesResponse | undefined): TestCasesResponse => {
          if (!previous) {
            return { cases: [] }
          }
          return { cases: previous.cases.filter((item) => item.id !== caseId) }
        },
      )
      queryClient.invalidateQueries({ queryKey: ['tests', 'cases'] })
      setDeleteCaseTarget(null)
      setParamFeedbackColor('green')
      setParamFeedback(`已删除测试例：${name}`)
      setPreviewCaseId((prev) => (prev === caseId ? '' : prev))
      window.setTimeout(() => setParamFeedback(''), 2800)
    },
    onError: () => {
      setParamFeedbackColor('red')
      setParamFeedback('删除测试例失败，请稍后重试。')
      window.setTimeout(() => setParamFeedback(''), 2800)
    },
  })

  const deletePlanMutation = useMutation({
    mutationFn: ({ planId }: { planId: string; planName: string }) => deleteTestPlan(planId),
    onSuccess: (_response, variables) => {
      const { planId, planName } = variables
      queryClient.setQueryData(
        ['tests', 'plans'],
        (previous: TestPlanListResponse | undefined): TestPlanListResponse => {
          if (!previous) return { plans: [] }
          return { plans: previous.plans.filter((item) => item.id !== planId) }
        },
      )
      queryClient.removeQueries({ queryKey: ['tests', 'plans', planId] })
      if (selectedPlanId === planId) {
        const nextPlans = queryClient.getQueryData(['tests', 'plans']) as TestPlanListResponse | undefined
        const nextId = nextPlans?.plans[0]?.id ?? ''
        setSelectedPlanId(nextId)
      }
      if (executingPlanId === planId) {
        setExecutionNotice('当前执行计划已被删除，已停止监控。')
      }
      setExecutionNotice((prev) => `已删除计划：${planName}${prev ? `\n${prev}` : ''}`)
      setDeletePlanTarget(null)
      setActiveStepId('')
      setParameterState({})
    },
    onError: () => {
      setExecutionNotice('删除计划失败，请稍后重试。')
    },
  })

  const handlePlanNameSave = () => {
    if (!activePlan) return
    const trimmed = planNameDraft.trim()
    if (!trimmed || trimmed === activePlan.name) {
      setPlanNameDraft(activePlan.name)
      return
    }
    updatePlanMutation.mutate({ planId: activePlan.id, payload: { name: trimmed } })
  }

  const handleParameterChange = (field: keyof StepParameter, value: string) => {
    if (!activeStepId) return
    setParamFeedback('')
    setParameterState((prev) => ({
      ...prev,
      [activeStepId]: {
        ...prev[activeStepId],
        [field]: value,
      },
    }))
  }

  const handleParameterSave = () => {
    if (!activePlan || persistStepsMutation.isPending) return
    setParamFeedback('')
    setParamFeedbackColor('green')
    const stepsPayload = buildPlanStepPayload(activePlan)
    persistStepsMutation.mutate({ planId: activePlan.id, steps: stepsPayload })
  }

  const handleCaseFormChange =
    (field: keyof CaseFormState) =>
    (event: ChangeEvent<HTMLInputElement> | ChangeEvent<HTMLTextAreaElement>) => {
      const value = event.currentTarget.value
      setCaseForm((prev) => ({ ...prev, [field]: value }))
    }

  const handleCreateCaseFieldChange =
    (field: Exclude<keyof NewCaseFormState, 'blueprint'>) =>
    (event: ChangeEvent<HTMLInputElement> | ChangeEvent<HTMLTextAreaElement>) => {
      const value = event.currentTarget.value
      setCreateCaseForm((prev) => ({ ...prev, [field]: value }))
    }

  const handleCreateCaseBlueprintChange = (value: string[]) => {
    setCreateCaseForm((prev) => ({ ...prev, blueprint: value }))
  }

  const handleOpenCreateCase = () => {
    setCreateCaseForm({
      name: '',
      category: '定制场景',
      dut: '',
      tags: '',
      description: '',
      blueprint: [],
    })
    setCreateCaseError('')
    createCaseMutation.reset()
    setCreateCaseOpened(true)
  }

  const handleCreateCaseConfirm = () => {
    if (createCaseMutation.isPending) return
    const name = createCaseForm.name.trim()
    const category = createCaseForm.category.trim()
    const dut = createCaseForm.dut.trim()
    if (!name || !category || !dut) {
      setCreateCaseError('请填写测试例名称、类别和被测设备。')
      return
    }
    const tags = createCaseForm.tags
      .split(',')
      .map((tag) => tag.trim())
      .filter((tag) => tag.length > 0)
    const description = createCaseForm.description.trim()
    const blueprint = createCaseForm.blueprint.filter((value) => value && value.length > 0)
    setCreateCaseError('')
    createCaseMutation.mutate({
      name,
      category,
      dut,
      tags,
      description: description.length > 0 ? description : undefined,
      blueprint: blueprint.length > 0 ? blueprint : undefined,
    })
  }

  const handleOpenCasePreview = (caseId: string) => {
    setPreviewCaseId(caseId)
  }

  const handleCloseCasePreview = () => {
    setPreviewCaseId('')
  }

  const handleDeleteCaseClick = (testCase: TestCase) => {
    setDeleteCaseTarget(testCase)
  }

  const handleDeleteCaseCancel = () => {
    if (deleteCaseMutation.isPending) return
    setDeleteCaseTarget(null)
  }

  const handleOpenSaveCase = () => {
    if (!activePlan) return
    const sourceCase = cases.find((item) => item.id === activePlan.caseId)
    setCaseForm({
      name: activePlan.name,
      category: sourceCase?.category ?? '定制场景',
      dut: sourceCase?.dut ?? '',
      tags: sourceCase?.tags?.join(', ') ?? '',
      caseId: '',
      description: sourceCase?.description ?? '',
    })
    setCaseModalError('')
    saveCaseMutation.reset()
    setSaveCaseOpened(true)
  }

  const handleSaveCaseConfirm = () => {
    if (!activePlan || saveCaseMutation.isPending) return
    const name = caseForm.name.trim()
    const category = caseForm.category.trim()
    const dut = caseForm.dut.trim()
    if (!name || !category || !dut) {
      setCaseModalError('请填写测试例名称、类别和被测设备。')
      return
    }
    const tags = caseForm.tags
      .split(',')
      .map((tag) => tag.trim())
      .filter((tag) => tag.length > 0)
    const description = caseForm.description.trim()
    const caseId = caseForm.caseId.trim()
    setCaseModalError('')
    saveCaseMutation.mutate({
      sourcePlanId: activePlan.id,
      name,
      category,
      dut,
      tags,
      description: description.length > 0 ? description : undefined,
      caseId: caseId.length > 0 ? caseId : undefined,
      steps: buildPlanStepPayload(activePlan),
    })
  }

  const handleDragStart = (event: DragEvent<HTMLDivElement>, stepId: string) => {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', stepId)
    setDraggingId(stepId)
  }

  const handleDragOver = (event: DragEvent<HTMLDivElement>, targetId: string) => {
    event.preventDefault()
    if (draggingId === targetId) return
    event.dataTransfer.dropEffect = 'move'
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>, targetId: string) => {
    event.preventDefault()
    if (!selectedPlanId) return
    const sourceId = draggingId ?? event.dataTransfer.getData('text/plain')
    if (!sourceId || sourceId === targetId) return
    reorderStepMutation.mutate({ planId: selectedPlanId, payload: { fromId: sourceId, toId: targetId } })
    setDraggingId(null)
  }

  const handleDragEnd = () => {
    setDraggingId(null)
  }

  const handleAppend = (libraryId: string) => {
    if (!selectedPlanId) return
    appendStepMutation.mutate({ planId: selectedPlanId, libraryId })
  }

  const handleQuickAppend = () => {
    if (library.length === 0 || !selectedPlanId) return
    handleAppend(library[0].id)
  }

  const handleRemoveStep = (stepId: string) => {
    if (!selectedPlanId) return
    removeStepMutation.mutate({ planId: selectedPlanId, stepId })
  }

  const handlePlanStatusChange = (planId: string, status: string) => {
    setPlanStatusMutation.mutate({ planId, status })
  }

  const handlePlanMove = (planId: string, direction: ReorderPlanQueuePayload['direction']) => {
    reorderPlanQueueMutation.mutate({ planId, direction })
  }

  const handleDeletePlanCancel = () => {
    if (deletePlanMutation.isPending) return
    setDeletePlanTarget(null)
  }

  const handleDeletePlanConfirm = () => {
    if (!deletePlanTarget || deletePlanMutation.isPending) return
    if (deletePlanTarget.id === executingPlanId) {
      setExecutionNotice('正在执行的计划无法删除。')
      return
    }
    deletePlanMutation.mutate({ planId: deletePlanTarget.id, planName: deletePlanTarget.name })
  }

  const handleRunFieldChange =
    (field: keyof RunMetadata) =>
    (event: ChangeEvent<HTMLInputElement>) => {
      const value = event.currentTarget.value
      setRunModalError('')
      setRunDraft((prev) => ({ ...prev, [field]: value }))
    }

  const handleRunConfirm = () => {
    if (!activePlan || runModalError) return
    const runName = runDraft.runName.trim()
    const artifactPrefix = sanitizeArtifactPrefix(
      (runDraft.artifactPrefix?.trim() || runName || activePlan.name).trim(),
    )
    if (!runName) {
      setRunModalError('请输入执行名称。')
      return
    }
    if (!artifactPrefix) {
      setRunModalError('请输入报告/附件前缀。')
      return
    }
    setExecutionNotice('')
    setRunModalOpen(false)
    setRunModalError('')
    onPlanExecute(activePlan, { runName, artifactPrefix, caseName: runDraft.caseName ?? activePlan.caseName ?? activePlan.name })
  }

  const handleExecutePlan = () => {
    if (!activePlan) {
      setExecutionNotice('请选择测试计划后再执行。')
      return
    }
    if (!canExecute) {
      setExecutionNotice('当前计划尚未配置步骤，无法执行。')
      return
    }
    if (activePlan.status !== '待执行') {
      setExecutionNotice('请先将计划状态调整为“待执行”。')
      return
    }
    if (isExecutingPlan) {
      setExecutionNotice('该计划正在执行中，请稍候。')
      return
    }
    const defaults = createDefaultRunMetadata(activePlan.name, activePlan.caseName ?? activePlan.name)
    setRunDraft(defaults)
    setRunModalError('')
    setRunModalOpen(true)
  }

  const isInitialLoading =
    isCasesLoading || isPlansLoading || isLibraryLoading || (selectedPlanId ? isPlanFetching : false)

  useEffect(() => {
    if (!executingPlanId) return
    if (selectedPlanId === executingPlanId) return
    setSelectedPlanId(executingPlanId)
  }, [executingPlanId, selectedPlanId])

  if (isInitialLoading) {
    return (
      <Card withBorder radius="md" padding="xl">
        <Title order={3} mb="sm">
          测试计划与编排
        </Title>
        <Text size="sm" c="gray.6">
          正在加载测试数据…
        </Text>
      </Card>
    )
  }

  const saveCaseModal = (
    <Modal
      opened={saveCaseOpened}
      onClose={() => {
        if (saveCaseMutation.isPending) return
        setSaveCaseOpened(false)
        setCaseModalError('')
      }}
      title="保存为测试例"
      centered
      size="lg"
    >
      <Stack gap="sm">
        <Text size="sm" c="gray.6">
          将当前测试计划保存为新的测试例，未来可在“测试例库”中一键复用。
        </Text>
        <TextInput
          label="测试例名称"
          required
          value={caseForm.name}
          onChange={handleCaseFormChange('name')}
        />
        <TextInput
          label="自定义案例 ID（可选）"
          value={caseForm.caseId}
          placeholder="例如：CUST-OTA-001"
          onChange={handleCaseFormChange('caseId')}
        />
        <TextInput
          label="类别"
          required
          value={caseForm.category}
          placeholder={categorySuggestionText ? `例如：${categorySuggestionText}` : '请输入类别'}
          onChange={handleCaseFormChange('category')}
        />
        <TextInput
          label="被测设备 (DUT)"
          required
          value={caseForm.dut}
          placeholder="例如：SUV 样车 / 某型号 TCU"
          onChange={handleCaseFormChange('dut')}
        />
        <TextInput
          label="标签 (逗号分隔)"
          value={caseForm.tags}
          placeholder="例如：NR, 城市峡谷"
          onChange={handleCaseFormChange('tags')}
        />
        <Textarea
          label="说明 (可选)"
          minRows={3}
          value={caseForm.description}
          placeholder="记录该测试例的适用场景、关键参数等补充信息"
          onChange={handleCaseFormChange('description')}
        />
        {caseModalError ? (
          <Alert color="red" variant="light" radius="md">
            {caseModalError}
          </Alert>
        ) : null}
        <Group justify="flex-end">
          <Button
            variant="subtle"
            onClick={() => {
              if (saveCaseMutation.isPending) return
              setSaveCaseOpened(false)
              setCaseModalError('')
            }}
          >
            取消
          </Button>
          <Button
            color="brand"
            onClick={handleSaveCaseConfirm}
            loading={saveCaseMutation.isPending}
            disabled={!activePlan}
          >
            保存
          </Button>
        </Group>
      </Stack>
    </Modal>
  )

  const createCaseModal = (
    <Modal
      opened={createCaseOpened}
      onClose={() => {
        if (createCaseMutation.isPending) return
        setCreateCaseOpened(false)
        setCreateCaseError('')
        createCaseMutation.reset()
      }}
      title="新建测试例"
      centered
      size="lg"
    >
      <Stack gap="sm">
        <Text size="sm" c="gray.6">
          从零定义一个测试例，可选关联常用步骤模板，后续在“测试计划库”中引用。
        </Text>
        <TextInput
          label="测试例名称"
          required
          value={createCaseForm.name}
          onChange={handleCreateCaseFieldChange('name')}
        />
        <TextInput
          label="类别"
          required
          value={createCaseForm.category}
          placeholder={categorySuggestionText ? `例如：${categorySuggestionText}` : '请输入类别'}
          onChange={handleCreateCaseFieldChange('category')}
        />
        <TextInput
          label="被测设备 (DUT)"
          required
          value={createCaseForm.dut}
          placeholder="例如：SUV 样车 / 某型号 TCU"
          onChange={handleCreateCaseFieldChange('dut')}
        />
        <TextInput
          label="标签 (逗号分隔)"
          value={createCaseForm.tags}
          placeholder="例如：NR, 城市峡谷"
          onChange={handleCreateCaseFieldChange('tags')}
        />
        <Textarea
          label="说明 (可选)"
          minRows={3}
          value={createCaseForm.description}
          placeholder="记录该测试例的适用场景、关键参数等补充信息"
          onChange={handleCreateCaseFieldChange('description')}
        />
        <MultiSelect
          label="关联步骤模板 (可选)"
          data={blueprintOptions}
          value={createCaseForm.blueprint}
          onChange={handleCreateCaseBlueprintChange}
          placeholder={library.length === 0 ? '尚未加载步骤库' : '选择步骤模板，未选择则使用默认模板'}
          searchable
          clearable
          disabled={library.length === 0}
        />
        {createCaseError ? (
          <Alert color="red" variant="light" radius="md">
            {createCaseError}
          </Alert>
        ) : null}
        <Group justify="flex-end">
          <Button
            variant="subtle"
            onClick={() => {
              if (createCaseMutation.isPending) return
              setCreateCaseOpened(false)
              setCreateCaseError('')
              createCaseMutation.reset()
            }}
          >
            取消
          </Button>
          <Button color="brand" onClick={handleCreateCaseConfirm} loading={createCaseMutation.isPending}>
            创建
          </Button>
        </Group>
      </Stack>
    </Modal>
  )

  const previewCaseModal = (
    <Modal
      opened={Boolean(previewCaseId)}
      onClose={handleCloseCasePreview}
      title={previewCase?.name ?? '测试例详情'}
      size="lg"
      centered
    >
      {isPreviewCaseLoading ? (
        <Text size="sm" c="gray.6">
          正在加载测试例详情…
        </Text>
      ) : !previewCase ? (
        <Text size="sm" c="gray.6">
          暂无可显示的测试例。
        </Text>
      ) : (
        <Stack gap="md">
          <Stack gap={4}>
            <Group justify="space-between" align="center">
              <Text fw={600}>{previewCase.name}</Text>
              <Badge color="brand" variant="light">
                {previewCase.category ?? '未分类'}
              </Badge>
            </Group>
            <Text size="sm" c="gray.6">
              #{previewCase.id} · {previewCase.dut}
            </Text>
            {previewCase.description ? (
              <Text size="sm" c="gray.6">
                {previewCase.description}
              </Text>
            ) : null}
            <Group gap="xs">
              {(previewCase.tags ?? []).map((tag) => (
                <Badge key={tag} size="xs" color="brand" variant="light">
                  {tag}
                </Badge>
              ))}
            </Group>
          </Stack>
          <Divider />
          <Stack gap="sm">
            <Group justify="space-between" align="center">
              <Text fw={600} size="sm">
                步骤模板
              </Text>
              <Button
                size="compact-sm"
                color="brand"
                onClick={() => {
                  if (createPlanMutation.isPending) return
                  handleCloseCasePreview()
                  createPlanMutation.mutate({
                    name: `${previewCase.name} - Test Plan`,
                    test_case_ids: [previewCase.id],
                    created_by: 'user'
                  })
                }}
                loading={createPlanMutation.isPending}
              >
                基于此测试例生成计划
              </Button>
            </Group>
            <ScrollArea h={260} type="auto">
              <Stack gap="sm" pr="sm">
                {previewCase.steps.map((step, index) => (
                  <Paper key={step.id ?? `${step.templateId}-${index}`} withBorder radius="md" p="md">
                    <Stack gap={4}>
                      <Group justify="space-between" align="center">
                        <Text fw={600} size="sm">
                          {index + 1}. {step.title}
                        </Text>
                        <Text size="xs" c="gray.6">
                          {step.meta}
                        </Text>
                      </Group>
                      {step.description ? (
                        <Text size="xs" c="gray.6">
                          {step.description}
                        </Text>
                      ) : null}
                    </Stack>
                  </Paper>
                ))}
              </Stack>
            </ScrollArea>
          </Stack>
        </Stack>
      )}
    </Modal>
  )

  const deleteCaseModal = (
    <Modal
      opened={Boolean(deleteCaseTarget)}
      onClose={handleDeleteCaseCancel}
      title="删除测试例"
      centered
      size="sm"
    >
      <Stack gap="md">
        <Text size="sm" c="gray.6">
          确认删除测试例
          <Text component="span" fw={600} c="red">
            {deleteCaseTarget?.name}
          </Text>
          吗？该操作会移除其预设步骤，后续生成的计划需重新选择模板。
        </Text>
        <Group justify="flex-end">
          <Button variant="subtle" onClick={handleDeleteCaseCancel} disabled={deleteCaseMutation.isPending}>
            取消
          </Button>
          <Button
            color="red"
            loading={deleteCaseMutation.isPending}
            onClick={() => {
              if (!deleteCaseTarget) return
              deleteCaseMutation.mutate({ caseId: deleteCaseTarget.id, name: deleteCaseTarget.name })
            }}
          >
            删除
          </Button>
        </Group>
      </Stack>
    </Modal>
  )

  const deletePlanModal = (
    <Modal
      opened={Boolean(deletePlanTarget)}
      onClose={handleDeletePlanCancel}
      title="删除测试计划"
      centered
      size="sm"
    >
      <Stack gap="md">
        <Text size="sm" c="gray.6">
          确认删除测试计划
          <Text component="span" fw={600} c="red">
            {deletePlanTarget?.name}
          </Text>
          吗？该操作无法撤销。
        </Text>
        <Group justify="flex-end">
          <Button variant="subtle" onClick={handleDeletePlanCancel} disabled={deletePlanMutation.isPending}>
            取消
          </Button>
          <Button color="red" loading={deletePlanMutation.isPending} onClick={handleDeletePlanConfirm}>
            删除
          </Button>
        </Group>
      </Stack>
    </Modal>
  )

  const runModal = (
    <Modal opened={runModalOpen} onClose={() => setRunModalOpen(false)} title="开始执行" centered size="sm">
      <Stack gap="md">
        <Text size="sm" c="gray.6">
          设置本次执行的名称与归档前缀，报告和附件将自动沿用该前缀。
        </Text>
        <Alert color="gray" variant="light" radius="md">
          测试例：{runDraft.caseName || activePlan?.caseName || activePlan?.name || '未指定'}
        </Alert>
        <TextInput
          label="执行名称"
          value={runDraft.runName}
          onChange={handleRunFieldChange('runName')}
          placeholder="例如：CTIA-01.40-2025-11-06-Run01"
        />
        <TextInput
          label="报告/附件前缀"
          value={runDraft.artifactPrefix}
          onChange={handleRunFieldChange('artifactPrefix')}
          description="用于生成报告文件、附件和日志归档，例如：CTIA-Run01"
        />
        {runModalError ? (
          <Alert color="red" variant="light" radius="md">
            {runModalError}
          </Alert>
        ) : null}
        <Group justify="flex-end">
          <Button variant="subtle" onClick={() => setRunModalOpen(false)}>
            取消
          </Button>
          <Button color="brand" onClick={handleRunConfirm}>
            开始执行
          </Button>
        </Group>
      </Stack>
    </Modal>
  )

  return (
    <>
      {saveCaseModal}
      {createCaseModal}
      {previewCaseModal}
      {deleteCaseModal}
      {deletePlanModal}
      {runModal}
      <Stack gap="xl">
      <Card withBorder radius="md" padding="xl">
        <Stack gap="md">
          <Group justify="space-between" align="flex-start">
            <Stack gap={4} style={{ flex: 1 }}>
              <Title order={3}>执行模式</Title>
              <Text size="sm" c="gray.6">
                当检测到关键仪器离线时系统会自动切换至模拟执行，可在硬件在线时手动切换为真实执行。
              </Text>
            </Stack>
            <Stack gap={6} align="flex-end">
              <Badge color={executionMode === 'real' ? 'green' : 'gray'} variant="light">
                {executionMode === 'real' ? '真实执行' : '模拟执行'}
              </Badge>
              <Switch
                checked={executionMode === 'real'}
                onChange={(event) => {
                  const useReal = event.currentTarget.checked
                  if (useReal) {
                    if (!hardwareOnline) {
                      setExecutionNotice('检测到关键硬件离线，已保持模拟执行。')
                      onExecutionModeChange(true)
                      return
                    }
                    setExecutionNotice('')
                    onExecutionModeChange(false)
                  } else {
                    setExecutionNotice('')
                    onExecutionModeChange(true)
                  }
                }}
                disabled={!hardwareOnline && executionMode !== 'real'}
                onLabel="真实"
                offLabel="模拟"
                size="md"
              />
                  <Button
                    size="compact-md"
                    color="brand"
                    disabled={
                      !canExecute || !activePlan || activePlan.status !== '待执行' || isExecutingPlan
                    }
                    onClick={handleExecutePlan}
                  >
                    开始执行
                  </Button>
            </Stack>
          </Group>
          <Group gap="sm">
            <Badge color={hardwareOnline ? 'green' : 'red'} variant="light">
              {hardwareOnline ? '硬件在线' : '硬件离线 (模拟执行)'}
            </Badge>
          </Group>
          <Group gap="sm">
            <Switch
              checked={autoChainExecution}
              onChange={(event) => onAutoChainExecutionChange(event.currentTarget.checked)}
              label="自动连续执行队列"
            />
          </Group>
          {!hardwareOnline ? (
            <Alert color="orange" variant="light" radius="md">
              检测到部分设备离线，系统已强制切换至模拟 (Mock) 执行模式。
            </Alert>
          ) : null}
          {executionNotice ? (
            <Alert color="gray" variant="light" radius="md">
              {executionNotice}
            </Alert>
          ) : null}
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            {systemStatus.map((item) => {
              const offline = /离线|错误|断开/i.test(item.value)
              return (
                <Paper key={item.label} withBorder radius="md" p="sm">
                  <Stack gap={4}>
                    <Group justify="space-between" align="center">
                      <Text size="xs" c="gray.6">
                        {item.label}
                      </Text>
                      <Badge color={offline ? 'red' : 'green'} variant="light">
                        {item.value}
                      </Badge>
                    </Group>
                    <Text size="xs" c="gray.5">
                      {item.detail}
                    </Text>
                  </Stack>
                </Paper>
              )
            })}
          </SimpleGrid>
        </Stack>
      </Card>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="xl">
        <Card withBorder radius="md" padding="xl">
          <Stack gap="md">
            <Title order={3}>测试计划库</Title>
            {plans.length === 0 ? (
              <Text size="sm" c="gray.6">
                暂无计划，请先从测试例库生成。
              </Text>
            ) : (
              <Stack gap="sm">
                {plans.map((plan, index) => {
                  const active = plan.id === selectedPlanId
                  const executing = plan.id === executingPlanId
                  const isFirst = index === 0
                  const isLast = index === plans.length - 1
                  return (
                    <Paper
                      key={plan.id}
                      withBorder
                      radius="md"
                      p="md"
                      style={{
                        borderColor: active ? theme.colors.brand[4] : executing ? theme.colors.yellow[5] : undefined,
                        background: active
                          ? hexToRgba(theme.colors.brand[0], 0.8)
                          : executing
                            ? hexToRgba(theme.colors.yellow[0], 0.6)
                            : undefined,
                        cursor: 'pointer',
                      }}
                      onClick={() => setSelectedPlanId(plan.id)}
                    >
                      <Stack gap="sm">
                        <Group justify="space-between" align="center">
                          <Stack gap={2} style={{ flex: 1 }}>
                            <Group gap="xs" align="center">
                              <Badge size="sm" variant="light" color="gray">
                                #{index + 1}
                              </Badge>
                              <Text fw={600}>{plan.name}</Text>
                            </Group>
                            <Text size="xs" c="gray.6">
                              基于：{plan.caseName}
                            </Text>
                          </Stack>
                          <Stack gap={4} align="flex-end">
                            <Badge
                              color={
                                plan.status === '已完成'
                                  ? 'green'
                                  : plan.status === '待执行'
                                    ? 'brand'
                                    : plan.status === '执行中'
                                      ? 'yellow'
                                      : 'gray'
                              }
                              variant="light"
                            >
                              {plan.status}
                            </Badge>
                            <Text size="xs" c="gray.6">
                              更新于 {plan.updatedAt}
                            </Text>
                          </Stack>
                        </Group>
                        <Group justify="space-between" align="center">
                          <Group gap="xs">
                            <Button
                              variant="subtle"
                              size="compact-xs"
                              onClick={(event) => {
                                event.stopPropagation()
                                handlePlanMove(plan.id, 'top')
                              }}
                              loading={reorderPlanQueueMutation.isPending}
                              disabled={isFirst || executing}
                            >
                              置顶
                            </Button>
                            <Button
                              variant="subtle"
                              size="compact-xs"
                              onClick={(event) => {
                                event.stopPropagation()
                                handlePlanMove(plan.id, 'up')
                              }}
                              loading={reorderPlanQueueMutation.isPending}
                              disabled={isFirst || executing}
                            >
                              上移
                            </Button>
                            <Button
                              variant="subtle"
                              size="compact-xs"
                              onClick={(event) => {
                                event.stopPropagation()
                                handlePlanMove(plan.id, 'down')
                              }}
                              loading={reorderPlanQueueMutation.isPending}
                              disabled={isLast || executing}
                            >
                              下移
                            </Button>
                          </Group>
                          <Group gap="xs">
                            {plan.status === '草稿' ? (
                              <Button
                                variant="light"
                                size="compact-xs"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  handlePlanStatusChange(plan.id, '待执行')
                                }}
                                loading={setPlanStatusMutation.isPending}
                                disabled={executing}
                              >
                                标记待执行
                              </Button>
                            ) : null}
                            <Button
                              variant="outline"
                              size="compact-xs"
                              onClick={(event) => {
                                event.stopPropagation()
                                setSelectedPlanId(plan.id)
                              }}
                            >
                              查看
                            </Button>
                            <Button
                              variant="outline"
                              size="compact-xs"
                              color="red"
                              onClick={(event) => {
                                event.stopPropagation()
                                setDeletePlanTarget(plan)
                              }}
                              disabled={executing || deletePlanMutation.isPending}
                            >
                              删除
                            </Button>
                            {executing && (
                              <Badge color="yellow" variant="light">
                                执行中
                              </Badge>
                            )}
                          </Group>
                        </Group>
                      </Stack>
                    </Paper>
                  )
                })}
              </Stack>
            )}
          </Stack>
        </Card>

        <Card withBorder radius="md" padding="xl">
          <Stack gap="md">
            <Group justify="space-between" align="center">
              <Title order={3}>测试例库</Title>
              <Button variant="light" size="compact-sm" onClick={handleOpenCreateCase}>
                新建测试例
              </Button>
            </Group>
            {cases.length === 0 ? (
              <Text size="sm" c="gray.6">
                暂无测试例，可点击右上角创建或通过计划另存。
              </Text>
            ) : (
              <Stack gap="sm">
                {cases.map((testCase) => (
                  <Paper key={testCase.id} withBorder radius="md" p="md">
                    <Group justify="space-between" align="flex-start" wrap="nowrap" gap="md">
                      <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
                        <Group justify="space-between" align="center">
                          <Text fw={600}>{testCase.name}</Text>
                          <Badge color="brand" variant="light">
                            {testCase.category ?? '未分类'}
                          </Badge>
                        </Group>
                        <Text size="xs" c="gray.6">
                          #{testCase.id} · {testCase.dut}
                        </Text>
                        <Text size="xs" c="gray.6">
                          创建时间：{testCase.createdAt}
                        </Text>
                        {testCase.description ? (
                          <Text size="xs" c="gray.6">
                            {testCase.description}
                          </Text>
                        ) : null}
                        {testCase.tags && testCase.tags.length > 0 ? (
                          <Group gap="xs">
                            {testCase.tags.map((tag) => (
                              <Badge key={tag} size="xs" color="brand" variant="light">
                                {tag}
                              </Badge>
                            ))}
                          </Group>
                        ) : null}
                      </Stack>
                      <Stack gap="xs" align="flex-end">
                        <Group gap="xs">
                          <Button
                            variant="light"
                            size="compact-sm"
                            onClick={() => handleOpenCasePreview(testCase.id)}
                          >
                            打开
                          </Button>
                          <Button
                            size="compact-sm"
                            color="brand"
                            loading={createPlanMutation.isPending}
                            onClick={() => createPlanMutation.mutate({
                              name: `${testCase.name} - Test Plan`,
                              test_case_ids: [testCase.id],
                              created_by: 'user'
                            })}
                          >
                            生成计划
                          </Button>
                        </Group>
                        <Button
                          variant="outline"
                          size="compact-sm"
                          color="red"
                          loading={
                            deleteCaseMutation.isPending && deleteCaseTarget?.id === testCase.id
                          }
                          onClick={() => handleDeleteCaseClick(testCase)}
                        >
                          删除
                        </Button>
                      </Stack>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            )}
          </Stack>
        </Card>
      </SimpleGrid>

      <Card withBorder radius="md" padding="xl">
        <Stack gap="md">
          <Group justify="space-between" align="center">
            <Stack gap={2}>
              <Title order={3}>序列编排</Title>
              <Text size="xs" c="gray.6">
                {activePlan ? `关联测试例：${activePlan.caseName}` : '请选择左侧测试计划以进行编辑'}
              </Text>
            </Stack>
            {activePlan ? (
              <Group gap="sm" align="center">
                <TextInput
                  size="sm"
                  value={planNameDraft}
                  onChange={(event) => setPlanNameDraft(event.currentTarget.value)}
                  onBlur={handlePlanNameSave}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      handlePlanNameSave()
                    }
                    if (event.key === 'Escape') {
                      setPlanNameDraft(activePlan.name)
                      event.currentTarget.blur()
                    }
                  }}
                  placeholder="输入计划名称"
                />
                <Badge
                  color={
                    activePlan.status === '已完成'
                      ? 'green'
                      : activePlan.status === '待执行'
                        ? 'brand'
                        : activePlan.status === '执行中'
                          ? 'yellow'
                          : 'gray'
                  }
                  variant="light"
                >
                  {activePlan.status}
                </Badge>
                <Group gap="xs">
                  {activePlan.status === '草稿' ? (
                    <Button
                      variant="light"
                      size="compact-sm"
                      loading={setPlanStatusMutation.isPending}
                      onClick={() => handlePlanStatusChange(activePlan.id, '待执行')}
                    >
                      标记待执行
                    </Button>
                  ) : null}
                  {activePlan.status === '待执行' ? (
                    <Button
                      variant="light"
                      size="compact-sm"
                      loading={setPlanStatusMutation.isPending}
                      onClick={() => handlePlanStatusChange(activePlan.id, '草稿')}
                    >
                      退回草稿
                    </Button>
                  ) : null}
                  {activePlan.status === '已完成' ? (
                    <Button
                      variant="light"
                      size="compact-sm"
                      loading={setPlanStatusMutation.isPending}
                      onClick={() => handlePlanStatusChange(activePlan.id, '待执行')}
                    >
                      重新排队
                    </Button>
                  ) : null}
                  {isExecutingPlan ? (
                    <Badge color="yellow" variant="light">
                      执行中
                    </Badge>
                  ) : null}
                </Group>
              </Group>
            ) : null}
          </Group>
          <ScrollArea h={340} type="auto">
            <Flex gap="md" wrap="wrap">
              {steps.map((step) => {
                const isActive = step.id === activeStepId
                const isDragging = step.id === draggingId
                return (
                  <Paper
                    key={step.id}
                    withBorder
                    shadow={isActive ? 'md' : 'xs'}
                    radius="md"
                    p="md"
                    draggable={Boolean(activePlan)}
                    onClick={() => setActiveStepId(step.id)}
                    onDragStart={(event) => activePlan && handleDragStart(event, step.id)}
                    onDragOver={(event) => handleDragOver(event, step.id)}
                    onDrop={(event) => handleDrop(event, step.id)}
                    onDragEnd={handleDragEnd}
                    style={{
                      flex: '1 1 260px',
                      minWidth: '260px',
                      maxWidth: '320px',
                      cursor: activePlan ? 'grab' : 'not-allowed',
                      backgroundColor: isActive ? theme.colors.brand[0] : undefined,
                      borderColor: isActive ? theme.colors.brand[5] : undefined,
                      opacity: isDragging ? 0.6 : 1,
                    }}
                  >
                    <Stack gap={6}>
                      <Text fw={600} size="sm">
                        {step.title}
                      </Text>
                      <Text size="xs" c="gray.6">
                        {step.meta}
                      </Text>
                      {step.description ? (
                        <Text size="xs" c="gray.6">
                          {step.description}
                        </Text>
                      ) : null}
                      <Group justify="flex-end">
                        <Button
                          variant="subtle"
                          size="compact-sm"
                          color="red"
                          disabled={!activePlan}
                          onClick={(event) => {
                            event.stopPropagation()
                            handleRemoveStep(step.id)
                          }}
                        >
                          移除
                        </Button>
                      </Group>
                    </Stack>
                  </Paper>
                )
              })}
              <Paper
                withBorder
                radius="md"
                p="md"
                style={{
                  flex: '1 1 260px',
                  minWidth: '260px',
                  maxWidth: '320px',
                  borderStyle: 'dashed',
                  borderColor: theme.colors.gray[5],
                  backgroundColor: theme.colors.dark[6],
                  opacity: 0.85,
                }}
                onDragOver={(event) => handleDragOver(event, steps[steps.length - 1]?.id ?? '')}
                onDrop={(event) => {
                  event.preventDefault()
                  if (!selectedPlanId) return
                  const sourceId = draggingId ?? event.dataTransfer.getData('text/plain')
                  if (!sourceId) return
                  reorderStepMutation.mutate({
                    planId: selectedPlanId,
                    payload: { fromId: sourceId, toId: '__end__' },
                  })
                  setDraggingId(null)
                }}
              >
                <Stack gap={6}>
                  <Text fw={600} size="sm">
                    + 添加步骤
                  </Text>
                  <Text size="xs" c="gray.6">
                    拖拽或从库中选择
                  </Text>
                  <Button
                    size="compact-sm"
                    color="brand"
                    onClick={handleQuickAppend}
                    disabled={library.length === 0 || !selectedPlanId}
                  >
                    快速追加
                  </Button>
                </Stack>
              </Paper>
            </Flex>
          </ScrollArea>
        </Stack>
      </Card>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="xl">
        <Card withBorder radius="md" padding="xl">
          <Stack gap="md">
            <Title order={3}>参数面板</Title>
            {!activePlan ? (
              <Text size="sm" c="gray.6">
                请选择左侧测试计划后，在此编辑步骤参数。
              </Text>
            ) : !templateDefinition || !currentParams ? (
              <Text size="sm" c="gray.6">
                当前步骤未绑定参数模板，请确认步骤来自步骤库或重新加载计划。
              </Text>
            ) : (
              <Stack gap="lg">
                {templateDefinition.summary ? (
                  <Alert color="gray" variant="light" radius="md">
                    {templateDefinition.summary}
                  </Alert>
                ) : null}
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                  {templateDefinition.fields.map((field) => (
                    <Box key={field.key}>{renderField(field)}</Box>
                  ))}
                </SimpleGrid>
                <Group justify="space-between" align="center">
                  <Button
                    variant="light"
                    onClick={handleOpenSaveCase}
                    disabled={!activePlan}
                    loading={saveCaseMutation.isPending}
                  >
                    另存为测试例
                  </Button>
                  <Button
                    color="brand"
                    onClick={handleParameterSave}
                    loading={persistStepsMutation.isPending}
                  >
                    保存计划
                  </Button>
                </Group>
                {paramFeedback ? (
                  <Alert color={paramFeedbackColor} variant="light" radius="md">
                    {paramFeedback}
                  </Alert>
                ) : null}
              </Stack>
            )}
          </Stack>
        </Card>

        <Card withBorder radius="md" padding="xl">
          <Stack gap="md">
            <Title order={3}>步骤库</Title>
            <ScrollArea h={360} type="auto">
              <Stack gap="sm">
                {library.map((item) => (
                  <Paper key={item.id} withBorder radius="md" p="md">
                    <Group justify="space-between" align="flex-start">
                      <Stack gap={4} style={{ flex: 1 }}>
                        <Text fw={600}>{item.title}</Text>
                        <Text size="xs" c="gray.6">
                          {item.meta}
                        </Text>
                        <Text size="sm" c="gray.6">
                          {item.description}
                        </Text>
                      </Stack>
                      <Button
                        variant="subtle"
                        size="compact-sm"
                        onClick={() => handleAppend(item.id)}
                        disabled={!selectedPlanId}
                      >
                        追加
                      </Button>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            </ScrollArea>
          </Stack>
        </Card>
      </SimpleGrid>
      </Stack>
    </>
  )
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
  autoChainExecution,
}: MonitoringProps) {
  const theme = useMantineTheme()
  const { data: feedsData, isLoading: isFeedsLoading } = useQuery({
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
    if (planDetail) {
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
    } else if (scenarioStatus === 'completed') {
      setExecStatus('idle')
      setIsStreaming(false)
    } else if (scenarioStatus === 'idle') {
      setExecStatus('idle')
      setIsStreaming(false)
    }
  }, [scenarioStatus])

  useEffect(() => {
    const wsUrl = `${window.location.origin.replace(/^http/, 'ws')}/api/v1/ws/monitoring`
    let isActive = true

    const connect = () => {
      if (!isActive) return
      const socket = new WebSocket(wsUrl)
      socketRef.current = socket

      socket.addEventListener('open', () => {
        if (!isActive) return
        setWsConnected(true)
      })

      socket.addEventListener('message', (event) => {
        if (!isActive) return
        try {
          const payload = JSON.parse(event.data) as {
            type: 'metrics' | 'waveform' | 'log' | 'status'
            data: unknown
          }
          switch (payload.type) {
            case 'metrics':
              if (scenarioMetricsRef.current) break
              if (Array.isArray(payload.data)) {
                setMetricFeeds(payload.data as typeof metricFeeds)
              }
              break
            case 'waveform':
              if (Array.isArray(payload.data)) {
                const samples = payload.data as number[]
                setWaveform((prev) => {
                  const merged = [...prev.slice(samples.length), ...samples]
                  return merged.length === 0 ? samples : merged
                })
              }
              break
            case 'log':
              setLogs((prev) => {
                const next = [...prev, payload.data as LogEntry]
                return next.slice(-40)
              })
              break
            case 'status':
              {
                if (scenarioMetricsRef.current) break
                const status = payload.data as {
                  execStatus?: 'running' | 'paused' | 'idle'
                  powerLevel?: number
                  interferenceMode?: 'off' | 'awgn' | 'co-channel'
                }
                if (status.execStatus) setExecStatus(status.execStatus)
                if (typeof status.powerLevel === 'number') setPowerLevel(status.powerLevel)
                if (status.interferenceMode) setInterferenceMode(status.interferenceMode)
              }
              break
            default:
              break
          }
        } catch {
          // ignore malformed messages
        }
      })

      const scheduleReconnect = () => {
        if (!isActive) return
        setWsConnected(false)
        if (reconnectTimerRef.current !== null) {
          window.clearTimeout(reconnectTimerRef.current)
        }
        reconnectTimerRef.current = window.setTimeout(connect, 2500)
      }

      socket.addEventListener('close', scheduleReconnect)
      socket.addEventListener('error', () => {
        socket.close()
      })
    }

    connect()

    return () => {
      isActive = false
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
      }
      if (socketRef.current) {
        socketRef.current.close()
      }
    }
  }, [setLogs])

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
    if (controlsDisabled || !hasPlanLoaded) return
    setExecStatus('running')
    setIsStreaming(true)
    onRestart()
  }

  const handlePause = () => {
    if (!hasPlanLoaded) return
    setExecStatus('paused')
    setIsStreaming(false)
  }

  const handleStop = () => {
    if (!hasPlanLoaded) return
    setExecStatus('idle')
    setIsStreaming(false)
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
          executingPlan && planDetail
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
                    disabled={controlsDisabled || execStatus === 'running' || !hasPlanLoaded}
                  >
                    开始
                  </Button>
                  <Button
                    variant="outline"
                    color="gray"
                    onClick={handlePause}
                    disabled={controlsDisabled || execStatus !== 'running' || !hasPlanLoaded}
                  >
                    暂停
                  </Button>
                  <Button
                    variant="outline"
                    color="red"
                    onClick={handleStop}
                    disabled={controlsDisabled || execStatus === 'idle' || !hasPlanLoaded}
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

function Results({
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
    enabled: false, // TEMP: Disabled - endpoint not implemented yet
    retry: false,
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
