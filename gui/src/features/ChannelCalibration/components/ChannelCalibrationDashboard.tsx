/**
 * Channel Calibration Dashboard Component
 *
 * Main dashboard showing channel calibration overview and status
 */
import {
  Grid,
  Paper,
  Text,
  Stack,
  Group,
  RingProgress,
  ThemeIcon,
  Badge,
  Button,
  Card,
  Skeleton,
  Alert,
  ActionIcon,
  Tooltip,
  SimpleGrid,
} from '@mantine/core'
import {
  IconCircleCheck,
  IconAlertTriangle,
  IconX,
  IconRefresh,
  IconCalendar,
  IconWaveSine,
  IconAlertCircle,
  IconChevronRight,
  IconClock,
  IconRadar,
  IconBroadcast,
  IconCircleDot,
  IconSphere,
  IconDeviceMobile,
} from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import {
  getCalibrationStatus,
  getCalibrationHistory,
  formatValidityStatus,
  getCalibrationTypeName,
  formatCalibrationDate,
} from '../../../api/channelCalibrationService'
import type {
  ChannelCalibrationType,
  ValidityStatus,
  ChannelCalibrationStatusSummary,
} from '../../../types/channelCalibration'

interface ChannelCalibrationDashboardProps {
  onStartCalibration?: (type: ChannelCalibrationType) => void
  onViewDetails?: (type: ChannelCalibrationType, calibrationId: string) => void
}

const CALIBRATION_TYPES: {
  type: ChannelCalibrationType
  label: string
  icon: typeof IconWaveSine
  validity: string
  description: string
}[] = [
  {
    type: 'temporal',
    label: '时域诊断（非标准 PDP）',
    icon: IconClock,
    validity: '无正式有效期',
    description: '代理或模拟材料不提供标准 PDP 判词',
  },
  {
    type: 'doppler',
    label: '多普勒诊断',
    icon: IconRadar,
    validity: '无正式有效期',
    description: '工程诊断材料，未获正式方法资格',
  },
  {
    type: 'spatial_correlation',
    label: '空间相关性诊断',
    icon: IconBroadcast,
    validity: '无正式有效期',
    description: '工程诊断材料，未获正式方法资格',
  },
  {
    type: 'angular_spread',
    label: '角度扩展诊断',
    icon: IconCircleDot,
    validity: '无正式有效期',
    description: '工程诊断材料，未获正式方法资格',
  },
  {
    type: 'quiet_zone',
    label: 'Quiet Zone',
    icon: IconSphere,
    validity: '180 days',
    description: 'Field uniformity validation',
  },
  {
    type: 'eis',
    label: 'EIS诊断',
    icon: IconDeviceMobile,
    validity: '无正式有效期',
    description: '工程诊断材料，未获正式方法资格',
  },
]

function getStatusFromSummary(
  summary: ChannelCalibrationStatusSummary,
  type: ChannelCalibrationType
): { status: ValidityStatus; lastCalibrated?: string; nextDue?: string } {
  switch (type) {
    case 'temporal':
      return {
        status: summary.temporal_status,
        lastCalibrated: summary.temporal_last_calibrated,
        nextDue: summary.temporal_next_due,
      }
    case 'doppler':
      return {
        status: summary.doppler_status,
        lastCalibrated: summary.doppler_last_calibrated,
        nextDue: summary.doppler_next_due,
      }
    case 'spatial_correlation':
      return {
        status: summary.spatial_correlation_status,
        lastCalibrated: summary.spatial_correlation_last_calibrated,
        nextDue: summary.spatial_correlation_next_due,
      }
    case 'angular_spread':
      return {
        status: summary.angular_spread_status,
        lastCalibrated: summary.angular_spread_last_calibrated,
        nextDue: summary.angular_spread_next_due,
      }
    case 'quiet_zone':
      return {
        status: summary.quiet_zone_status,
        lastCalibrated: summary.quiet_zone_last_calibrated,
        nextDue: summary.quiet_zone_next_due,
      }
    case 'eis':
      return {
        status: summary.eis_status,
        lastCalibrated: summary.eis_last_calibrated,
        nextDue: summary.eis_next_due,
      }
    default:
      return { status: 'unknown' }
  }
}

