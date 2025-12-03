/**
 * Execution Metrics Card Component
 *
 * Phase 2.7: Differentiated monitoring for test execution
 *
 * 差异化特性：
 * - 显示测试执行上下文（当前值 vs 期望值范围）
 * - 复用 RealtimeMetricsCard 的优化（throttling, memo）
 * - 增加执行状态指示器
 * - 与Dashboard的通用监控形成差异化
 *
 * 使用场景：
 * - Dashboard: 系统健康监控（无测试上下文）
 * - Monitoring Tab: 测试执行监控（带期望值对比）
 */

import {
  Card,
  Title,
  Stack,
  Group,
  Text,
  Badge,
  Alert,
  SimpleGrid,
  ActionIcon,
  Tooltip,
  Skeleton,
  Progress,
  Paper,
} from '@mantine/core'
import {
  IconPlugConnected,
  IconPlugConnectedX,
  IconRefresh,
  IconActivity,
  IconTarget,
  IconAlertTriangle,
} from '@tabler/icons-react'
import { useMonitoringWebSocket, type MonitoringMetricData } from '../../../hooks/useMonitoringWebSocket'
import { memo } from 'react'

interface ExecutionMetricsCardProps {
  /** 显示调试信息（默认：false） */
  debug?: boolean
  /** 节流间隔（毫秒，默认：100） */
  throttleMs?: number
  /** 测试计划名称 */
  testPlanName?: string
  /** 当前步骤信息 */
  currentStep?: {
    index: number
    total: number
    title?: string
  }
  /** 期望值范围（用于对比） */
  expectedRanges?: {
    throughput?: { min: number; max: number }
    snr?: { min: number; max: number }
    quiet_zone_uniformity?: { min: number; max: number }
    eirp?: { min: number; max: number }
    temperature?: { min: number; max: number }
  }
}

// 指标显示标签（中文）
const METRIC_LABELS: Record<string, string> = {
  throughput: '吞吐量',
  snr: '信噪比 (SNR)',
  quiet_zone_uniformity: '静区均匀度',
  eirp: 'EIRP',
  temperature: '温度',
}

// 获取状态颜色
const getStatusColor = (status: string): string => {
  switch (status) {
    case 'normal':
      return 'green'
    case 'warning':
      return 'yellow'
    case 'critical':
      return 'red'
    default:
      return 'gray'
  }
}

// 格式化数值
const formatValue = (value: number, decimals: number = 2): string => {
  return value.toFixed(decimals)
}

// 检查值是否在期望范围内
const isWithinRange = (value: number, range?: { min: number; max: number }): boolean => {
  if (!range) return true
  return value >= range.min && value <= range.max
}

// 带期望值对比的指标卡片（子组件）
interface ExecutionMetricCardProps {
  label: string
  data: MonitoringMetricData
  decimals?: number
  expectedRange?: { min: number; max: number }
}

const ExecutionMetricCard = memo(
  ({ label, data, decimals = 2, expectedRange }: ExecutionMetricCardProps) => {
    const withinRange = isWithinRange(data.value, expectedRange)
    const hasExpectedRange = expectedRange !== undefined

    return (
      <Card
        withBorder
        padding="sm"
        radius="sm"
        style={{
          transition: 'all 0.3s ease',
          borderColor: hasExpectedRange && !withinRange ? 'var(--mantine-color-yellow-5)' : undefined,
          borderWidth: hasExpectedRange && !withinRange ? 2 : undefined,
        }}
      >
        <Stack gap="xs">
          {/* 标签和状态 */}
          <Group justify="space-between">
            <Text size="sm" c="dimmed">
              {label}
            </Text>
            <Group gap={4}>
              <Badge size="xs" color={getStatusColor(data.status)}>
                {data.status}
              </Badge>
              {hasExpectedRange && !withinRange && (
                <Tooltip label="超出期望范围">
                  <IconAlertTriangle size={14} color="var(--mantine-color-yellow-6)" />
                </Tooltip>
              )}
            </Group>
          </Group>

          {/* 当前值 */}
          <Text
            size="xl"
            fw={700}
            c={hasExpectedRange && !withinRange ? 'yellow.6' : undefined}
            style={{
              transition: 'color 0.3s ease',
            }}
          >
            {formatValue(data.value, decimals)} {data.unit}
          </Text>

          {/* 期望值范围 */}
          {hasExpectedRange && (
            <Group gap={4}>
              <IconTarget size={12} color="var(--mantine-color-gray-6)" />
              <Text size="xs" c="dimmed">
                期望: {formatValue(expectedRange.min, decimals)} - {formatValue(expectedRange.max, decimals)}{' '}
                {data.unit}
              </Text>
            </Group>
          )}
        </Stack>
      </Card>
    )
  }
)

ExecutionMetricCard.displayName = 'ExecutionMetricCard'

