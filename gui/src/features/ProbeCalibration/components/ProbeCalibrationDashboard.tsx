/**
 * Probe Calibration Dashboard Component
 *
 * Main dashboard showing calibration overview and status
 */
import { useState } from 'react'
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
  List,
  Skeleton,
  Alert,
  Divider,
  ActionIcon,
  Tooltip,
} from '@mantine/core'
import {
  IconCircleCheck,
  IconAlertTriangle,
  IconX,
  IconRefresh,
  IconCalendar,
  IconAntenna,
  IconWaveSine,
  IconCircuitResistor,
  IconFocusCentered,
  IconLink,
  IconAlertCircle,
  IconChevronRight,
} from '@tabler/icons-react'
import {
  useValidityReport,
  useExpiringCalibrations,
  useLinkValidity,
} from '../../../hooks/useProbeCalibration'
import { CalibrationStatusBadge, OverallStatusIndicator } from './CalibrationStatusBadge'
import type { ValidityStatus, CalibrationType } from '../../../types/probeCalibration'

interface ProbeCalibrationDashboardProps {
  onStartCalibration?: (type: CalibrationType) => void
  onViewProbe?: (probeId: number) => void
  onViewExpiring?: () => void
  onViewExpired?: () => void
}

const CALIBRATION_TYPES: {
  type: CalibrationType
  label: string
  icon: typeof IconAntenna
  validity: string
}[] = [
  { type: 'amplitude', label: 'Amplitude', icon: IconWaveSine, validity: '90 days' },
  { type: 'phase', label: 'Phase', icon: IconCircuitResistor, validity: '90 days' },
  { type: 'polarization', label: 'Polarization', icon: IconFocusCentered, validity: '180 days' },
  { type: 'pattern', label: 'Pattern', icon: IconAntenna, validity: '365 days' },
  { type: 'link', label: 'Link', icon: IconLink, validity: '7 days' },
]

