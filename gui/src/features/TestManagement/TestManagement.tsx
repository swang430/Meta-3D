/**
 * Unified Test Management Main Component
 *
 * Refactored: TestCase Library is now the first tab (foundation).
 * TestPlan organizes TestCases, not the other way around.
 *
 * @version 3.0.0
 * @date 2026-05-04
 */

import { useState } from 'react'
import { Container, Tabs, Title, Stack, Text } from '@mantine/core'
import {
  IconChecklist,
  IconList,
  IconFileCode,
  IconClock,
  IconChartBar,
} from '@tabler/icons-react'
import { TestCaseLibrary } from '../../components/TestPlanManagement/TestCaseLibrary'
import { PlansTab } from './components/PlansTab'
import { StepsTab } from './components/StepsTab'
import { QueueTab } from './components/QueueTab'
import { HistoryTab } from './components/HistoryTab'

/**
 * Main Test Management Container Component
 *
 * Features 5 tabs:
 * - CaseLibrary: Standard test case templates (foundation) ★ NEW
 * - Plans: Test plan lifecycle management (create, edit, list, delete)
 * - Steps: Step-level orchestration and parameter configuration
 * - Queue: Test execution queue and scheduling
 * - History: Execution history and analytics
 */
export function TestManagement() {
  const [activeTab, setActiveTab] = useState<string | null>('caseLibrary')
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null)

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        {/* Header */}
        <div>
          <Title order={2}>测试管理</Title>
          <Text size="sm" c="dimmed">
            以测试用例为基础的统一测试管理与编排系统
          </Text>
        </div>

        {/* Main Tabs */}
        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab value="caseLibrary" leftSection={<IconChecklist size={16} />}>
              测试用例库
            </Tabs.Tab>
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

          {/* Test Case Library Tab — Foundation */}
          <Tabs.Panel value="caseLibrary" pt="md">
            <TestCaseLibrary />
          </Tabs.Panel>

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
