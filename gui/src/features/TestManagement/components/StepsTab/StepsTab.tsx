/**
 * Steps Tab - Test Step Orchestration
 *
 * Main container for test step management:
 * - View and edit test steps for a selected plan
 * - Add steps from sequence library
 * - Configure step parameters
 * - Reorder steps (drag & drop)
 * - Duplicate and delete steps
 *
 * @version 2.0.0
 */

import { useState, useEffect } from 'react'
import { Stack, Text, Alert, Group, Button } from '@mantine/core'
import { IconAlertCircle, IconPlus } from '@tabler/icons-react'
import { useTestPlan, useTestSteps } from '../../hooks'
import { StepsList } from './StepsList'
import { StepEditor } from './StepEditor'
import { AddStepModal } from './AddStepModal'

interface StepsTabProps {
  selectedPlanId: string | null
}

export function StepsTab({ selectedPlanId }: StepsTabProps) {
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [addStepModalOpened, setAddStepModalOpened] = useState(false)

  // Query hooks
  const { data: testPlan, isLoading: isPlanLoading } = useTestPlan(
    selectedPlanId || undefined,
  )
  const { data: steps, isLoading: isStepsLoading } = useTestSteps(
    selectedPlanId || undefined,
  )

  // Reset selected step when plan changes
  useEffect(() => {
    setSelectedStepId(null)
  }, [selectedPlanId])

  // No plan selected
  if (!selectedPlanId) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} title="未选择测试计划" color="blue">
        <Text size="sm">
          请先在"计划管理"标签页中选择一个测试计划，然后返回此处编排测试步骤。
        </Text>
      </Alert>
    )
  }

  // Plan is in execution - read-only mode
  const isReadOnly =
    testPlan?.status &&
    ['queued', 'running', 'paused'].includes(testPlan.status)

  return (
    <Stack gap="md">
      {/* Header Info */}
      {testPlan && (
        <Alert title={testPlan.name} color="gray">
          <Text size="sm" c="dimmed">
            {testPlan.description || '无描述'}
          </Text>
          <Group gap="xs" mt="xs">
            <Text size="xs" c="dimmed">
              状态: {testPlan.status}
            </Text>
            <Text size="xs" c="dimmed">
              •
            </Text>
            <Text size="xs" c="dimmed">
              步骤数: {steps?.length || 0}
            </Text>
          </Group>
        </Alert>
      )}

      {isReadOnly && (
        <Alert icon={<IconAlertCircle size={16} />} title="只读模式" color="orange">
          <Text size="sm">
            该测试计划正在执行队列中或正在执行，无法编辑步骤。
          </Text>
        </Alert>
      )}

      {/* Main Content */}
      <Group align="flex-start" gap="md" style={{ flexWrap: 'nowrap' }}>
        {/* Left: Steps List */}
        <Stack style={{ flex: '0 0 400px' }} gap="md">
          <Group justify="space-between">
            <Text size="lg" fw={600}>
              测试步骤
            </Text>
            {!isReadOnly && (
              <Button
                size="xs"
                leftSection={<IconPlus size={14} />}
                onClick={() => setAddStepModalOpened(true)}
              >
                添加步骤
              </Button>
            )}
          </Group>

          <StepsList
            planId={selectedPlanId}
            steps={steps || []}
            selectedStepId={selectedStepId}
            onSelectStep={setSelectedStepId}
            isLoading={isStepsLoading}
            readOnly={isReadOnly}
          />
        </Stack>

        {/* Right: Step Editor */}
        <Stack style={{ flex: 1 }} gap="md">
          {selectedStepId ? (
            <StepEditor
              planId={selectedPlanId}
              stepId={selectedStepId}
              readOnly={isReadOnly}
            />
          ) : (
            <Alert title="未选择步骤" color="gray">
              <Text size="sm">请从左侧列表中选择一个步骤进行编辑</Text>
            </Alert>
          )}
        </Stack>
      </Group>

      {/* Add Step Modal */}
      <AddStepModal
        opened={addStepModalOpened}
        onClose={() => setAddStepModalOpened(false)}
        planId={selectedPlanId}
      />
    </Stack>
  )
}

export default StepsTab
