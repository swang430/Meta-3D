/**
 * Virtual Road Test Main Component
 *
 * Entry point for Virtual Road Test feature
 */

import { useState } from 'react'
import { Container, Tabs, Title, Text, Badge, Group } from '@mantine/core'
import ScenarioLibrary from './ScenarioLibrary'

export default function VirtualRoadTest() {
  const [activeTab, setActiveTab] = useState<string | null>('library')

  return (
    <Container size="xl" py="md">
      <Group justify="space-between" mb="xl">
        <div>
          <Title order={2}>🚗 Virtual Road Test</Title>
          <Text c="dimmed" size="sm" mt="xs">
            Replicate real-world road testing in laboratory environments
          </Text>
        </div>
        <Badge size="lg" variant="light" color="blue">
          Phase 2: OTA Mode
        </Badge>
      </Group>

      <Tabs value={activeTab} onChange={setActiveTab}>
        <Tabs.List>
          <Tabs.Tab value="library">
            📚 Scenario Library
          </Tabs.Tab>
          <Tabs.Tab value="executions">
            ▶️ Test Executions
          </Tabs.Tab>
          <Tabs.Tab value="capabilities">
            ⚙️ System Capabilities
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="library" pt="md">
          <ScenarioLibrary />
        </Tabs.Panel>

        <Tabs.Panel value="executions" pt="md">
          <Text c="dimmed" ta="center" py="xl">
            Test Executions view - Coming soon
          </Text>
        </Tabs.Panel>

        <Tabs.Panel value="capabilities" pt="md">
          <Text c="dimmed" ta="center" py="xl">
            System Capabilities view - Coming soon
          </Text>
        </Tabs.Panel>
      </Tabs>
    </Container>
  )
}
