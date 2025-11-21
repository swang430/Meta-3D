/**
 * Steps List Component
 *
 * Displays a list of test steps with drag-and-drop reordering.
 */

import { Stack, Paper, Text, ActionIcon, Group, Badge, Menu, Loader, Center } from '@mantine/core'
import {
  IconGripVertical,
  IconDots,
  IconCopy,
  IconTrash,
  IconFileCode,
} from '@tabler/icons-react'
import { useDeleteTestStep, useDuplicateTestStep } from '../../hooks'
import type { TestStep } from '../../types'

interface StepsListProps {
  planId: string
  steps: TestStep[]
  selectedStepId: string | null
  onSelectStep: (stepId: string) => void
  isLoading: boolean
  readOnly: boolean
}

// Helper to get step status color
function getStepStatusColor(status?: string): string {
  const colorMap: Record<string, string> = {
    pending: 'gray',
    running: 'blue',
    completed: 'green',
    failed: 'red',
    skipped: 'yellow',
  }
  return colorMap[status || 'pending'] || 'gray'
}

// Helper to get step status label
function getStepStatusLabel(status?: string): string {
  const labelMap: Record<string, string> = {
    pending: '待执行',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    skipped: '已跳过',
  }
  return labelMap[status || 'pending'] || '待执行'
}

export function StepsList({
  planId,
  steps,
  selectedStepId,
  onSelectStep,
  isLoading,
  readOnly,
}: StepsListProps) {
  const { mutate: deleteStep } = useDeleteTestStep()
  const { mutate: duplicateStep } = useDuplicateTestStep()

  const handleDelete = (stepId: string) => {
    if (confirm('确定要删除此步骤吗？')) {
      deleteStep({ planId, stepId })
    }
  }

  const handleDuplicate = (stepId: string) => {
    duplicateStep({ planId, stepId })
  }

  if (isLoading) {
    return (
      <Paper p="md" withBorder>
        <Center>
          <Loader size="sm" />
        </Center>
      </Paper>
    )
  }

  if (steps.length === 0) {
    return (
      <Paper p="xl" withBorder>
        <Stack align="center" gap="xs">
          <IconFileCode size={32} stroke={1.5} color="gray" />
          <Text size="sm" c="dimmed" ta="center">
            暂无测试步骤
          </Text>
          <Text size="xs" c="dimmed" ta="center">
            点击"添加步骤"从序列库中添加
          </Text>
        </Stack>
      </Paper>
    )
  }

  return (
    <Stack gap="xs">
      {steps.map((step, index) => {
        const isSelected = step.id === selectedStepId
        const hasStatus = step.status && step.status !== 'pending'

        return (
          <Paper
            key={step.id}
            p="sm"
            withBorder
            style={{
              cursor: 'pointer',
              backgroundColor: isSelected ? 'var(--mantine-color-blue-0)' : undefined,
              borderColor: isSelected ? 'var(--mantine-color-blue-5)' : undefined,
            }}
            onClick={() => onSelectStep(step.id)}
          >
            <Group gap="xs" wrap="nowrap">
              {/* Drag Handle (disabled in read-only mode) */}
              {!readOnly && (
                <ActionIcon size="sm" variant="subtle" style={{ cursor: 'grab' }}>
                  <IconGripVertical size={14} />
                </ActionIcon>
              )}

              {/* Order Number */}
              <Badge size="sm" variant="light" color="gray">
                {index + 1}
              </Badge>

              {/* Step Info */}
              <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
                <Text size="sm" fw={500} truncate>
                  {step.title}
                </Text>
                {step.description && (
                  <Text size="xs" c="dimmed" truncate>
                    {step.description}
                  </Text>
                )}
                {hasStatus && (
                  <Badge size="xs" color={getStepStatusColor(step.status)} variant="dot">
                    {getStepStatusLabel(step.status)}
                  </Badge>
                )}
              </Stack>

              {/* Actions Menu */}
              {!readOnly && (
                <Menu position="bottom-end" onClick={(e) => e.stopPropagation()}>
                  <Menu.Target>
                    <ActionIcon size="sm" variant="subtle">
                      <IconDots size={14} />
                    </ActionIcon>
                  </Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item
                      leftSection={<IconCopy size={14} />}
                      onClick={() => handleDuplicate(step.id)}
                    >
                      复制
                    </Menu.Item>
                    <Menu.Divider />
                    <Menu.Item
                      leftSection={<IconTrash size={14} />}
                      color="red"
                      onClick={() => handleDelete(step.id)}
                    >
                      删除
                    </Menu.Item>
                  </Menu.Dropdown>
                </Menu>
              )}
            </Group>
          </Paper>
        )
      })}
    </Stack>
  )
}

export default StepsList
