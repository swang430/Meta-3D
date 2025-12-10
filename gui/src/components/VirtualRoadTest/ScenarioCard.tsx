/**
 * Scenario Card Component
 *
 * Display scenario summary in card format
 */

import { useState } from 'react'
import { Card, Text, Badge, Group, Button, Stack, Tooltip } from '@mantine/core'
import {
  IconMapPin,
  IconClock,
  IconRuler,
  IconPlayerPlay,
  IconInfoCircle,
  IconTransform,
  IconSettings,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import type { ScenarioSummary } from '../../types/roadTest'
import { TestExecutionModal } from './TestExecutionModal'
import { ScenarioDetailModal } from './ScenarioDetailModal'
import { generateTestPlanFromScenario, canConvertToTestPlan } from '../../utils/scenarioToTestPlan'
import { createTestPlan } from '../../api/service'

interface Props {
  scenario: ScenarioSummary
  onRefresh?: () => void
}

const CATEGORY_COLORS: Record<string, string> = {
  standard: 'blue',
  functional: 'green',
  performance: 'orange',
  environment: 'teal',
  extreme: 'red',
  custom: 'violet',
}

const CATEGORY_LABELS: Record<string, string> = {
  standard: '⭐ Standard',
  functional: '🔧 Functional',
  performance: '🚀 Performance',
  environment: '🌍 Environment',
  extreme: '⚠️ Extreme',
  custom: '✏️ Custom',
}

// 统计配置了多少个步骤
const countConfiguredSteps = (scenario: ScenarioSummary): number => {
  if (!scenario.step_configuration) return 0
  const config = scenario.step_configuration
  let count = 0
  if (config.chamber_init) count++
  if (config.network_config) count++
  if (config.base_station_setup) count++
  if (config.ota_mapper) count++
  if (config.route_execution) count++
  if (config.kpi_validation) count++
  if (config.report_generation) count++
  return count
}

export default function ScenarioCard({ scenario, onRefresh }: Props) {
  const configuredStepsCount = countConfiguredSteps(scenario)
  const [executionModalOpened, setExecutionModalOpened] = useState(false)
  const [detailModalOpened, setDetailModalOpened] = useState(false)
  const [converting, setConverting] = useState(false)

  const handleRun = () => {
    setExecutionModalOpened(true)
  }

  const handleViewDetails = () => {
    setDetailModalOpened(true)
  }

  const handleConvertToTestPlan = async () => {
    // Validate scenario can be converted
    const validation = canConvertToTestPlan(scenario)
    if (!validation.canConvert) {
      notifications.show({
        title: 'Cannot Convert',
        message: validation.reason || 'Scenario cannot be converted to test plan',
        color: 'red',
      })
      return
    }

    setConverting(true)
    try {
      // Generate test plan payload from scenario
      const testPlanPayload = generateTestPlanFromScenario(scenario)

      // Create test plan via API
      const response = await createTestPlan(testPlanPayload)

      // Backend returns plan directly, not wrapped in {plan: ...}
      const planName = (response as any).plan?.name || (response as any).name || 'test plan'

      notifications.show({
        title: 'Test Plan Created',
        message: `Successfully created "${planName}"`,
        color: 'green',
      })

      // TODO: Navigate to Test Management when routing is available
      // navigate(`/test-management/plans?id=${response.plan.id}`)

      // Refresh parent component if callback provided
      if (onRefresh) {
        onRefresh()
      }
    } catch (error: any) {
      console.error('Failed to convert scenario to test plan:', error)
      notifications.show({
        title: 'Conversion Failed',
        message: error?.response?.data?.detail || 'Failed to create test plan',
        color: 'red',
      })
    } finally {
      setConverting(false)
    }
  }

  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder>
      {/* Header */}
      <Group justify="space-between" mb="xs">
        <Group gap="xs">
          <Badge color={CATEGORY_COLORS[scenario.category]} variant="light" size="sm">
            {CATEGORY_LABELS[scenario.category]}
          </Badge>
          {configuredStepsCount > 0 && (
            <Tooltip label={`已配置 ${configuredStepsCount}/7 个测试步骤`}>
              <Badge color="cyan" variant="dot" size="sm" leftSection={<IconSettings size={12} />}>
                自定义步骤
              </Badge>
            </Tooltip>
          )}
        </Group>
        <Badge color="gray" variant="outline" size="xs">
          {scenario.source}
        </Badge>
      </Group>

      {/* Title */}
      <Text fw={600} size="lg" mb="xs">
        {scenario.name}
      </Text>

      {/* Description */}
      <Text size="sm" c="dimmed" lineClamp={2} mb="md">
        {scenario.description || 'No description available'}
      </Text>

      {/* Tags */}
      {scenario.tags.length > 0 && (
        <Group gap="xs" mb="md">
          {scenario.tags.slice(0, 3).map((tag) => (
            <Badge key={tag} size="xs" variant="dot" color="gray">
              {tag}
            </Badge>
          ))}
          {scenario.tags.length > 3 && (
            <Badge size="xs" variant="dot" color="gray">
              +{scenario.tags.length - 3} more
            </Badge>
          )}
        </Group>
      )}

      {/* Stats */}
      <Stack gap="xs" mb="md">
        <Group gap="xs">
          <IconClock size={14} />
          <Text size="xs" c="dimmed">
            Duration: {Math.round(scenario.duration_s)}s (~
            {Math.round(scenario.duration_s / 60)} min)
          </Text>
        </Group>

        <Group gap="xs">
          <IconRuler size={14} />
          <Text size="xs" c="dimmed">
            Distance: {Math.round(scenario.distance_m)}m (~
            {(scenario.distance_m / 1000).toFixed(1)} km)
          </Text>
        </Group>

        {scenario.created_at && (
          <Group gap="xs">
            <IconMapPin size={14} />
            <Text size="xs" c="dimmed">
              Created: {new Date(scenario.created_at).toLocaleDateString()}
            </Text>
          </Group>
        )}
      </Stack>

      {/* Actions */}
      <Stack gap="xs">
        <Group gap="xs">
          <Button
            flex={1}
            variant="light"
            leftSection={<IconPlayerPlay size={16} />}
            onClick={handleRun}
          >
            Run Test
          </Button>
          <Button
            variant="subtle"
            size="sm"
            onClick={handleViewDetails}
            leftSection={<IconInfoCircle size={14} />}
          >
            Details
          </Button>
        </Group>

        <Button
          fullWidth
          variant="outline"
          color="blue"
          size="sm"
          leftSection={<IconTransform size={14} />}
          onClick={handleConvertToTestPlan}
          loading={converting}
        >
          Convert to Test Plan
        </Button>
      </Stack>

      {/* Test Execution Modal */}
      <TestExecutionModal
        opened={executionModalOpened}
        onClose={() => setExecutionModalOpened(false)}
        scenario={scenario}
      />

      {/* Scenario Detail Modal */}
      <ScenarioDetailModal
        opened={detailModalOpened}
        onClose={() => setDetailModalOpened(false)}
        scenario={scenario}
      />
    </Card>
  )
}
