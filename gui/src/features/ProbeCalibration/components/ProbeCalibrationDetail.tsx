/**
 * Probe Calibration Detail Component
 *
 * Detailed view of calibration data for a single probe
 */
import {
  Paper,
  Text,
  Stack,
  Group,
  Badge,
  Tabs,
  Table,
  Skeleton,
  Alert,
  Card,
  ThemeIcon,
  Button,
  Divider,
  ActionIcon,
  Tooltip,
} from '@mantine/core'
import {
  IconAlertCircle,
  IconWaveSine,
  IconCircuitResistor,
  IconFocusCentered,
  IconAntenna,
  IconLink,
  IconRefresh,
  IconHistory,
  IconX,
} from '@tabler/icons-react'
import { useProbeCalibrationData } from '../../../hooks/useProbeCalibration'
import { CalibrationStatusBadge } from './CalibrationStatusBadge'
import type {
  AmplitudeCalibrationResponse,
  PhaseCalibrationResponse,
  PolarizationCalibrationResponse,
  PatternCalibrationResponse,
  LinkCalibrationResponse,
  ValidityStatus,
} from '../../../types/probeCalibration'

interface ProbeCalibrationDetailProps {
  probeId: number
  onClose?: () => void
  onInvalidate?: (calibrationType: string, calibrationId: string) => void
  onViewHistory?: (calibrationType: string) => void
}

