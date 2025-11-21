/**
 * Unified Test Management Main Component
 *
 * This is the main container for the unified test management system,
 * integrating both TestConfig and TestPlanManagement functionalities.
 *
 * @version 2.0.0
 * @date 2025-11-18
 */

import { useState } from 'react'
import { Container, Tabs, Title, Stack, Text } from '@mantine/core'
import {
  IconList,
  IconFileCode,
  IconClock,
  IconChartBar,
} from '@tabler/icons-react'
import { PlansTab } from './components/PlansTab'
import { StepsTab } from './components/StepsTab'
import { QueueTab } from './components/QueueTab'
import { HistoryTab } from './components/HistoryTab'

/**
 * Main Test Management Container Component
 *
 * Features 4 tabs:
 * - Plans: Test plan lifecycle management (create, edit, list, delete)
 * - Steps: Step-level orchestration and parameter configuration
 * - Queue: Test execution queue and scheduling
 * - History: Execution history and analytics
 */
export function TestManagement() {
  const [activeTab, setActiveTab] = useState<string | null>('plans')
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null)

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        {/* Header */}
        <div>
          <Title order={2}>测试管理</Title>
          <Text size="sm" c="dimmed">
            统一的测试计划管理与步骤编排系统
          </Text>
        </div>

        {/* Main Tabs */}
        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab value="plans" leftSection={<IconList size={16} />}>
              计划管理
            </Tabs.Tab>
            <Tabs.Tab value="steps" leftSection={<IconFileCode size={16} />}>
              步骤编排
            </Tabs.Tab>
            <Tabs.Tab value="queue" leftSection={<IconClock size={16} />}>
              执行队列
            </Tabs.Tab>
            <Tabs.Tab value="history" leftSection={<IconChartBar size={16} />}>
              执行历史
            </Tabs.Tab>
          </Tabs.List>

          {/* Plans Tab */}
          <Tabs.Panel value="plans" pt="md">
            <PlansTab onSelectPlan={setSelectedPlanId} />
          </Tabs.Panel>

          {/* Steps Tab */}
          <Tabs.Panel value="steps" pt="md">
            <StepsTab selectedPlanId={selectedPlanId} />
          </Tabs.Panel>

          {/* Queue Tab */}
          <Tabs.Panel value="queue" pt="md">
            <QueueTab />
          </Tabs.Panel>

          {/* History Tab */}
          <Tabs.Panel value="history" pt="md">
            <HistoryTab />
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </Container>
  )
}

export default TestManagement