export function ProbeCalibrationDashboard({
  onStartCalibration,
  onViewProbe,
  onViewExpiring,
  onViewExpired,
}: ProbeCalibrationDashboardProps) {
  const {
    data: validityReport,
    isLoading: isLoadingReport,
    error: reportError,
    refetch: refetchReport,
  } = useValidityReport()

  const {
    data: expiringData,
    isLoading: isLoadingExpiring,
  } = useExpiringCalibrations(7)

  const {
    data: linkValidity,
    isLoading: isLoadingLink,
  } = useLinkValidity()

  if (reportError) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
        Failed to load calibration report: {(reportError as Error).message}
      </Alert>
    )
  }

  const totalProbes = validityReport?.total_probes ?? 32
  const validProbes = validityReport?.valid_probes ?? 0
  const expiredProbes = validityReport?.expired_probes ?? 0
  const expiringProbes = validityReport?.expiring_soon_probes ?? 0
  const passRate = totalProbes > 0 ? Math.round((validProbes / totalProbes) * 100) : 0

  const overallStatus: ValidityStatus =
    expiredProbes > 0 ? 'expired' : expiringProbes > 0 ? 'expiring_soon' : validProbes > 0 ? 'valid' : 'unknown'

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between">
        <Group gap="xs">
          <ThemeIcon size="lg" variant="light" color="blue">
            <IconAntenna size={20} />
          </ThemeIcon>
          <Text size="lg" fw={600}>
            Probe Calibration Status
          </Text>
        </Group>
        <Tooltip label="Refresh">
          <ActionIcon variant="light" onClick={() => refetchReport()}>
            <IconRefresh size={16} />
          </ActionIcon>
        </Tooltip>
      </Group>

      <Grid>
        {/* Overall Status */}
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md" withBorder h="100%">
            {isLoadingReport ? (
              <Skeleton height={160} />
            ) : (
              <Stack align="center" gap="md">
                <Text size="sm" fw={600}>
                  Overall Calibration Status
                </Text>
                <RingProgress
                  size={140}
                  thickness={12}
                  sections={[
                    { value: (validProbes / totalProbes) * 100, color: 'green' },
                    { value: (expiringProbes / totalProbes) * 100, color: 'yellow' },
                    { value: (expiredProbes / totalProbes) * 100, color: 'red' },
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
                <OverallStatusIndicator
                  status={overallStatus}
                  validCount={validProbes}
                  expiringSoonCount={expiringProbes}
                  expiredCount={expiredProbes}
                />
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
            {isLoadingReport ? (
              <Skeleton height={120} />
            ) : (
              <Grid>
                <Grid.Col span={3}>
                  <Card padding="sm" radius="md" withBorder>
                    <Stack gap={4} align="center">
                      <ThemeIcon size="lg" color="green" variant="light">
                        <IconCircleCheck size={20} />
                      </ThemeIcon>
                      <Text size="xl" fw={700}>
                        {validProbes}
                      </Text>
                      <Text size="xs" c="dimmed">
                        Valid Probes
                      </Text>
                    </Stack>
                  </Card>
                </Grid.Col>
                <Grid.Col span={3}>
                  <Card padding="sm" radius="md" withBorder>
                    <Stack gap={4} align="center">
                      <ThemeIcon size="lg" color="yellow" variant="light">
                        <IconAlertTriangle size={20} />
                      </ThemeIcon>
                      <Text size="xl" fw={700}>
                        {expiringProbes}
                      </Text>
                      <Text size="xs" c="dimmed">
                        Expiring Soon
                      </Text>
                    </Stack>
                  </Card>
                </Grid.Col>
                <Grid.Col span={3}>
                  <Card padding="sm" radius="md" withBorder>
                    <Stack gap={4} align="center">
                      <ThemeIcon size="lg" color="red" variant="light">
                        <IconX size={20} />
                      </ThemeIcon>
                      <Text size="xl" fw={700}>
                        {expiredProbes}
                      </Text>
                      <Text size="xs" c="dimmed">
                        Expired
                      </Text>
                    </Stack>
                  </Card>
                </Grid.Col>
                <Grid.Col span={3}>
                  <Card padding="sm" radius="md" withBorder>
                    <Stack gap={4} align="center">
                      <ThemeIcon size="lg" color="blue" variant="light">
                        <IconAntenna size={20} />
                      </ThemeIcon>
                      <Text size="xl" fw={700}>
                        {totalProbes}
                      </Text>
                      <Text size="xs" c="dimmed">
                        Total Probes
                      </Text>
                    </Stack>
                  </Card>
                </Grid.Col>
              </Grid>
            )}
          </Paper>
        </Grid.Col>

        {/* Calibration Types */}
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper p="md" withBorder>
            <Text size="sm" fw={600} mb="md">
              Calibration Types
            </Text>
            <Stack gap="xs">
              {CALIBRATION_TYPES.map(({ type, label, icon: Icon, validity }) => (
                <Group key={type} justify="space-between">
                  <Group gap="sm">
                    <ThemeIcon size="sm" variant="light" color="gray">
                      <Icon size={14} />
                    </ThemeIcon>
                    <Text size="sm">{label}</Text>
                  </Group>
                  <Group gap="xs">
                    <Badge size="xs" variant="outline">
                      {validity}
                    </Badge>
                    <Button
                      size="xs"
                      variant="light"
                      onClick={() => onStartCalibration?.(type)}
                    >
                      Start
                    </Button>
                  </Group>
                </Group>
              ))}
            </Stack>
          </Paper>
        </Grid.Col>

        {/* Link Calibration Status */}
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper p="md" withBorder>
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Link Calibration Status
              </Text>
              <Badge
                color={
                  linkValidity?.status === 'valid'
                    ? 'green'
                    : linkValidity?.status === 'expiring_soon'
                      ? 'yellow'
                      : 'red'
                }
              >
                {linkValidity?.status || 'Unknown'}
              </Badge>
            </Group>
            {isLoadingLink ? (
              <Skeleton height={80} />
            ) : linkValidity ? (
              <Stack gap="xs">
                {linkValidity.calibrated_at && (
                  <Group gap="xs">
                    <IconCalendar size={14} />
                    <Text size="xs" c="dimmed">
                      Last calibration: {new Date(linkValidity.calibrated_at).toLocaleDateString()}
                    </Text>
                  </Group>
                )}
                {linkValidity.days_remaining !== undefined && (
                  <Text size="sm">
                    Valid for <strong>{linkValidity.days_remaining}</strong> more days
                  </Text>
                )}
                {linkValidity.days_overdue !== undefined && (
                  <Text size="sm" c="red">
                    Expired <strong>{linkValidity.days_overdue}</strong> days ago
                  </Text>
                )}
                {linkValidity.deviation_db !== undefined && (
                  <Text size="xs" c="dimmed">
                    Last deviation: {linkValidity.deviation_db.toFixed(3)} dB
                  </Text>
                )}
                <Button
                  size="xs"
                  variant="light"
                  fullWidth
                  mt="sm"
                  onClick={() => onStartCalibration?.('link')}
                >
                  Run Link Calibration
                </Button>
              </Stack>
            ) : (
              <Text size="sm" c="dimmed">
                No link calibration data available
              </Text>
            )}
          </Paper>
        </Grid.Col>

        {/* Expiring Calibrations */}
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper p="md" withBorder>
            <Group justify="space-between" mb="md">
              <Text size="sm" fw={600}>
                Expiring Soon (7 days)
              </Text>
              <Badge color="yellow" variant="light">
                {expiringData?.count ?? 0}
              </Badge>
            </Group>
            {isLoadingExpiring ? (
              <Skeleton height={100} />
            ) : expiringData && expiringData.calibrations.length > 0 ? (
              <Stack gap="xs">
                <List size="sm" spacing="xs">
                  {expiringData.calibrations.slice(0, 5).map((cal, idx) => (
                    <List.Item key={idx}>
                      <Group gap="xs">
                        <Text size="sm">
                          Probe {cal.probe_id} - {cal.calibration_type}
                        </Text>
                        <Badge size="xs" color="yellow">
                          {cal.days_remaining}d
                        </Badge>
                      </Group>
                    </List.Item>
                  ))}
                </List>
                {expiringData.count > 5 && (
                  <Button
                    size="xs"
                    variant="subtle"
                    rightSection={<IconChevronRight size={14} />}
                    onClick={onViewExpiring}
                  >
                    View all {expiringData.count} expiring
                  </Button>
                )}
              </Stack>
            ) : (
              <Text size="sm" c="dimmed" ta="center">
                No calibrations expiring soon
              </Text>
            )}
          </Paper>
        </Grid.Col>

        {/* Recommendations */}
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper p="md" withBorder>
            <Text size="sm" fw={600} mb="md">
              Recommendations
            </Text>
            {isLoadingReport ? (
              <Skeleton height={100} />
            ) : validityReport && validityReport.recommendations.length > 0 ? (
              <Stack gap="xs">
                {validityReport.recommendations.slice(0, 5).map((rec, idx) => (
                  <Group key={idx} gap="xs" wrap="nowrap">
                    <Badge
                      size="xs"
                      color={
                        rec.priority === 'critical'
                          ? 'red'
                          : rec.priority === 'high'
                            ? 'orange'
                            : 'blue'
                      }
                    >
                      {rec.priority}
                    </Badge>
                    <Text size="xs" lineClamp={1}>
                      Probe {rec.probe_id}: {rec.action}
                    </Text>
                  </Group>
                ))}
              </Stack>
            ) : (
              <Stack gap="xs" align="center">
                <ThemeIcon size="lg" color="green" variant="light">
                  <IconCircleCheck size={20} />
                </ThemeIcon>
                <Text size="sm" c="dimmed" ta="center">
                  All calibrations are up to date
                </Text>
              </Stack>
            )}
          </Paper>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
