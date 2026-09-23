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
} from '@mantine/core'
import {
  IconDashboard,
  IconGridDots,
  IconFileImport,
  IconLink,
  IconAntenna,
} from '@tabler/icons-react'
import {
  ProbeCalibrationDashboard,
  ProbeCalibrationGrid,
  ProbeCalibrationDetail,
  PatternImportPanel,
  RFChainDiagramPanel,
  PatternMeasurementPanel,
} from './components'
import type { CalibrationType } from '../../types/probeCalibration'

interface ProbeCalibrationPageProps {
  defaultTab?: 'dashboard' | 'probes' | 'pattern_measurement' | 'pattern_import' | 'rf_chain_diagram'
  labProfileId: string
  chamberId: string
  chamberName?: string
  probeCount: number
}

export function ProbeCalibrationPage({ defaultTab = 'dashboard', labProfileId, chamberId, chamberName, probeCount }: ProbeCalibrationPageProps) {
  const [activeTab, setActiveTab] = useState<string | null>(defaultTab)
  const [selectedProbeId, setSelectedProbeId] = useState<number | null>(null)
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false)

  const handleProbeSelect = (probeId: number) => {
    setSelectedProbeId(probeId)
    setIsDetailModalOpen(true)
  }

  const handleStartCalibration = (type: CalibrationType) => {
    if (type === 'pattern') {
      setActiveTab('pattern_measurement')
      return
    }
    // The other calibration workflows remain outside P2-32B.
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
            <Tabs.Tab value="pattern_measurement" leftSection={<IconAntenna size={14} />}>
              方向图测量
            </Tabs.Tab>
            <Tabs.Tab value="pattern_import" leftSection={<IconFileImport size={14} />}>
              Pattern 导入
            </Tabs.Tab>
            <Tabs.Tab value="rf_chain_diagram" leftSection={<IconLink size={14} />}>
              链路 + 路损启动
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="dashboard" pt="md">
            <ProbeCalibrationDashboard
              chamberId={chamberId}
              chamberName={chamberName}
              onStartCalibration={handleStartCalibration}
              onViewProbe={handleViewProbe}
            />
          </Tabs.Panel>

          <Tabs.Panel value="probes" pt="md">
            <ProbeCalibrationGrid
              chamberId={chamberId}
              onProbeSelect={handleProbeSelect}
              selectedProbeId={selectedProbeId ?? undefined}
              probeCount={probeCount}
            />
          </Tabs.Panel>

          <Tabs.Panel value="pattern_measurement" pt="md">
            <PatternMeasurementPanel
              labProfileId={labProfileId}
              chamberId={chamberId}
              probeCount={probeCount}
            />
          </Tabs.Panel>

          <Tabs.Panel value="pattern_import" pt="md">
            <PatternImportPanel chamberId={chamberId} />
          </Tabs.Panel>

          <Tabs.Panel value="rf_chain_diagram" pt="md">
            <RFChainDiagramPanel />
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
            chamberId={chamberId}
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
