/**
 * Probe Calibration Grid Component
 *
 * Grid view showing all probes with their calibration status
 */
import { useState, useMemo } from 'react'
import {
  Paper,
  SimpleGrid,
  Text,
  Group,
  Stack,
  ActionIcon,
  Tooltip,
  Box,
  SegmentedControl,
  TextInput,
  Badge,
  Skeleton,
  Alert,
} from '@mantine/core'
import {
  IconSearch,
  IconGridDots,
  IconList,
  IconEye,
  IconRefresh,
  IconAlertCircle,
} from '@tabler/icons-react'
import { useValidityReport, useProbeValidity } from '../../../hooks/useProbeCalibration'
import { CalibrationStatusBadge, ProbeCalibrationStatusSummary } from './CalibrationStatusBadge'
import type { ValidityStatus, CalibrationType } from '../../../types/probeCalibration'

interface ProbeCalibrationGridProps {
  onProbeSelect?: (probeId: number) => void
  selectedProbeId?: number
  probeCount?: number
}

export function ProbeCalibrationGrid({
  onProbeSelect,
  selectedProbeId,
  probeCount = 32,
}: ProbeCalibrationGridProps) {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [searchQuery, setSearchQuery] = useState('')
  const [filterStatus, setFilterStatus] = useState<ValidityStatus | 'all'>('all')

  // Generate probe IDs string for API call
  const probeIdsString = useMemo(() => {
    return Array.from({ length: probeCount }, (_, i) => i).join(',')
  }, [probeCount])

  const {
    data: validityReport,
    isLoading,
    error,
    refetch,
  } = useValidityReport(probeIdsString)

  // Create a map of probe validity from the report
  const probeStatusMap = useMemo(() => {
    const map = new Map<number, ValidityStatus>()

    if (!validityReport) return map

    // Initialize all probes as unknown
    for (let i = 0; i < probeCount; i++) {
      map.set(i, 'unknown')
    }

    // Mark valid probes
    // Note: The API returns counts, not individual statuses
    // We need to infer from expired/expiring lists
    validityReport.expired_calibrations.forEach((cal) => {
      const current = map.get(cal.probe_id)
      if (current !== 'expired') {
        map.set(cal.probe_id, 'expired')
      }
    })

    validityReport.expiring_soon_calibrations.forEach((cal) => {
      const current = map.get(cal.probe_id)
      if (current !== 'expired') {
        map.set(cal.probe_id, 'expiring_soon')
      }
    })

    // The rest are valid if they have calibration data
    // This is a simplification - in real app, we'd need per-probe status
    return map
  }, [validityReport, probeCount])

  // Filter probes based on search and status
  const filteredProbes = useMemo(() => {
    const probes = Array.from({ length: probeCount }, (_, i) => i)

    return probes.filter((probeId) => {
      // Search filter
      if (searchQuery && !`Probe ${probeId}`.toLowerCase().includes(searchQuery.toLowerCase())) {
        return false
      }

      // Status filter
      if (filterStatus !== 'all') {
        const status = probeStatusMap.get(probeId) || 'unknown'
        if (status !== filterStatus) return false
      }

      return true
    })
  }, [probeCount, searchQuery, filterStatus, probeStatusMap])

  if (error) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
        Failed to load probe calibration status: {(error as Error).message}
      </Alert>
    )
  }

  return (
    <Stack gap="md">
      {/* Toolbar */}
      <Group justify="space-between">
        <Group gap="sm">
          <TextInput
            placeholder="Search probes..."
            leftSection={<IconSearch size={16} />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.currentTarget.value)}
            size="sm"
            style={{ width: 200 }}
          />
          <SegmentedControl
            value={filterStatus}
            onChange={(v) => setFilterStatus(v as ValidityStatus | 'all')}
            size="xs"
            data={[
              { label: 'All', value: 'all' },
              { label: 'Valid', value: 'valid' },
              { label: 'Expiring', value: 'expiring_soon' },
              { label: 'Expired', value: 'expired' },
            ]}
          />
        </Group>
        <Group gap="xs">
          <Tooltip label="Refresh">
            <ActionIcon variant="light" onClick={() => refetch()}>
              <IconRefresh size={16} />
            </ActionIcon>
          </Tooltip>
          <SegmentedControl
            value={viewMode}
            onChange={(v) => setViewMode(v as 'grid' | 'list')}
            size="xs"
            data={[
              { label: <IconGridDots size={14} />, value: 'grid' },
              { label: <IconList size={14} />, value: 'list' },
            ]}
          />
        </Group>
      </Group>

      {/* Summary */}
      {validityReport && (
        <Group gap="md">
          <Badge color="green" variant="light" size="lg">
            {validityReport.valid_probes} Valid
          </Badge>
          <Badge color="yellow" variant="light" size="lg">
            {validityReport.expiring_soon_probes} Expiring
          </Badge>
          <Badge color="red" variant="light" size="lg">
            {validityReport.expired_probes} Expired
          </Badge>
          <Badge color="gray" variant="light" size="lg">
            {validityReport.total_probes -
              validityReport.valid_probes -
              validityReport.expiring_soon_probes -
              validityReport.expired_probes}{' '}
            Unknown
          </Badge>
        </Group>
      )}

      {/* Grid View */}
      {isLoading ? (
        <SimpleGrid cols={{ base: 4, sm: 6, md: 8 }}>
          {Array.from({ length: probeCount }).map((_, i) => (
            <Skeleton key={i} height={80} radius="md" />
          ))}
        </SimpleGrid>
      ) : viewMode === 'grid' ? (
        <SimpleGrid cols={{ base: 4, sm: 6, md: 8 }}>
          {filteredProbes.map((probeId) => (
            <ProbeCard
              key={probeId}
              probeId={probeId}
              status={probeStatusMap.get(probeId) || 'unknown'}
              isSelected={probeId === selectedProbeId}
              onClick={() => onProbeSelect?.(probeId)}
            />
          ))}
        </SimpleGrid>
      ) : (
        <Stack gap="xs">
          {filteredProbes.map((probeId) => (
            <ProbeListItem
              key={probeId}
              probeId={probeId}
              status={probeStatusMap.get(probeId) || 'unknown'}
              isSelected={probeId === selectedProbeId}
              onClick={() => onProbeSelect?.(probeId)}
            />
          ))}
        </Stack>
      )}

      {/* Empty state */}
      {filteredProbes.length === 0 && (
        <Paper p="xl" withBorder>
          <Text ta="center" c="dimmed">
            No probes match the current filter
          </Text>
        </Paper>
      )}
    </Stack>
  )
}