export function ExecutionMetricsCard({
  debug = false,
  throttleMs = 100,
  testPlanName,
  currentStep,
  expectedRanges,
}: ExecutionMetricsCardProps) {
  const { metrics, isConnected, error, reconnect } = useMonitoringWebSocket({
    debug: debug,
    autoReconnect: true,
    reconnectDelay: 3000,
    throttleMs: throttleMs,
  })

  // 计算在范围内的指标数量
  const metricsInRange = metrics
    ? Object.keys(metrics).filter((key) => {
        const metricKey = key as keyof typeof metrics
        const metricData = metrics[metricKey]
        const expectedRange = expectedRanges?.[metricKey]
        return isWithinRange(metricData.value, expectedRange)
      }).length
    : 0

  const totalMetrics = metrics ? Object.keys(metrics).length : 5
  const complianceRate = totalMetrics > 0 ? (metricsInRange / totalMetrics) * 100 : 100

  return (
    <Card withBorder radius="md" padding="lg">
      <Stack gap="md">
        {/* 头部 - 测试执行信息 */}
        <Group justify="space-between">
          <Group gap="xs">
            <IconActivity size={20} />
            <Title order={4}>测试执行监控</Title>
          </Group>
          <Group gap="xs">
            <Badge
              color={isConnected ? 'green' : 'red'}
              variant="dot"
              leftSection={isConnected ? <IconPlugConnected size={14} /> : <IconPlugConnectedX size={14} />}
            >
              {isConnected ? 'WebSocket 已连接' : 'WebSocket 断开'}
            </Badge>
            {!isConnected && (
              <Tooltip label="重新连接">
                <ActionIcon variant="subtle" color="blue" onClick={reconnect}>
                  <IconRefresh size={16} />
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
        </Group>

        {/* 测试上下文信息 */}
        {testPlanName ? (
          <Paper withBorder radius="sm" p="xs" bg="gray.0">
            <Stack gap={4}>
              <Group justify="space-between">
                <Text size="sm" fw={500}>
                  {testPlanName}
                </Text>
                {currentStep && (
                  <Badge size="sm" variant="light">
                    步骤 {currentStep.index + 1}/{currentStep.total}
                  </Badge>
                )}
              </Group>
              {currentStep?.title && (
                <Text size="xs" c="dimmed">
                  当前: {currentStep.title}
                </Text>
              )}
            </Stack>
          </Paper>
        ) : (
          <Alert color="blue" variant="light" title="提示">
            当前未检测到正在执行的测试计划。此监控组件显示通过 Demo 模式启动的测试。若您在"测试管理"标签页中启动了测试，请在该标签页中查看执行状态。
          </Alert>
        )}

        {/* 指标合规率 */}
        {expectedRanges && metrics && (
          <Stack gap="xs">
            <Group justify="space-between">
              <Text size="sm" c="dimmed">
                指标合规率
              </Text>
              <Text size="sm" fw={500} c={complianceRate < 80 ? 'yellow.6' : 'green.6'}>
                {complianceRate.toFixed(0)}%
              </Text>
            </Group>
            <Progress
              value={complianceRate}
              color={complianceRate >= 80 ? 'green' : complianceRate >= 60 ? 'yellow' : 'red'}
              size="sm"
              radius="sm"
            />
            <Text size="xs" c="dimmed">
              {metricsInRange}/{totalMetrics} 项指标在期望范围内
            </Text>
          </Stack>
        )}

        {/* 错误提示 */}
        {error && (
          <Alert color="red" variant="light" title="连接错误">
            {error.message}
          </Alert>
        )}

        {/* 指标网格 */}
        {metrics ? (
          <SimpleGrid cols={2} spacing="md">
            <ExecutionMetricCard
              label={METRIC_LABELS.throughput}
              data={metrics.throughput}
              decimals={2}
              expectedRange={expectedRanges?.throughput}
            />
            <ExecutionMetricCard
              label={METRIC_LABELS.snr}
              data={metrics.snr}
              decimals={2}
              expectedRange={expectedRanges?.snr}
            />
            <ExecutionMetricCard
              label={METRIC_LABELS.quiet_zone_uniformity}
              data={metrics.quiet_zone_uniformity}
              decimals={3}
              expectedRange={expectedRanges?.quiet_zone_uniformity}
            />
            <ExecutionMetricCard
              label={METRIC_LABELS.eirp}
              data={metrics.eirp}
              decimals={2}
              expectedRange={expectedRanges?.eirp}
            />
            <ExecutionMetricCard
              label={METRIC_LABELS.temperature}
              data={metrics.temperature}
              decimals={1}
              expectedRange={expectedRanges?.temperature}
            />
          </SimpleGrid>
        ) : (
          // 骨架加载状态
          <SimpleGrid cols={2} spacing="md">
            {Array.from({ length: 5 }).map((_, index) => (
              <Card key={index} withBorder padding="sm" radius="sm">
                <Stack gap="xs">
                  <Group justify="space-between">
                    <Skeleton height={16} width="60%" />
                    <Skeleton height={20} width={60} />
                  </Group>
                  <Skeleton height={32} width="80%" />
                  <Skeleton height={12} width="70%" />
                </Stack>
              </Card>
            ))}
          </SimpleGrid>
        )}

        {/* 调试信息 */}
        {debug && metrics && (
          <Card withBorder padding="xs" radius="sm" bg="gray.0">
            <Text size="xs" c="dimmed" style={{ fontFamily: 'monospace' }}>
              最后更新: {metrics.throughput.timestamp}
            </Text>
          </Card>
        )}
      </Stack>
    </Card>
  )
}
