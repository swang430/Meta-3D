/**
 * Probe Calibration Page
 *
 * Main page for probe calibration management
 */
import { useState } from 'react'
import {
  Container,
  Tabs,
  Stack,
  Modal,
  Title,
  Group,
  ActionIcon,
  Tooltip,
} from '@mantine/core'
import {
  IconDashboard,
  IconGridDots,
  IconSettings,
  IconX,
} from '@tabler/icons-react'
import {
  ProbeCalibrationDashboard,
  ProbeCalibrationGrid,
  ProbeCalibrationDetail,
} from './components'
import type { CalibrationType } from '../../types/probeCalibration'

interface ProbeCalibrationPageProps {
  defaultTab?: 'dashboard' | 'probes'
}

export function ProbeCalibrationPage({ defaultTab = 'dashboard' }: ProbeCalibrationPageProps) {
  const [activeTab, setActiveTab] = useState<string | null>(defaultTab)
  const [selectedProbeId, setSelectedProbeId] = useState<number | null>(null)
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false)

  const handleProbeSelect = (probeId: number) => {
    setSelectedProbeId(probeId)
    setIsDetailModalOpen(true)
  }

  const handleStartCalibration = (type: CalibrationType) => {
    // TODO: Open calibration wizard for the specific type
    console.log('Start calibration:', type)
  }

  const handleViewProbe = (probeId: number) => {
    setSelectedProbeId(probeId)
    setIsDetailModalOpen(true)
  }

  const handleInvalidate = (calibrationType: string, calibrationId: string) => {
    // TODO: Implement invalidation confirmation dialog
    console.log('Invalidate:', calibrationType, calibrationId)
  }

  const handleViewHistory = (calibrationType: string) => {
    // TODO: Open history modal
    console.log('View history:', calibrationType)
  }

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab value="dashboard" leftSection={<IconDashboard size={14} />}>
              Dashboard
            </Tabs.Tab>
            <Tabs.Tab value="probes" leftSection={<IconGridDots size={14} />}>
              Probe Grid
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="dashboard" pt="md">
            <ProbeCalibrationDashboard
              onStartCalibration={handleStartCalibration}
              onViewProbe={handleViewProbe}
            />
          </Tabs.Panel>

          <Tabs.Panel value="probes" pt="md">
            <ProbeCalibrationGrid
              onProbeSelect={handleProbeSelect}
              selectedProbeId={selectedProbeId ?? undefined}
              probeCount={32}
            />
          </Tabs.Panel>
        </Tabs>
      </Stack>

      {/* Probe Detail Modal */}
      <Modal
        opened={isDetailModalOpen}
        onClose={() => setIsDetailModalOpen(false)}
        size="xl"
        title={
          <Group gap="xs">
            <Title order={4}>Probe {selectedProbeId} Calibration</Title>
          </Group>
        }
      >
        {selectedProbeId !== null && (
          <ProbeCalibrationDetail
            probeId={selectedProbeId}
            onClose={() => setIsDetailModalOpen(false)}
            onInvalidate={handleInvalidate}
            onViewHistory={handleViewHistory}
          />
        )}
      </Modal>
    </Container>
  )
}