interface ProbeCardProps {
  probeId: number
  status: ValidityStatus
  isSelected?: boolean
  onClick?: () => void
}

function ProbeCard({ probeId, status, isSelected, onClick }: ProbeCardProps) {
  const statusColors: Record<ValidityStatus, string> = {
    valid: 'green',
    expiring_soon: 'yellow',
    expired: 'red',
    unknown: 'gray',
  }

  return (
    <Paper
      p="xs"
      withBorder
      style={{
        cursor: 'pointer',
        borderColor: isSelected ? 'var(--mantine-color-blue-5)' : undefined,
        borderWidth: isSelected ? 2 : 1,
        backgroundColor: isSelected ? 'var(--mantine-color-blue-0)' : undefined,
      }}
      onClick={onClick}
    >
      <Stack gap={4} align="center">
        <Box
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            backgroundColor: `var(--mantine-color-${statusColors[status]}-1)`,
            border: `2px solid var(--mantine-color-${statusColors[status]}-5)`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Text size="xs" fw={600} c={statusColors[status]}>
            {probeId}
          </Text>
        </Box>
        <CalibrationStatusBadge status={status} size="xs" showLabel={false} />
      </Stack>
    </Paper>
  )
}

interface ProbeListItemProps {
  probeId: number
  status: ValidityStatus
  isSelected?: boolean
  onClick?: () => void
}

function ProbeListItem({ probeId, status, isSelected, onClick }: ProbeListItemProps) {
  const { data: probeValidity } = useProbeValidity(probeId)

  return (
    <Paper
      p="sm"
      withBorder
      style={{
        cursor: 'pointer',
        borderColor: isSelected ? 'var(--mantine-color-blue-5)' : undefined,
        borderWidth: isSelected ? 2 : 1,
        backgroundColor: isSelected ? 'var(--mantine-color-blue-0)' : undefined,
      }}
      onClick={onClick}
    >
      <Group justify="space-between">
        <Group gap="sm">
          <Text fw={600} size="sm">
            Probe {probeId}
          </Text>
          <CalibrationStatusBadge status={status} size="sm" />
        </Group>
        {probeValidity && (
          <ProbeCalibrationStatusSummary
            amplitude={probeValidity.amplitude?.status as ValidityStatus}
            phase={probeValidity.phase?.status as ValidityStatus}
            polarization={probeValidity.polarization?.status as ValidityStatus}
            pattern={probeValidity.pattern?.status as ValidityStatus}
            link={probeValidity.link?.status as ValidityStatus}
          />
        )}
        <ActionIcon variant="subtle" size="sm">
          <IconEye size={14} />
        </ActionIcon>
      </Group>
    </Paper>
  )
}
