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
import { Container, Tabs, Title, Stack, Text, Button, Group } from '@mantine/core'
import {
  IconChecklist,
  IconList,
  IconFileCode,
  IconClock,
  IconChartBar,
  IconPlus,
  IconRoute,
} from '@tabler/icons-react'
import { TestCaseLibrary } from '../../components/TestPlanManagement/TestCaseLibrary'
import { CreateTestPlanWizard } from '../../components/TestPlanManagement/CreateTestPlanWizard'
import { PlansTab } from './components/PlansTab'
import { StepsTab } from './components/StepsTab'
import { QueueTab } from './components/QueueTab'
import { HistoryTab } from './components/HistoryTab'
import { VirtualRoadTest } from '../../components/VirtualRoadTest'

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
  
  // Test Case Selection State
  const [selectedTestCaseIds, setSelectedTestCaseIds] = useState<string[]>([])
  const [wizardOpened, setWizardOpened] = useState(false)

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        {/* Header */}
        <Group justify="space-between" align="flex-end">
          <div>
            <Title order={2}>测试管理</Title>
            <Text size="sm" c="dimmed">
              以测试用例为基础的统一测试管理与编排系统
            </Text>
          </div>
          
          {activeTab === 'caseLibrary' && selectedTestCaseIds.length > 0 && (
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={() => setWizardOpened(true)}
            >
              新建测试计划 ({selectedTestCaseIds.length})
            </Button>
          )}
        </Group>

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
            <Tabs.Tab value="virtualRoadTest" leftSection={<IconRoute size={16} />}>
              虚拟路测
            </Tabs.Tab>
          </Tabs.List>

          {/* Test Case Library Tab — Foundation */}
          <Tabs.Panel value="caseLibrary" pt="md">
            <TestCaseLibrary
              selectionMode={true}
              selectedIds={selectedTestCaseIds}
              onSelectionChange={setSelectedTestCaseIds}
              enableExecute={true}
            />
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

          {/* Virtual Road Test Tab — VRT consolidated as TestCase derivative (test_type='VirtualRoadTest') */}
          <Tabs.Panel value="virtualRoadTest" pt="md">
            <VirtualRoadTest />
          </Tabs.Panel>
        </Tabs>

        {/* Create Test Plan from Selected Cases */}
        <CreateTestPlanWizard
          opened={wizardOpened}
          onClose={() => setWizardOpened(false)}
          preSelectedCaseIds={selectedTestCaseIds}
          onCreated={() => {
            setWizardOpened(false)
            setSelectedTestCaseIds([])
            setActiveTab('plans') // Switch to plans tab to see the newly created plan
          }}
        />
      </Stack>
    </Container>
  )
}

export default TestManagement
