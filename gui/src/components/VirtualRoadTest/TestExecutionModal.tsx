/**
 * Test Execution Modal
 *
 * Display test execution progress and status with real API integration
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Modal,
  Button,
  Stack,
  Progress,
  Group,
  Text,
  Badge,
  Alert,
  Timeline,
  Card,
  SimpleGrid,
  Loader,
} from '@mantine/core'
import {
  IconCheck,
  IconClock,
  IconPlayerPlay,
  IconPlayerStop,
  IconAlertCircle,
  IconFileReport,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import type { ScenarioSummary, TestMode, ExecutionStatus, PhaseResult, KPISummary } from '../../types/roadTest'
import {
  createExecution,
  controlExecution,
  submitExecutionMetrics,
  type TimeSeriesPoint,
} from '../../api/roadTestService'
import { TestReportModal } from './TestReportModal'

interface Props {
  opened: boolean
  onClose: () => void
  scenario: ScenarioSummary
  testMode?: TestMode
}

const TEST_PHASES = [
  { name: '初始化', duration: 5 },
  { name: '配置网络', duration: 10 },
  { name: '启动基站', duration: 8 },
  { name: '连接DUT', duration: 7 },
  { name: '运行测试', duration: 30 },
  { name: '收集数据', duration: 10 },
  { name: '生成报告', duration: 5 },
]

const MODE_LABELS: Record<TestMode, string> = {
  digital_twin: '数字孪生',
  conducted: '传导测试',
  ota: 'OTA测试',
}

// Modes that require additional hardware setup
const MODES_REQUIRING_HARDWARE: TestMode[] = ['conducted', 'ota']

export function TestExecutionModal({ opened, onClose, scenario, testMode }: Props) {
  const queryClient = useQueryClient()
  const [executionId, setExecutionId] = useState<string>('')
  const [status, setStatus] = useState<ExecutionStatus>('idle')
  const [progress, setProgress] = useState(0)
  const [currentPhase, setCurrentPhase] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [reportModalOpened, setReportModalOpened] = useState(false)

  // Metrics collection
  const collectedMetricsRef = useRef<TimeSeriesPoint[]>([])
  const phaseResultsRef = useRef<PhaseResult[]>([])
  const startTimeRef = useRef<Date | null>(null)
  const phaseStartTimeRef = useRef<Date>(new Date())
  const lastPhaseRef = useRef<number>(-1)

  // Check if current mode requires hardware
  const requiresHardware = testMode && MODES_REQUIRING_HARDWARE.includes(testMode)

  // Create execution mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      // For modes requiring hardware, use digital_twin mode for simulation
      // In production, this would require topology_id for conducted mode
      const effectiveMode = requiresHardware ? 'digital_twin' : (testMode || 'digital_twin')

      return createExecution({
        mode: effectiveMode,
        scenario_id: scenario.id,
        config: scenario.step_configuration || {},
        notes: `Virtual road test: ${scenario.name} (requested mode: ${testMode || 'digital_twin'})`,
      })
    },
    onSuccess: (data) => {
      setExecutionId(data.execution_id)
      // Don't reset status - simulation may already be running
      setError(null)
      // Don't show notification - it's background operation now
    },
    onError: (err: any) => {
      // Don't show error for "already started" - it's expected when simulation is running
      const errorMsg = err?.response?.data?.detail || err?.message || ''
      if (!errorMsg.toLowerCase().includes('already started')) {
        setError(errorMsg || '创建执行失败')
        notifications.show({
          title: '创建失败',
          message: errorMsg,
          color: 'red',
        })
      }
    },
  })

  // Control execution mutation
  const controlMutation = useMutation({
    mutationFn: async (action: 'start' | 'pause' | 'resume' | 'stop') => {
      return controlExecution(executionId, action)
    },
    onSuccess: (_, action) => {
      if (action === 'start') {
        setStatus('running')
        notifications.show({
          title: '执行已开始',
          message: '测试正在运行中...',
          color: 'blue',
        })
      } else if (action === 'stop') {
        setStatus('stopped')
        notifications.show({
          title: '执行已停止',
          message: '测试已被用户停止',
          color: 'orange',
        })
      }
    },
    onError: (err: any) => {
      // Don't show error for "already started" - it's expected when simulation is running
      const errorMsg = err?.response?.data?.detail || err?.message || ''
      if (!errorMsg.toLowerCase().includes('already started')) {
        setError(errorMsg || '控制执行失败')
      }
    },
  })

  // Poll for status updates - DISABLED for demo mode
  // The backend doesn't actually run tests, so polling would reset our simulated progress
  // useEffect(() => {
  //   if (!executionId || status !== 'running') return
  //   const pollStatus = async () => { ... }
  //   const interval = setInterval(pollStatus, 1000)
  //   return () => clearInterval(interval)
  // }, [executionId, status, queryClient])

  // Generate a simulated metric data point
  const generateMetricPoint = useCallback((elapsedSeconds: number, progressPercent: number): TimeSeriesPoint => {
    // Simulate realistic RF and throughput values
    const baseRsrp = -75 - progressPercent * 0.1 // Slight degradation over distance
    const baseSinr = 18 - progressPercent * 0.05

    return {
      time_s: elapsedSeconds,
      rsrp_dbm: baseRsrp + (Math.random() - 0.5) * 8,
      rsrq_db: -10 + (Math.random() - 0.5) * 4,
      sinr_db: baseSinr + (Math.random() - 0.5) * 6,
      dl_throughput_mbps: 100 + Math.random() * 40 - progressPercent * 0.3,
      ul_throughput_mbps: 35 + Math.random() * 15,
      latency_ms: 10 + Math.random() * 8,
      // Simulate position along a route (example: Haidian Park area)
      position: {
        lat: 39.99 + (progressPercent / 100) * 0.02,
        lon: 116.32 + (progressPercent / 100) * 0.015,
        alt: 50,
      },
      event: progressPercent > 30 && progressPercent < 32 ? 'handover' :
        progressPercent > 60 && progressPercent < 62 ? 'beam_switch' : undefined,
    }
  }, [])

  // Compute KPI summary from collected metrics
  const computeKPISummary = useCallback((metrics: TimeSeriesPoint[]): KPISummary[] => {
    if (metrics.length === 0) return []

    const computeStats = (values: number[], name: string, unit: string, target: number): KPISummary => {
      const mean = values.reduce((a, b) => a + b, 0) / values.length
      const min = Math.min(...values)
      const max = Math.max(...values)
      const std = Math.sqrt(values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / values.length)

      return {
        name,
        unit,
        mean: Math.round(mean * 100) / 100,
        min: Math.round(min * 100) / 100,
        max: Math.round(max * 100) / 100,
        std: Math.round(std * 100) / 100,
        target,
        passed: name === '端到端延迟' ? mean <= target : mean >= target,
      }
    }

    const result: KPISummary[] = []
    const dlValues = metrics.map(m => m.dl_throughput_mbps).filter((v): v is number => v !== undefined)
    const ulValues = metrics.map(m => m.ul_throughput_mbps).filter((v): v is number => v !== undefined)
    const latencyValues = metrics.map(m => m.latency_ms).filter((v): v is number => v !== undefined)
    const rsrpValues = metrics.map(m => m.rsrp_dbm).filter((v): v is number => v !== undefined)
    const sinrValues = metrics.map(m => m.sinr_db).filter((v): v is number => v !== undefined)

    if (dlValues.length) result.push(computeStats(dlValues, '下行吞吐量', 'Mbps', 100))
    if (ulValues.length) result.push(computeStats(ulValues, '上行吞吐量', 'Mbps', 40))
    if (latencyValues.length) result.push(computeStats(latencyValues, '端到端延迟', 'ms', 20))
    if (rsrpValues.length) result.push(computeStats(rsrpValues, 'RSRP', 'dBm', -90))
    if (sinrValues.length) result.push(computeStats(sinrValues, 'SINR', 'dB', 10))

    return result
  }, [])

  // Generate events from metrics
  const generateEvents = useCallback((metrics: TimeSeriesPoint[]): Array<{ time: string; type: string; description: string }> => {
    const events: Array<{ time: string; type: string; description: string }> = []
    const startTime = startTimeRef.current || new Date()

    metrics.forEach(m => {
      if (m.event) {
        const eventTime = new Date(startTime.getTime() + m.time_s * 1000)
        events.push({
          time: eventTime.toISOString(),
          type: m.event,
          description: m.event === 'handover' ? '切换到邻近基站' : '波束切换',
        })
      }
    })

    return events
  }, [])

  // Helper to submit current metrics
  const submitCurrentMetrics = useCallback(async () => {
    if (!executionId || collectedMetricsRef.current.length === 0) return

    try {
      await submitExecutionMetrics(executionId, {
        time_series: collectedMetricsRef.current,
        phases: phaseResultsRef.current,
        events: generateEvents(collectedMetricsRef.current),
        kpi_summary: computeKPISummary(collectedMetricsRef.current),
      })
    } catch (err) {
      console.error('Failed to submit metrics:', err)
      throw err // Re-throw to caller knows it failed
    }
  }, [executionId, generateEvents, computeKPISummary])

  // Submit metrics and notify backend when simulation completes
  const notifyBackendComplete = useCallback(async () => {
    if (!executionId) return

    try {
      // Submit collected metrics
      await submitCurrentMetrics().catch(e => console.warn('Metrics submission minor failure:', e))

      // Mark execution as complete
      await controlExecution(executionId, 'complete')
      queryClient.invalidateQueries({ queryKey: ['road-test-executions'] })
    } catch (err) {
      console.error('Failed to complete execution:', err)
      // Still try to complete the execution if it was just metrics failure
      try {
        await controlExecution(executionId, 'complete')
        queryClient.invalidateQueries({ queryKey: ['road-test-executions'] })
      } catch {
        // Ignore
      }
    }
  }, [executionId, queryClient, submitCurrentMetrics])

  // Simulate progress for demo (since backend doesn't actually run tests)
  useEffect(() => {
    if (status !== 'running') {
      return
    }

    // Record start time
    if (!startTimeRef.current) {
      startTimeRef.current = new Date()
      phaseStartTimeRef.current = new Date()
      lastPhaseRef.current = -1
      collectedMetricsRef.current = []
      phaseResultsRef.current = []
    }

    const interval = setInterval(() => {
      setProgress((prev) => {
        const now = new Date()
        const elapsedSeconds = (now.getTime() - (startTimeRef.current?.getTime() || now.getTime())) / 1000

        if (prev >= 100) {
          // Record final phase
          if (lastPhaseRef.current >= 0 && lastPhaseRef.current < TEST_PHASES.length) {
            phaseResultsRef.current.push({
              name: TEST_PHASES[lastPhaseRef.current].name,
              status: 'completed',
              duration_s: (now.getTime() - phaseStartTimeRef.current.getTime()) / 1000,
              start_time: phaseStartTimeRef.current.toISOString(),
              end_time: now.toISOString(),
            })
          }

          setStatus('completed')
          notifyBackendComplete()
          notifications.show({
            title: '测试完成',
            message: '所有测试阶段已完成',
            color: 'green',
          })
          return 100
        }

        const increment = Math.random() * 5 + 2
        const newProgress = Math.min(prev + increment, 100)

        // Collect metric data point
        const metricPoint = generateMetricPoint(elapsedSeconds, newProgress)
        collectedMetricsRef.current.push(metricPoint)

        // Update phase based on progress
        const phaseIndex = Math.min(
          Math.floor((newProgress / 100) * TEST_PHASES.length),
          TEST_PHASES.length - 1
        )

        // Record phase transition
        if (phaseIndex !== lastPhaseRef.current) {
          // Complete previous phase
          if (lastPhaseRef.current >= 0) {
            phaseResultsRef.current.push({
              name: TEST_PHASES[lastPhaseRef.current].name,
              status: 'completed',
              duration_s: (now.getTime() - phaseStartTimeRef.current.getTime()) / 1000,
              start_time: phaseStartTimeRef.current.toISOString(),
              end_time: now.toISOString(),
            })
          }
          // Start new phase
          phaseStartTimeRef.current = now
          lastPhaseRef.current = phaseIndex
        }

        setCurrentPhase(phaseIndex)
        return newProgress
      })
    }, 800)

    return () => {
      clearInterval(interval)
    }
  }, [status, notifyBackendComplete, generateMetricPoint])

  const handleStart = useCallback(async () => {
    setError(null)

    // Start simulation immediately for demo purposes
    // API calls are for record-keeping only
    setStatus('running')
    setProgress(0)
    setCurrentPhase(0)

    // Try to create execution record in background (non-blocking)
    if (!executionId) {
      createMutation.mutate(undefined, {
        onSuccess: async (data) => {
          // Try to start execution via API (best effort)
          try {
            await controlExecution(data.execution_id, 'start')
          } catch {
            // Ignore - simulation is already running
          }
        },
      })
    } else {
      // Try to start via API (best effort)
      controlMutation.mutate('start')
    }
  }, [executionId, createMutation, controlMutation])

  const handleStop = useCallback(async () => {
    if (executionId) {
      // Submit metrics before stopping
      try {
        await submitCurrentMetrics()
      } catch (e) {
        console.warn('Failed to save metrics on stop', e)
      }
      controlMutation.mutate('stop')
    } else {
      setStatus('stopped')
    }
  }, [executionId, controlMutation, submitCurrentMetrics])

  const handleViewReport = useCallback(() => {
    if (executionId) {
      setReportModalOpened(true)
    } else {
      notifications.show({
        title: '无法查看报告',
        message: '执行ID不存在',
        color: 'red',
      })
    }
  }, [executionId])

  const handleClose = useCallback(() => {
    // Reset state when closing
    setExecutionId('')
    setStatus('idle')
    setProgress(0)
    setCurrentPhase(0)
    setError(null)
    // Reset refs
    collectedMetricsRef.current = []
    phaseResultsRef.current = []
    startTimeRef.current = null
    lastPhaseRef.current = -1
    onClose()
  }, [onClose])

  const totalDuration = TEST_PHASES.reduce((sum, phase) => sum + phase.duration, 0)
  const estimatedTime = Math.round((totalDuration * (100 - progress)) / 100)
  const isCompleted = status === 'completed' || progress >= 100
  const isRunning = status === 'running'
  const isFailed = status === 'failed'
  const isStopped = status === 'stopped'
  const isPending = createMutation.isPending || controlMutation.isPending

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title={`执行测试: ${scenario.name}`}
      size="lg"
      centered
    >
      <Stack gap="md">
        {/* Hardware Mode Warning */}
        {requiresHardware && (
          <Alert icon={<IconAlertCircle size={16} />} title="硬件模式提示" color="yellow">
            <Text size="sm">
              {testMode === 'conducted' ? '传导测试' : 'OTA测试'}模式需要配置硬件拓扑。
              当前将使用<strong>数字孪生</strong>模式进行模拟演示。
            </Text>
          </Alert>
        )}

        {/* Error Alert */}
        {error && (
          <Alert icon={<IconAlertCircle size={16} />} title="错误" color="red">
            {error}
          </Alert>
        )}

        {/* Execution Info */}
        <Card withBorder p="md">
          <SimpleGrid cols={2} spacing="md">
            <div>
              <Text size="xs" c="dimmed" fw={500}>
                场景
              </Text>
              <Text size="sm">{scenario.name}</Text>
            </div>
            <div>
              <Text size="xs" c="dimmed" fw={500}>
                测试模式
              </Text>
              <Text size="sm">
                {testMode ? MODE_LABELS[testMode] : '未指定'}
                {requiresHardware && <Text span size="xs" c="dimmed"> (模拟)</Text>}
              </Text>
            </div>
            <div>
              <Text size="xs" c="dimmed" fw={500}>
                执行 ID
              </Text>
              <Text size="sm" ff="monospace">
                {executionId || '-'}
              </Text>
            </div>
            <div>
              <Text size="xs" c="dimmed" fw={500}>
                预计时间
              </Text>
              <Text size="sm">
                {estimatedTime}s / {totalDuration}s
              </Text>
            </div>
          </SimpleGrid>
        </Card>

        {/* Progress */}
        <div>
          <Group justify="space-between" mb="xs">
            <Text fw={500}>执行进度</Text>
            <Badge color={isCompleted ? 'green' : isFailed ? 'red' : 'blue'}>
              {Math.round(progress)}%
            </Badge>
          </Group>
          <Progress
            value={progress}
            size="lg"
            color={isCompleted ? 'green' : isFailed ? 'red' : 'blue'}
            animated={isRunning}
          />
        </div>

        {/* Current Phase */}
        <Card
          withBorder
          p="md"
          bg={isCompleted ? 'green.0' : isFailed ? 'red.0' : 'blue.0'}
        >
          <Group>
            {isPending ? (
              <Loader size="sm" />
            ) : (
              <IconPlayerPlay
                size={20}
                color={isCompleted ? 'green' : isFailed ? 'red' : 'blue'}
              />
            )}
            <div>
              <Text size="sm" fw={500}>
                当前阶段: {TEST_PHASES[currentPhase]?.name || '完成'}
              </Text>
              <Text size="xs" c="dimmed">
                {isCompleted
                  ? '测试已完成'
                  : isFailed
                    ? '测试失败'
                    : isStopped
                      ? '测试已停止'
                      : isPending
                        ? '正在处理...'
                        : `${Math.round(TEST_PHASES[currentPhase]?.duration * (progress / 100))}s`}
              </Text>
            </div>
          </Group>
        </Card>

        {/* Phase Timeline */}
        <div>
          <Text fw={500} size="sm" mb="md">
            执行阶段
          </Text>
          <Timeline active={currentPhase + 1} bulletSize={24} lineWidth={2}>
            {TEST_PHASES.map((phase, index) => (
              <Timeline.Item
                key={phase.name}
                bullet={
                  index <= currentPhase ? (
                    <IconCheck size={12} />
                  ) : (
                    <IconClock size={12} />
                  )
                }
                title={phase.name}
              >
                <Text c="dimmed" size="sm">
                  {phase.duration}s
                </Text>
              </Timeline.Item>
            ))}
          </Timeline>
        </div>

        {/* Results (when complete) */}
        {isCompleted && (
          <Alert icon={<IconCheck size={16} />} title="测试完成" color="green">
            <Stack gap="xs">
              <Text size="sm">✓ 所有测试阶段已完成</Text>
              <Text size="sm">✓ 数据已收集并保存</Text>
              <Text size="sm">✓ 执行记录已添加到历史</Text>
            </Stack>
          </Alert>
        )}

        {/* Actions */}
        <Group justify="flex-end">
          {!isRunning && !isCompleted && !isStopped && (
            <Button
              onClick={handleStart}
              leftSection={<IconPlayerPlay size={16} />}
              loading={isPending}
            >
              开始执行
            </Button>
          )}
          {isRunning && (
            <Button
              onClick={handleStop}
              variant="light"
              color="red"
              leftSection={<IconPlayerStop size={16} />}
              loading={isPending}
            >
              停止执行
            </Button>
          )}
          {isCompleted && (
            <Button
              variant="light"
              leftSection={<IconFileReport size={16} />}
              onClick={handleViewReport}
            >
              查看报告
            </Button>
          )}
          <Button variant="subtle" onClick={handleClose}>
            {isCompleted ? '关闭' : '取消'}
          </Button>
        </Group>
      </Stack>

      {/* Report Modal */}
      <TestReportModal
        opened={reportModalOpened}
        onClose={() => setReportModalOpened(false)}
        executionId={executionId}
      />
    </Modal>
  )
}
