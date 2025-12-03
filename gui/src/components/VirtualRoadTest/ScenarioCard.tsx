/**
 * Scenario Card Component
 *
 * Display scenario summary in card format
 */

import { useState } from 'react'
import { Card, Text, Badge, Group, Button, Stack } from '@mantine/core'
import {
  IconMapPin,
  IconClock,
  IconRuler,
  IconPlayerPlay,
  IconInfoCircle,
} from '@tabler/icons-react'
import type { ScenarioSummary } from '../../types/roadTest'
import { TestExecutionModal } from './TestExecutionModal'
import { ScenarioDetailModal } from './ScenarioDetailModal'

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

export default function ScenarioCard({ scenario, onRefresh }: Props) {
  const [executionModalOpened, setExecutionModalOpened] = useState(false)
  const [detailModalOpened, setDetailModalOpened] = useState(false)

  const handleRun = () => {
    setExecutionModalOpened(true)
  }

  const handleViewDetails = () => {
    setDetailModalOpened(true)
  }

  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder>
      {/* Header */}
      <Group justify="space-between" mb="xs">
        <Badge color={CATEGORY_COLORS[scenario.category]} variant="light" size="sm">
          {CATEGORY_LABELS[scenario.category]}
        </Badge>
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
      <Group gap="xs">
        <Button
          fullWidth
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
