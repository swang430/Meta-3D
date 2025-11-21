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
            <QueueTabPlaceholder />
          </Tabs.Panel>

          {/* History Tab */}
          <Tabs.Panel value="history" pt="md">
            <HistoryTabPlaceholder />
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </Container>
  )
}

/**
 * Temporary placeholder components
 * These will be replaced with actual implementations in subsequent phases
 */

interface PlansTabPlaceholderProps {
  onSelectPlan: (planId: string) => void
}

function PlansTabPlaceholder({ onSelectPlan }: PlansTabPlaceholderProps) {
  return (
    <Stack gap="md" align="center" py="xl">
      <IconList size={48} stroke={1.5} color="gray" />
      <div style={{ textAlign: 'center' }}>
        <Title order={3}>计划管理</Title>
        <Text c="dimmed" size="sm">
          测试计划的创建、编辑、复制和删除功能
        </Text>
        <Text c="dimmed" size="sm" mt="xs">
          Phase 2 将实现完整的 PlansTab 组件
        </Text>
      </div>
    </Stack>
  )
}

interface StepsTabPlaceholderProps {
  selectedPlanId: string | null
}

function StepsTabPlaceholder({ selectedPlanId }: StepsTabPlaceholderProps) {
  return (
    <Stack gap="md" align="center" py="xl">
      <IconFileCode size={48} stroke={1.5} color="gray" />
      <div style={{ textAlign: 'center' }}>
        <Title order={3}>步骤编排</Title>
        <Text c="dimmed" size="sm">
          从序列库添加步骤，配置参数，拖拽排序
        </Text>
        {selectedPlanId && (
          <Text c="blue" size="sm" mt="xs">
            当前选中计划: {selectedPlanId}
          </Text>
        )}
        <Text c="dimmed" size="sm" mt="xs">
          Phase 3 将从 TestConfig 提取步骤编辑器
        </Text>
      </div>
    </Stack>
  )
}

function QueueTabPlaceholder() {
  return (
    <Stack gap="md" align="center" py="xl">
      <IconClock size={48} stroke={1.5} color="gray" />
      <div style={{ textAlign: 'center' }}>
        <Title order={3}>执行队列</Title>
        <Text c="dimmed" size="sm">
          查看和管理测试计划执行队列
        </Text>
        <Text c="dimmed" size="sm" mt="xs">
          Phase 4 将实现队列管理功能
        </Text>
      </div>
    </Stack>
  )
}

function HistoryTabPlaceholder() {
  return (
    <Stack gap="md" align="center" py="xl">
      <IconChartBar size={48} stroke={1.5} color="gray" />
      <div style={{ textAlign: 'center' }}>
        <Title order={3}>执行历史</Title>
        <Text c="dimmed" size="sm">
          查看历史执行记录和统计分析
        </Text>
        <Text c="dimmed" size="sm" mt="xs">
          Phase 4 将实现历史记录功能
        </Text>
      </div>
    </Stack>
  )
}

export default TestManagement
