/**
 * Scenario Library Component
 *
 * Browse and manage road test scenarios
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Group,
  TextInput,
  Select,
  Button,
  SimpleGrid,
  Text,
  Loader,
  Alert,
  Tabs,
} from '@mantine/core'
import { IconSearch, IconPlus, IconAlertCircle } from '@tabler/icons-react'
import { fetchScenarios } from '../../api/roadTestService'
import type { ScenarioCategory } from '../../types/roadTest'
import ScenarioCard from './ScenarioCard'
import { CreateScenarioDialog } from './CreateScenarioDialog'

const CATEGORIES: { value: ScenarioCategory; label: string }[] = [
  { value: 'standard', label: '⭐ Standard (3GPP/CTIA)' },
  { value: 'functional', label: '🔧 Functional' },
  { value: 'performance', label: '🚀 Performance' },
  { value: 'environment', label: '🌍 Environment' },
  { value: 'extreme', label: '⚠️ Extreme' },
  { value: 'custom', label: '✏️ Custom' },
]

export default function ScenarioLibrary() {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<ScenarioCategory | null>(null)
  const [selectedSource, setSelectedSource] = useState<'standard' | 'custom' | null>(null)
  const [createDialogOpened, setCreateDialogOpened] = useState(false)

  // Fetch scenarios
  const {
    data: scenarios,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['scenarios', selectedCategory, selectedSource],
    queryFn: () =>
      fetchScenarios({
        category: selectedCategory || undefined,
        source: selectedSource || undefined,
      }),
  })

  // Filter scenarios by search query
  const filteredScenarios = scenarios?.filter((s) => {
    const query = searchQuery.toLowerCase()
    return (
      s.name.toLowerCase().includes(query) ||
      s.description?.toLowerCase().includes(query) ||
      s.tags.some((tag) => tag.toLowerCase().includes(query))
    )
  })

  return (
    <div>
      {/* Filters */}
      <Group mb="md">
        <TextInput
          placeholder="Search scenarios by name, description, or tags..."
          leftSection={<IconSearch size={16} />}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.currentTarget.value)}
          style={{ flex: 1 }}
        />

        <Select
          placeholder="Category"
          value={selectedCategory}
          onChange={(value) => setSelectedCategory(value as ScenarioCategory | null)}
          data={[{ value: '', label: 'All Categories' }, ...CATEGORIES]}
          clearable
          style={{ width: 200 }}
        />

        <Select
          placeholder="Source"
          value={selectedSource}
          onChange={(value) => setSelectedSource(value as 'standard' | 'custom' | null)}
          data={[
            { value: '', label: 'All Sources' },
            { value: 'standard', label: 'Standard' },
            { value: 'custom', label: 'Custom' },
          ]}
          clearable
          style={{ width: 150 }}
        />

        <Button
          leftSection={<IconPlus size={16} />}
          variant="light"
          onClick={() => setCreateDialogOpened(true)}
        >
          Create Scenario
        </Button>
      </Group>

      {/* Scenario Grid */}
      {isLoading && (
        <Group justify="center" py="xl">
          <Loader size="md" />
          <Text c="dimmed">Loading scenarios...</Text>
        </Group>
      )}

      {error && (
        <Alert icon={<IconAlertCircle size={16} />} title="Error" color="red" mb="md">
          Failed to load scenarios: {(error as Error).message}
        </Alert>
      )}

      {filteredScenarios && filteredScenarios.length === 0 && (
        <Text c="dimmed" ta="center" py="xl">
          No scenarios found. Try adjusting your filters or create a new scenario.
        </Text>
      )}

      {filteredScenarios && filteredScenarios.length > 0 && (
        <>
          <Text size="sm" c="dimmed" mb="md">
            Found {filteredScenarios.length} scenario{filteredScenarios.length !== 1 ? 's' : ''}
          </Text>

          <SimpleGrid
            cols={{ base: 1, sm: 2, lg: 3 }}
            spacing="md"
            verticalSpacing="md"
          >
            {filteredScenarios.map((scenario) => (
              <ScenarioCard key={scenario.id} scenario={scenario} onRefresh={refetch} />
            ))}
          </SimpleGrid>
        </>
      )}

      {/* Create Scenario Dialog */}
      <CreateScenarioDialog
        opened={createDialogOpened}
        onClose={() => {
          setCreateDialogOpened(false)
          refetch()
        }}
      />
    </div>
  )
}