export function ProbeCalibrationDetail({
  probeId,
  onClose,
  onInvalidate,
  onViewHistory,
}: ProbeCalibrationDetailProps) {
  const {
    data: probeData,
    isLoading,
    error,
    refetch,
  } = useProbeCalibrationData(probeId)

  if (error) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} color="red" title="Error">
        Failed to load probe calibration data: {(error as Error).message}
      </Alert>
    )
  }

  if (isLoading) {
    return (
      <Stack gap="md">
        <Skeleton height={60} />
        <Skeleton height={200} />
        <Skeleton height={200} />
      </Stack>
    )
  }

  if (!probeData) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} color="yellow" title="No Data">
        No calibration data found for probe {probeId}
      </Alert>
    )
  }

  const { validity_status } = probeData

  return (
    <Stack gap="md">
      {/* Header */}
      <Paper p="md" withBorder>
        <Group justify="space-between">
          <Group gap="md">
            <ThemeIcon size="xl" variant="light" color="blue">
              <IconAntenna size={24} />
            </ThemeIcon>
            <Stack gap={0}>
              <Text size="lg" fw={600}>
                Probe {probeId}
              </Text>
              <Group gap="xs">
                <CalibrationStatusBadge
                  status={validity_status.overall_status as ValidityStatus}
                  size="sm"
                />
              </Group>
            </Stack>
          </Group>
          <Group gap="xs">
            <Tooltip label="Refresh">
              <ActionIcon variant="light" onClick={() => refetch()}>
                <IconRefresh size={16} />
              </ActionIcon>
            </Tooltip>
            {onClose && (
              <Tooltip label="Close">
                <ActionIcon variant="light" onClick={onClose}>
                  <IconX size={16} />
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
        </Group>
      </Paper>

      {/* Calibration Tabs */}
      <Tabs defaultValue="amplitude">
        <Tabs.List>
          <Tabs.Tab
            value="amplitude"
            leftSection={<IconWaveSine size={14} />}
            rightSection={
              validity_status.amplitude && (
                <CalibrationStatusBadge
                  status={validity_status.amplitude.status as ValidityStatus}
                  size="xs"
                  showLabel={false}
                />
              )
            }
          >
            Amplitude
          </Tabs.Tab>
          <Tabs.Tab
            value="phase"
            leftSection={<IconCircuitResistor size={14} />}
            rightSection={
              validity_status.phase && (
                <CalibrationStatusBadge
                  status={validity_status.phase.status as ValidityStatus}
                  size="xs"
                  showLabel={false}
                />
              )
            }
          >
            Phase
          </Tabs.Tab>
          <Tabs.Tab
            value="polarization"
            leftSection={<IconFocusCentered size={14} />}
            rightSection={
              validity_status.polarization && (
                <CalibrationStatusBadge
                  status={validity_status.polarization.status as ValidityStatus}
                  size="xs"
                  showLabel={false}
                />
              )
            }
          >
            Polarization
          </Tabs.Tab>
          <Tabs.Tab
            value="pattern"
            leftSection={<IconAntenna size={14} />}
            rightSection={
              validity_status.pattern && (
                <CalibrationStatusBadge
                  status={validity_status.pattern.status as ValidityStatus}
                  size="xs"
                  showLabel={false}
                />
              )
            }
          >
            Pattern
          </Tabs.Tab>
          <Tabs.Tab
            value="link"
            leftSection={<IconLink size={14} />}
            rightSection={
              validity_status.link && (
                <CalibrationStatusBadge
                  status={validity_status.link.status as ValidityStatus}
                  size="xs"
                  showLabel={false}
                />
              )
            }
          >
            Link
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="amplitude" pt="md">
          <AmplitudeCalibrationPanel
            data={probeData.amplitude_calibration}
            onInvalidate={onInvalidate}
            onViewHistory={() => onViewHistory?.('amplitude')}
          />
        </Tabs.Panel>

        <Tabs.Panel value="phase" pt="md">
          <PhaseCalibrationPanel
            data={probeData.phase_calibration}
            onInvalidate={onInvalidate}
            onViewHistory={() => onViewHistory?.('phase')}
          />
        </Tabs.Panel>

        <Tabs.Panel value="polarization" pt="md">
          <PolarizationCalibrationPanel
            data={probeData.polarization_calibration}
            onInvalidate={onInvalidate}
            onViewHistory={() => onViewHistory?.('polarization')}
          />
        </Tabs.Panel>

        <Tabs.Panel value="pattern" pt="md">
          <PatternCalibrationPanel
            data={probeData.pattern_calibrations}
            onViewHistory={() => onViewHistory?.('pattern')}
          />
        </Tabs.Panel>

        <Tabs.Panel value="link" pt="md">
          <LinkCalibrationPanel
            data={probeData.link_calibration}
            onInvalidate={onInvalidate}
            onViewHistory={() => onViewHistory?.('link')}
          />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}

interface PanelProps<T> {
  data: T | undefined | null
  onInvalidate?: (type: string, id: string) => void
  onViewHistory?: () => void
}

function AmplitudeCalibrationPanel({
  data,
  onInvalidate,
  onViewHistory,
}: PanelProps<AmplitudeCalibrationResponse>) {
  if (!data) {
    return <NoDataAlert message="No amplitude calibration data available" />
  }

  return (
    <Stack gap="md">
      <CalibrationMetadata
        calibratedAt={data.calibrated_at}
        calibratedBy={data.calibrated_by}
        validUntil={data.valid_until}
        status={data.status}
        calibrationId={data.id}
        calibrationType="amplitude"
        onInvalidate={onInvalidate}
        onViewHistory={onViewHistory}
      />

      <Card padding="sm" withBorder>
        <Text size="sm" fw={600} mb="sm">
          Gain Data
        </Text>
        <Table size="sm" striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Frequency (MHz)</Table.Th>
              <Table.Th>TX Gain (dBi)</Table.Th>
              <Table.Th>RX Gain (dBi)</Table.Th>
              <Table.Th>TX Uncertainty</Table.Th>
              <Table.Th>RX Uncertainty</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.frequency_points_mhz.map((freq, idx) => (
              <Table.Tr key={idx}>
                <Table.Td>{freq}</Table.Td>
                <Table.Td>{data.tx_gain_dbi[idx]?.toFixed(2)}</Table.Td>
                <Table.Td>{data.rx_gain_dbi[idx]?.toFixed(2)}</Table.Td>
                <Table.Td>
                  <Badge size="xs" variant="outline">
                    ±{data.tx_gain_uncertainty_db[idx]?.toFixed(2)} dB
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Badge size="xs" variant="outline">
                    ±{data.rx_gain_uncertainty_db[idx]?.toFixed(2)} dB
                  </Badge>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  )
}

function PhaseCalibrationPanel({
  data,
  onInvalidate,
  onViewHistory,
}: PanelProps<PhaseCalibrationResponse>) {
  if (!data) {
    return <NoDataAlert message="No phase calibration data available" />
  }

  return (
    <Stack gap="md">
      <CalibrationMetadata
        calibratedAt={data.calibrated_at}
        calibratedBy={data.calibrated_by}
        validUntil={data.valid_until}
        status={data.status}
        calibrationId={data.id}
        calibrationType="phase"
        onInvalidate={onInvalidate}
        onViewHistory={onViewHistory}
      />

      <Group gap="md">
        <Badge variant="light">Reference Probe: {data.reference_probe_id}</Badge>
        <Badge variant="light">Polarization: {data.polarization}</Badge>
      </Group>

      <Card padding="sm" withBorder>
        <Text size="sm" fw={600} mb="sm">
          Phase Data
        </Text>
        <Table size="sm" striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Frequency (MHz)</Table.Th>
              <Table.Th>Phase Offset (deg)</Table.Th>
              <Table.Th>Group Delay (ns)</Table.Th>
              <Table.Th>Uncertainty</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {data.frequency_points_mhz.map((freq, idx) => (
              <Table.Tr key={idx}>
                <Table.Td>{freq}</Table.Td>
                <Table.Td>{data.phase_offset_deg[idx]?.toFixed(1)}°</Table.Td>
                <Table.Td>{data.group_delay_ns[idx]?.toFixed(2)}</Table.Td>
                <Table.Td>
                  <Badge size="xs" variant="outline">
                    ±{data.phase_uncertainty_deg[idx]?.toFixed(1)}°
                  </Badge>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  )
}

function PolarizationCalibrationPanel({
  data,
  onInvalidate,
  onViewHistory,
}: PanelProps<PolarizationCalibrationResponse>) {
  if (!data) {
    return <NoDataAlert message="No polarization calibration data available" />
  }

  const isLinear = data.probe_type === 'dual_linear' || data.probe_type === 'dual_slant'

  return (
    <Stack gap="md">
      <CalibrationMetadata
        calibratedAt={data.calibrated_at}
        calibratedBy={data.calibrated_by}
        validUntil={data.valid_until}
        status={data.status}
        calibrationId={data.id}
        calibrationType="polarization"
        onInvalidate={onInvalidate}
        onViewHistory={onViewHistory}
      />

      <Group gap="md">
        <Badge variant="light">Probe Type: {data.probe_type}</Badge>
        {!isLinear && data.polarization_hand && (
          <Badge variant="light">Hand: {data.polarization_hand}</Badge>
        )}
      </Group>

      <Card padding="sm" withBorder>
        <Text size="sm" fw={600} mb="sm">
          {isLinear ? 'Cross-Polarization Isolation' : 'Axial Ratio'}
        </Text>
        {isLinear ? (
          <Stack gap="xs">
            <Group justify="space-between">
              <Text size="sm">V-to-H Isolation:</Text>
              <Badge color={data.v_to_h_isolation_db && data.v_to_h_isolation_db >= 20 ? 'green' : 'yellow'}>
                {data.v_to_h_isolation_db?.toFixed(1)} dB
              </Badge>
            </Group>
            <Group justify="space-between">
              <Text size="sm">H-to-V Isolation:</Text>
              <Badge color={data.h_to_v_isolation_db && data.h_to_v_isolation_db >= 20 ? 'green' : 'yellow'}>
                {data.h_to_v_isolation_db?.toFixed(1)} dB
              </Badge>
            </Group>
            <Text size="xs" c="dimmed">
              Requirement: XPD ≥ 20 dB
            </Text>
          </Stack>
        ) : (
          <Stack gap="xs">
            <Group justify="space-between">
              <Text size="sm">Axial Ratio:</Text>
              <Badge color={data.axial_ratio_db && data.axial_ratio_db <= 3 ? 'green' : 'yellow'}>
                {data.axial_ratio_db?.toFixed(2)} dB
              </Badge>
            </Group>
            <Text size="xs" c="dimmed">
              Requirement: AR ≤ 3 dB
            </Text>
          </Stack>
        )}
      </Card>
    </Stack>
  )
}

function PatternCalibrationPanel({
  data,
  onViewHistory,
}: { data: PatternCalibrationResponse[] | undefined | null; onViewHistory?: () => void }) {
  if (!data || data.length === 0) {
    return <NoDataAlert message="No pattern calibration data available" />
  }

  const latestPattern = data[0]

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Group gap="xs">
          <Text size="sm" c="dimmed">
            Calibrated: {new Date(latestPattern.measured_at).toLocaleDateString()}
          </Text>
          {latestPattern.measured_by && (
            <Text size="sm" c="dimmed">
              by {latestPattern.measured_by}
            </Text>
          )}
        </Group>
        <Button
          size="xs"
          variant="subtle"
          leftSection={<IconHistory size={14} />}
          onClick={onViewHistory}
        >
          History
        </Button>
      </Group>

      <Group gap="md">
        <Badge variant="light">Frequency: {latestPattern.frequency_mhz} MHz</Badge>
        <Badge variant="light">Polarization: {latestPattern.polarization}</Badge>
      </Group>

      <Card padding="sm" withBorder>
        <Text size="sm" fw={600} mb="sm">
          Pattern Parameters
        </Text>
        <Group grow>
          <Stack gap={4} align="center">
            <Text size="xs" c="dimmed">
              Peak Gain
            </Text>
            <Text size="lg" fw={700}>
              {latestPattern.peak_gain_dbi?.toFixed(1)} dBi
            </Text>
          </Stack>
          <Stack gap={4} align="center">
            <Text size="xs" c="dimmed">
              HPBW (Az)
            </Text>
            <Text size="lg" fw={700}>
              {latestPattern.hpbw_azimuth_deg?.toFixed(0)}°
            </Text>
          </Stack>
          <Stack gap={4} align="center">
            <Text size="xs" c="dimmed">
              HPBW (El)
            </Text>
            <Text size="lg" fw={700}>
              {latestPattern.hpbw_elevation_deg?.toFixed(0)}°
            </Text>
          </Stack>
          <Stack gap={4} align="center">
            <Text size="xs" c="dimmed">
              F/B Ratio
            </Text>
            <Text size="lg" fw={700}>
              {latestPattern.front_to_back_ratio_db?.toFixed(1)} dB
            </Text>
          </Stack>
        </Group>
      </Card>

      {data.length > 1 && (
        <Text size="xs" c="dimmed">
          + {data.length - 1} more frequency measurements available
        </Text>
      )}
    </Stack>
  )
}

function LinkCalibrationPanel({
  data,
  onInvalidate,
  onViewHistory,
}: PanelProps<LinkCalibrationResponse>) {
  if (!data) {
    return <NoDataAlert message="No link calibration data available" />
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Group gap="xs">
          <Text size="sm" c="dimmed">
            Calibrated: {new Date(data.calibrated_at).toLocaleDateString()}
          </Text>
          {data.calibrated_by && (
            <Text size="sm" c="dimmed">
              by {data.calibrated_by}
            </Text>
          )}
        </Group>
        <Group gap="xs">
          <Button
            size="xs"
            variant="subtle"
            leftSection={<IconHistory size={14} />}
            onClick={onViewHistory}
          >
            History
          </Button>
          {onInvalidate && (
            <Button
              size="xs"
              variant="subtle"
              color="red"
              onClick={() => onInvalidate('link', data.id)}
            >
              Invalidate
            </Button>
          )}
        </Group>
      </Group>

      <Group gap="md">
        <Badge variant="light">Type: {data.calibration_type}</Badge>
        <Badge variant="light">Frequency: {data.frequency_mhz} MHz</Badge>
        <Badge color={data.validation_pass ? 'green' : 'red'}>
          {data.validation_pass ? 'PASS' : 'FAIL'}
        </Badge>
      </Group>

      <Card padding="sm" withBorder>
        <Text size="sm" fw={600} mb="sm">
          Measurement Results
        </Text>
        <Stack gap="xs">
          <Group justify="space-between">
            <Text size="sm">Known Gain:</Text>
            <Text size="sm" fw={600}>
              {data.known_gain_dbi?.toFixed(2)} dBi
            </Text>
          </Group>
          <Group justify="space-between">
            <Text size="sm">Measured Gain:</Text>
            <Text size="sm" fw={600}>
              {data.measured_gain_dbi?.toFixed(2)} dBi
            </Text>
          </Group>
          <Divider />
          <Group justify="space-between">
            <Text size="sm">Deviation:</Text>
            <Badge color={Math.abs(data.deviation_db || 0) <= data.threshold_db ? 'green' : 'red'}>
              {data.deviation_db?.toFixed(3)} dB
            </Badge>
          </Group>
          <Group justify="space-between">
            <Text size="sm">Threshold:</Text>
            <Text size="sm" c="dimmed">
              ±{data.threshold_db} dB
            </Text>
          </Group>
        </Stack>
      </Card>

      {data.standard_dut_type && (
        <Card padding="sm" withBorder>
          <Text size="sm" fw={600} mb="sm">
            Standard DUT
          </Text>
          <Group gap="md">
            <Badge variant="outline">{data.standard_dut_type}</Badge>
            {data.standard_dut_model && <Text size="sm">{data.standard_dut_model}</Text>}
            {data.standard_dut_serial && (
              <Text size="xs" c="dimmed">
                S/N: {data.standard_dut_serial}
              </Text>
            )}
          </Group>
        </Card>
      )}
    </Stack>
  )
}

function CalibrationMetadata({
  calibratedAt,
  calibratedBy,
  validUntil,
  status,
  calibrationId,
  calibrationType,
  onInvalidate,
  onViewHistory,
}: {
  calibratedAt: string
  calibratedBy?: string
  validUntil: string
  status: string
  calibrationId: string
  calibrationType: string
  onInvalidate?: (type: string, id: string) => void
  onViewHistory?: () => void
}) {
  return (
    <Group justify="space-between">
      <Group gap="xs">
        <Text size="sm" c="dimmed">
          Calibrated: {new Date(calibratedAt).toLocaleDateString()}
        </Text>
        {calibratedBy && (
          <Text size="sm" c="dimmed">
            by {calibratedBy}
          </Text>
        )}
        <Divider orientation="vertical" />
        <Text size="sm" c="dimmed">
          Valid until: {new Date(validUntil).toLocaleDateString()}
        </Text>
        <CalibrationStatusBadge status={status as ValidityStatus} size="xs" />
      </Group>
      <Group gap="xs">
        <Button
          size="xs"
          variant="subtle"
          leftSection={<IconHistory size={14} />}
          onClick={onViewHistory}
        >
          History
        </Button>
        {onInvalidate && (
          <Button
            size="xs"
            variant="subtle"
            color="red"
            onClick={() => onInvalidate(calibrationType, calibrationId)}
          >
            Invalidate
          </Button>
        )}
      </Group>
    </Group>
  )
}

function NoDataAlert({ message }: { message: string }) {
  return (
    <Alert icon={<IconAlertCircle size={16} />} color="gray">
      {message}
    </Alert>
  )
}
