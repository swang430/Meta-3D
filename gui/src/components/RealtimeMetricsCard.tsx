/**
 * Realtime Metrics Card Component
 *
 * Demonstrates the useMonitoringWebSocket hook with live data from backend.
 * Can be integrated into Dashboard or Monitoring panels.
 *
 * Phase 2.6 Optimizations:
 * - Memoized helper functions for performance
 * - React.memo for component-level optimization
 * - Extracted MetricCard sub-component
 * - Smooth transitions for value changes
 */

import { Card, Title, Stack, Group, Text, Badge, Alert, SimpleGrid, ActionIcon, Tooltip, Skeleton } from '@mantine/core'
import { IconPlugConnected, IconPlugConnectedX, IconRefresh, IconActivity } from '@tabler/icons-react'
import { useMonitoringWebSocket, type MonitoringMetricData } from '../hooks/useMonitoringWebSocket'
import { memo, useMemo, useCallback } from 'react'

interface RealtimeMetricsCardProps {
  /** Show debug info (default: false) */
  debug?: boolean
  /** Throttle interval in ms (default: 100) */
  throttleMs?: number
}

// Memoized helper functions
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

const formatValue = (value: number, decimals: number = 2): string => {
  return value.toFixed(decimals)
}

// Metric display labels in Chinese
const METRIC_LABELS: Record<string, string> = {
  throughput: '吞吐量',
  snr: '信噪比 (SNR)',
  quiet_zone_uniformity: '静区均匀度',
  eirp: 'EIRP',
  temperature: '温度',
}

// Sub-component for individual metric display (memoized)
interface MetricCardProps {
  label: string
  data: MonitoringMetricData
  decimals?: number
}

const MetricCard = memo(({ label, data, decimals = 2 }: MetricCardProps) => {
  return (
    <Card
      withBorder
      padding="sm"
      radius="sm"
      style={{
        transition: 'all 0.3s ease',
      }}
    >
      <Stack gap="xs">
        <Group justify="space-between">
          <Text size="sm" c="dimmed">
            {label}
          </Text>
          <Badge size="xs" color={getStatusColor(data.status)}>
            {data.status}
          </Badge>
        </Group>
        <Text
          size="xl"
          fw={700}
          style={{
            transition: 'color 0.3s ease',
          }}
        >
          {formatValue(data.value, decimals)} {data.unit}
        </Text>
      </Stack>
    </Card>
  )
})

MetricCard.displayName = 'MetricCard'

export function RealtimeMetricsCard({ debug = false, throttleMs = 100 }: RealtimeMetricsCardProps) {
  const { metrics, isConnected, error, reconnect } = useMonitoringWebSocket({
    debug: debug,
    autoReconnect: true,
    reconnectDelay: 3000,
    throttleMs: throttleMs,
  })

  return (
    <Card withBorder radius="md" padding="lg">
      <Stack gap="md">
        {/* Header */}
        <Group justify="space-between">
          <Group gap="xs">
            <IconActivity size={20} />
            <Title order={4}>实时监控指标</Title>
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

        {/* Error Alert */}
        {error && (
          <Alert color="red" variant="light" title="连接错误">
            {error.message}
          </Alert>
        )}

        {/* Metrics Grid */}
        {metrics ? (
          <SimpleGrid cols={2} spacing="md">
            <MetricCard label={METRIC_LABELS.throughput} data={metrics.throughput} decimals={2} />
            <MetricCard label={METRIC_LABELS.snr} data={metrics.snr} decimals={2} />
            <MetricCard
              label={METRIC_LABELS.quiet_zone_uniformity}
              data={metrics.quiet_zone_uniformity}
              decimals={3}
            />
            <MetricCard label={METRIC_LABELS.eirp} data={metrics.eirp} decimals={2} />
            <MetricCard label={METRIC_LABELS.temperature} data={metrics.temperature} decimals={1} />
          </SimpleGrid>
        ) : (
          <SimpleGrid cols={2} spacing="md">
            {Array.from({ length: 5 }).map((_, index) => (
              <Card key={index} withBorder padding="sm" radius="sm">
                <Stack gap="xs">
                  <Group justify="space-between">
                    <Skeleton height={16} width="60%" />
                    <Skeleton height={20} width={60} />
                  </Group>
                  <Skeleton height={32} width="80%" />
                </Stack>
              </Card>
            ))}
          </SimpleGrid>
        )}

        {/* Debug Info */}
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
