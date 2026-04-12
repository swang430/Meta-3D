/**
 * Channel Calibration Page
 *
 * Main page for channel calibration management
 */
import { useState } from 'react'
import { Container, Tabs, Title, Stack, Modal, Text, Group, Button } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import {
  IconWaveSine,
  IconHistory,
  IconSettings,
  IconCircleCheck,
  IconX,
} from '@tabler/icons-react'
import { ChannelCalibrationDashboard } from './components/ChannelCalibrationDashboard'
import type { ChannelCalibrationType } from '../../types/channelCalibration'
import {
  startTemporalCalibration,
  startDopplerCalibration,
  startSpatialCorrelationCalibration,
  startAngularSpreadCalibration,
  startQuietZoneCalibration,
  startEISValidation,
  getCalibrationTypeName,
} from '../../api/channelCalibrationService'

export function ChannelCalibrationPage() {
  const [activeTab, setActiveTab] = useState<string | null>('dashboard')
  const [startModalOpen, setStartModalOpen] = useState(false)
  const [selectedType, setSelectedType] = useState<ChannelCalibrationType | null>(null)
  const [isStarting, setIsStarting] = useState(false)

  const handleStartCalibration = (type: ChannelCalibrationType) => {
    setSelectedType(type)
    setStartModalOpen(true)
  }

  const handleConfirmStart = async () => {
    if (!selectedType) return

    setIsStarting(true)
    try {
      let result
      switch (selectedType) {
        case 'temporal':
          result = await startTemporalCalibration({
            scenario: { type: 'UMa', condition: 'LOS', fc_ghz: 3.5 },
            calibrated_by: 'system',
          })
          break
        case 'doppler':
          result = await startDopplerCalibration({
            velocity_kmh: 120,
            fc_ghz: 3.5,
            calibrated_by: 'system',
          })
          break
        case 'spatial_correlation':
          result = await startSpatialCorrelationCalibration({
            scenario: { type: 'UMa', condition: 'NLOS', fc_ghz: 3.5 },
            test_dut: { antenna_spacing_wavelengths: 0.5 },
            calibrated_by: 'system',
          })
          break
        case 'angular_spread':
          result = await startAngularSpreadCalibration({
            scenario: { type: 'UMa', condition: 'NLOS', fc_ghz: 3.5 },
            calibrated_by: 'system',
          })
          break
        case 'quiet_zone':
          result = await startQuietZoneCalibration({
            quiet_zone: { shape: 'sphere', diameter_m: 1.0 },
            fc_ghz: 3.5,
            calibrated_by: 'system',
          })
          break
        case 'eis':
          result = await startEISValidation({
            test_config: { fc_ghz: 3.5 },
            dut: { model: 'Reference DUT' },
            measured_by: 'system',
          })
          break
      }

      notifications.show({
        title: 'Calibration Started',
        message: `${getCalibrationTypeName(selectedType)} calibration completed successfully`,
        color: 'green',
        icon: <IconCircleCheck size={16} />,
      })

      setStartModalOpen(false)
    } catch (error) {
      notifications.show({
        title: 'Calibration Failed',
        message: (error as Error).message,
        color: 'red',
        icon: <IconX size={16} />,
      })
    } finally {
      setIsStarting(false)
    }
  }

  const handleViewDetails = (type: ChannelCalibrationType, calibrationId: string) => {
    // TODO: Navigate to detail view
    console.log('View details:', type, calibrationId)
  }

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        <Title order={2}>Channel Calibration</Title>

        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab value="dashboard" leftSection={<IconWaveSine size={16} />}>
              Dashboard
            </Tabs.Tab>
            <Tabs.Tab value="history" leftSection={<IconHistory size={16} />}>
              History
            </Tabs.Tab>
            <Tabs.Tab value="settings" leftSection={<IconSettings size={16} />}>
              Settings
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="dashboard" pt="md">
            <ChannelCalibrationDashboard
              onStartCalibration={handleStartCalibration}
              onViewDetails={handleViewDetails}
            />
          </Tabs.Panel>

          <Tabs.Panel value="history" pt="md">
            <Text c="dimmed">Calibration history view coming soon...</Text>
          </Tabs.Panel>

          <Tabs.Panel value="settings" pt="md">
            <Text c="dimmed">Calibration settings coming soon...</Text>
          </Tabs.Panel>
        </Tabs>
      </Stack>

      {/* Start Calibration Modal */}
      <Modal
        opened={startModalOpen}
        onClose={() => setStartModalOpen(false)}
        title={`Start ${selectedType ? getCalibrationTypeName(selectedType) : ''} Calibration`}
      >
        <Stack>
          <Text size="sm">
            This will start a {selectedType ? getCalibrationTypeName(selectedType) : ''} calibration
            with default parameters.
          </Text>
          <Text size="xs" c="dimmed">
            For custom parameters, use the advanced calibration wizard.
          </Text>
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={() => setStartModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleConfirmStart} loading={isStarting}>
              Start Calibration
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Container>
  )
}