export function ChannelCalibrationDashboard({
  onStartCalibration,
  onViewDetails,
}: ChannelCalibrationDashboardProps) {
  const {
    data: statusSummary,
    isLoading: isLoadingStatus,
    error: statusError,
    refetch: refetchStatus,
  } = useQuery({
    queryKey: ['channelCalibrationStatus'],
    queryFn: getCalibrationStatus,
    staleTime: 30000,
  })

  const { data: historyData, isLoading: isLoadingHistory } = useQuery({
    queryKey: ['channelCalibrationHistory', { limit: 10 }],
    queryFn: () => getCalibrationHistory({ limit: 10 }),
    staleTime: 30000,
  })

  if (statusError) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
        Failed to load channel calibration status: {(statusError as Error).message}
      </Alert>
    )
  }

  // Calculate statistics
  const validCount = statusSummary
    ? CALIBRATION_TYPES.filter(
        (t) => getStatusFromSummary(statusSummary, t.type).status === 'valid'
      ).length
    : 0
  const expiringCount = statusSummary
    ? CALIBRATION_TYPES.filter(
        (t) => getStatusFromSummary(statusSummary, t.type).status === 'expiring_soon'
      ).length
    : 0
  const expiredCount = statusSummary
    ? CALIBRATION_TYPES.filter(
        (t) => getStatusFromSummary(statusSummary, t.type).status === 'expired'
      ).length
    : 0
  const unknownCount = CALIBRATION_TYPES.length - validCount - expiringCount - expiredCount

  const passRate = Math.round((validCount / CALIBRATION_TYPES.length) * 100)

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size="lg" variant="light" color="blue">
            <IconWaveSine size={20} />
          </ThemeIcon>
          <Text size="lg" fw={600}>
            Channel Calibration Status
          </Text>
        </Group>
        <Tooltip label="Refresh">
          <ActionIcon variant="light" onClick={() => refetchStatus()}>
            <IconRefresh size={16} />
          </ActionIcon>
        </Tooltip>
      </Group>

      <Grid>
        {/* Overall Status */}
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md" withBorder h="100%">
            {isLoadingStatus ? (
              <Skeleton height={180} />
            ) : (
              <Stack align="center" gap="md">
                <Text size="sm" fw={600}>
                  Overall Channel Calibration
                </Text>
                <RingProgress
                  size={140}
                  thickness={12}
                  sections={[
                    { value: (validCount / CALIBRATION_TYPES.length) * 100, color: 'green' },
                    { value: (expiringCount / CALIBRATION_TYPES.length) * 100, color: 'yellow' },
                    { value: (expiredCount / CALIBRATION_TYPES.length) * 100, color: 'red' },
                    { value: (unknownCount / CALIBRATION_TYPES.length) * 100, color: 'gray' },
                  ]}
                  label={
                    <Stack gap={0} align="center">
                      <Text size="xl" fw={700}>
                        {passRate}%
                      </Text>
                      <Text size="xs" c="dimmed">
                        Valid
                      </Text>
                    </Stack>
                  }
                />
                <Group gap="xs">
                  <Badge color="green" variant="light">
                    {validCount} Valid
                  </Badge>
                  {expiringCount > 0 && (
                    <Badge color="yellow" variant="light">
                      {expiringCount} Expiring
                    </Badge>
                  )}
                  {expiredCount > 0 && (
                    <Badge color="red" variant="light">
                      {expiredCount} Expired
                    </Badge>
                  )}
                </Group>
              </Stack>
            )}
          </Paper>
        </Grid.Col>

        {/* Quick Stats */}
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper p="md" withBorder h="100%">
            <Text size="sm" fw={600} mb="md">
              Calibration Statistics
            </Text>
            {isLoadingStatus ? (
              <Skeleton height={120} />
            ) : (
              <SimpleGrid cols={4}>
                <Card padding="sm" radius="md" withBorder>
                  <Stack gap={4} align="center">
                    <ThemeIcon size="lg" color="green" variant="light">
                      <IconCircleCheck size={20} />
                    </ThemeIcon>
                    <Text size="xl" fw={700}>
                      {validCount}
                    </Text>
                    <Text size="xs" c="dimmed">
                      Valid
                    </Text>
                  </Stack>
                </Card>
                <Card padding="sm" radius="md" withBorder>
                  <Stack gap={4} align="center">
                    <ThemeIcon size="lg" color="yellow" variant="light">
                      <IconAlertTriangle size={20} />
                    </ThemeIcon>
                    <Text size="xl" fw={700}>
                      {expiringCount}
                    </Text>
                    <Text size="xs" c="dimmed">
                      Expiring Soon
                    </Text>
                  </Stack>
                </Card>
                <Card padding="sm" radius="md" withBorder>
                  <Stack gap={4} align="center">
                    <ThemeIcon size="lg" color="red" variant="light">
                      <IconX size={20} />
                    </ThemeIcon>
                    <Text size="xl" fw={700}>
                      {expiredCount}
                    </Text>
                    <Text size="xs" c="dimmed">
                      Expired
                    </Text>
                  </Stack>
                </Card>
                <Card padding="sm" radius="md" withBorder>
                  <Stack gap={4} align="center">
                    <ThemeIcon size="lg" color="gray" variant="light">
                      <IconCircleDot size={20} />
                    </ThemeIcon>
                    <Text size="xl" fw={700}>
                      {unknownCount}
                    </Text>
                    <Text size="xs" c="dimmed">
                      Unknown
                    </Text>
                  </Stack>
                </Card>
              </SimpleGrid>
            )}
          </Paper>
        </Grid.Col>

        {/* Calibration Types Grid */}
        <Grid.Col span={12}>
          <Paper p="md" withBorder>
            <Text size="sm" fw={600} mb="md">
              Calibration Types
            </Text>
            {isLoadingStatus ? (
              <Skeleton height={200} />
            ) : (
              <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
                {CALIBRATION_TYPES.map(({ type, label, icon: Icon, validity, description }) => {
                  const typeStatus = statusSummary
                    ? getStatusFromSummary(statusSummary, type)
                    : { status: 'unknown' as ValidityStatus }
                  const { color } = formatValidityStatus(typeStatus.status)

                  return (
                    <Card key={type} padding="md" radius="md" withBorder>
                      <Group justify="space-between" mb="xs">
                        <Group gap="sm">
                          <ThemeIcon size="md" variant="light" color={color}>
                            <Icon size={16} />
                          </ThemeIcon>
                          <Text size="sm" fw={600}>
                            {label}
                          </Text>
                        </Group>
                        <Badge color={color} variant="light" size="sm">
                          {typeStatus.status}
                        </Badge>
                      </Group>

                      <Text size="xs" c="dimmed" mb="xs">
                        {description}
                      </Text>

                      <Stack gap={4}>
                        <Group gap="xs">
                          <IconCalendar size={12} />
                          <Text size="xs" c="dimmed">
                            Validity: {validity}
                          </Text>
                        </Group>
                        {typeStatus.lastCalibrated && (
                          <Text size="xs" c="dimmed">
                            Last: {formatCalibrationDate(typeStatus.lastCalibrated)}
                          </Text>
                        )}
                      </Stack>

                      <Button
                        size="xs"
                        variant="light"
                        fullWidth
                        mt="sm"
                        onClick={() => onStartCalibration?.(type)}
                      >
                        Start Calibration
                      </Button>
                    </Card>
                  )
                })}
              </SimpleGrid>
            )}
          </Paper>
        </Grid.Col>

        {/* Recent Calibrations */}
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper p="md" withBorder>
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Recent Calibrations
              </Text>
              <Badge variant="light">{historyData?.total ?? 0} total</Badge>
            </Group>
            {isLoadingHistory ? (
              <Skeleton height={150} />
            ) : historyData && historyData.items.length > 0 ? (
              <Stack gap="xs">
                {historyData.items.slice(0, 5).map((item) => (
                  <Group key={item.calibration_id} justify="space-between">
                    <Group gap="xs">
                      <Badge
                        size="xs"
                        color={item.validation_pass === null ? 'yellow' : item.validation_pass ? 'green' : 'red'}
                        variant="light"
                      >
                        {item.validation_pass === null ? 'UNKNOWN' : item.validation_pass ? 'PASS' : 'FAIL'}
                      </Badge>
                      <Text size="sm">{getCalibrationTypeName(item.calibration_type)}</Text>
                    </Group>
                    <Group gap="xs">
                      <Text size="xs" c="dimmed">
                        {formatCalibrationDate(item.calibrated_at)}
                      </Text>
                      <ActionIcon
                        size="xs"
                        variant="subtle"
                        onClick={() => onViewDetails?.(item.calibration_type, item.calibration_id)}
                      >
                        <IconChevronRight size={14} />
                      </ActionIcon>
                    </Group>
                  </Group>
                ))}
              </Stack>
            ) : (
              <Text size="sm" c="dimmed" ta="center">
                No calibration history available
              </Text>
            )}
          </Paper>
        </Grid.Col>

        <Grid.Col span={12}>
          <Alert color="yellow">标准 PDP 覆盖未判定：时域诊断没有独立参考验证，不能计入标准信道覆盖率。</Alert>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
