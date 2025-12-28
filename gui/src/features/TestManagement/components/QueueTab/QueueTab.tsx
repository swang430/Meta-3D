/**
 * Queue Tab - Test Execution Queue
 *
 * Displays and manages the test execution queue.
 * Features:
 * - View queued test plans
 * - Start execution
 * - Remove from queue
 * - Reorder queue items
 * - Auto-refresh every 5 seconds
 *
 * @version 2.0.0
 */

import {
  Stack,
  Paper,
  Title,
  Group,
  Button,
  Table,
  Badge,
  ActionIcon,
  Text,
  Tooltip,
  Progress,
  Loader,
  Center,
} from '@mantine/core'
import {
  IconRefresh,
  IconPlayerPlay,
  IconPlayerPause,
  IconTrash,
  IconCheck,
  IconX,
  IconClock,
  IconChevronUp,
  IconChevronDown,
} from '@tabler/icons-react'
import {
  useTestQueue,
  useRemoveFromQueue,
  useStartExecution,
  usePauseExecution,
  useCompleteExecution,
  useCancelExecution,
  useResumeExecution,
  useMoveQueueItem,
} from '../../hooks'
import { appEventBus } from '../../../../lib/eventBus'

// Helper functions for status display
function getStatusColor(status: string): string {
  const colorMap: Record<string, string> = {
    draft: 'gray',
    ready: 'blue',
    queued: 'cyan',
    running: 'green',
    paused: 'yellow',
    completed: 'teal',
    failed: 'red',
    cancelled: 'orange',
    waiting: 'gray',
    blocked: 'orange',
  }
  return colorMap[status] || 'gray'
}

function getStatusLabel(status: string): string {
  const labelMap: Record<string, string> = {
    draft: '草稿',
    ready: '就绪',
    queued: '已排队',
    running: '执行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    waiting: '等待中',
    blocked: '阻塞',
  }
  return labelMap[status] || status
}

export function QueueTab() {
  // Query hooks (auto-refreshes every 5 seconds)
  const { data: queueItems, isLoading, refetch } = useTestQueue()

  // Mutation hooks
  const { mutate: removeFromQueue } = useRemoveFromQueue()
  const { mutate: startExecution } = useStartExecution()
  const { mutate: pauseExecution } = usePauseExecution()
  const { mutate: completeExecution } = useCompleteExecution()
  const { mutate: cancelExecution } = useCancelExecution()
  const { mutate: resumeExecution } = useResumeExecution()
  const { mutate: moveQueueItem, isPending: isMoving } = useMoveQueueItem()

  const handleStart = (_queueItemId: string, planId: string, planName: string) => {
    startExecution(
      {
        planId,
        payload: { started_by: '当前用户' },
      },
      {
        onSuccess: () => {
          // Emit event to App.tsx to switch to monitoring and start execution
          appEventBus.emit({
            type: 'execution:start',
            payload: { planId, planName },
          })
        },
      },
    )
  }

  const handleRemove = (testPlanId: string) => {
    if (confirm('确定要从队列中移除此测试计划吗？')) {
      // Note: Backend expects test_plan_id, not queue_item_id
      removeFromQueue(testPlanId)
    }
  }

  const handleComplete = (planId: string) => {
    if (confirm('确定要完成此测试计划吗？')) {
      completeExecution(planId)
      // Emit event to sync with Monitoring
      appEventBus.emit({ type: 'execution:complete', payload: { planId } })
    }
  }

  const handlePause = (planId: string) => {
    pauseExecution(
      { planId, payload: { paused_by: '当前用户' } },
      {
        onSuccess: () => {
          // Emit event to pause execution in Monitoring
          appEventBus.emit({ type: 'execution:pause', payload: { planId } })
        },
      },
    )
  }

  const handleResume = (planId: string, planName: string) => {
    resumeExecution(
      { planId, payload: { resumed_by: '当前用户' } },
      {
        onSuccess: () => {
          // Emit event to resume execution in Monitoring
          appEventBus.emit({ type: 'execution:start', payload: { planId, planName } })
        },
      },
    )
  }

  const handleCancel = (planId: string) => {
    if (confirm('确定要取消此测试计划的执行吗？')) {
      cancelExecution(
        { planId, payload: { cancelled_by: '当前用户' } },
        {
          onSuccess: () => {
            // Emit event to stop execution in Monitoring
            appEventBus.emit({ type: 'execution:stop', payload: { planId } })
          },
        },
      )
    }
  }

  // Move up/down handlers
  const handleMoveUp = (planId: string) => {
    moveQueueItem({ planId, direction: 'up' })
  }
  const handleMoveDown = (planId: string) => {
    moveQueueItem({ planId, direction: 'down' })
  }

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between">
        <Title order={2}>执行队列</Title>
        <Button
          leftSection={<IconRefresh size={16} />}
          variant="light"
          onClick={() => refetch()}
          loading={isLoading}
        >
          刷新
        </Button>
      </Group>

      {/* Queue Info */}
      <Paper p="md" withBorder>
        <Group gap="xl">
          <div>
            <Text size="xs" c="dimmed">
              队列中的计划
            </Text>
            <Text size="lg" fw={600}>
              {queueItems?.length || 0}
            </Text>
          </div>
          <div>
            <Text size="xs" c="dimmed">
              执行中
            </Text>
            <Text size="lg" fw={600} c="green">
              {queueItems?.filter((item) => item.test_plan.status === 'running')
                .length || 0}
            </Text>
          </div>
          <div>
            <Text size="xs" c="dimmed">
              等待中
            </Text>
            <Text size="lg" fw={600} c="cyan">
              {queueItems?.filter((item) => item.test_plan.status === 'queued')
                .length || 0}
            </Text>
          </div>
        </Group>
      </Paper>

      {/* Queue Table */}
      <Paper withBorder>
        {isLoading ? (
          <Center p="xl">
            <Loader size="md" />
          </Center>
        ) : (
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th style={{ width: 60 }}>位置</Table.Th>
                <Table.Th>测试计划</Table.Th>
                <Table.Th>状态</Table.Th>
                <Table.Th>进度</Table.Th>
                <Table.Th>优先级</Table.Th>
                <Table.Th>入队时间</Table.Th>
                <Table.Th>操作</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {!queueItems || queueItems.length === 0 ? (
                <Table.Tr>
                  <Table.Td colSpan={7}>
                    <Stack align="center" gap="xs" py="xl">
                      <IconClock size={48} stroke={1.5} color="gray" />
                      <Text c="dimmed" ta="center">
                        执行队列为空
                      </Text>
                      <Text size="xs" c="dimmed" ta="center">
                        在"计划管理"中将就绪的测试计划添加到队列
                      </Text>
                    </Stack>
                  </Table.Td>
                </Table.Tr>
              ) : (
                queueItems.map((item, index) => {
                  const plan = item.test_plan
                  const queueItem = item.queue_item
                  const progress =
                    plan.total_test_cases > 0
                      ? Math.round(
                          (plan.completed_test_cases / plan.total_test_cases) * 100,
                        )
                      : 0

                  return (
                    <Table.Tr key={queueItem.id}>
                      {/* Position */}
                      <Table.Td>
                        <Group gap={4}>
                          <Badge size="lg" variant="filled" color="blue">
                            {queueItem.position}
                          </Badge>
                        </Group>
                      </Table.Td>

                      {/* Plan Name */}
                      <Table.Td>
                        <Stack gap={2}>
                          <Text size="sm" fw={500}>
                            {plan.name}
                          </Text>
                          <Text size="xs" c="dimmed">
                            ID: {plan.id.substring(0, 8)}
                          </Text>
                        </Stack>
                      </Table.Td>

                      {/* Status */}
                      <Table.Td>
                        <Badge color={getStatusColor(plan.status)} variant="light">
                          {getStatusLabel(plan.status)}
                        </Badge>
                      </Table.Td>

                      {/* Progress */}
                      <Table.Td>
                        <Group gap="xs">
                          <Progress
                            value={progress}
                            size="sm"
                            style={{ flex: 1, minWidth: 100 }}
                            color={plan.failed_test_cases > 0 ? 'red' : 'blue'}
                          />
                          <Text size="xs" c="dimmed">
                            {plan.completed_test_cases}/{plan.total_test_cases}
                          </Text>
                        </Group>
                      </Table.Td>

                      {/* Priority */}
                      <Table.Td>
                        <Badge size="sm" color="gray" variant="outline">
                          P{queueItem.priority}
                        </Badge>
                      </Table.Td>

                      {/* Queued Time */}
                      <Table.Td>
                        <Tooltip
                          label={new Date(queueItem.queued_at).toLocaleString()}
                        >
                          <Text size="sm" c="dimmed">
                            {new Date(queueItem.queued_at).toLocaleDateString()}
                          </Text>
                        </Tooltip>
                      </Table.Td>

                      {/* Actions */}
                      <Table.Td>
                        <Group gap="xs">
                          {/* Start button (only for queued status) */}
                          {plan.status === 'queued' && index === 0 && (
                            <Tooltip label="开始执行">
                              <ActionIcon
                                variant="light"
                                color="green"
                                onClick={() =>
                                  handleStart(queueItem.id, plan.id, plan.name)
                                }
                              >
                                <IconPlayerPlay size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}

                          {/* Pause button (for running status) */}
                          {plan.status === 'running' && (
                            <Tooltip label="暂停执行">
                              <ActionIcon
                                variant="light"
                                color="yellow"
                                onClick={() => handlePause(plan.id)}
                              >
                                <IconPlayerPause size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}

                          {/* Resume button (for paused status) */}
                          {plan.status === 'paused' && (
                            <Tooltip label="恢复执行">
                              <ActionIcon
                                variant="light"
                                color="green"
                                onClick={() => handleResume(plan.id, plan.name)}
                              >
                                <IconPlayerPlay size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}

                          {/* Complete button (for running or paused status) */}
                          {(plan.status === 'running' || plan.status === 'paused') && (
                            <Tooltip label="完成执行">
                              <ActionIcon
                                variant="light"
                                color="teal"
                                onClick={() => handleComplete(plan.id)}
                              >
                                <IconCheck size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}

                          {/* Cancel button (for running or paused status) */}
                          {(plan.status === 'running' || plan.status === 'paused') && (
                            <Tooltip label="取消执行">
                              <ActionIcon
                                variant="light"
                                color="orange"
                                onClick={() => handleCancel(plan.id)}
                              >
                                <IconX size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}

                          {/* Move up/down buttons */}
                          {index > 0 && plan.status === 'queued' && (
                            <Tooltip label="上移">
                              <ActionIcon
                                variant="subtle"
                                onClick={() => handleMoveUp(plan.id)}
                                loading={isMoving}
                              >
                                <IconChevronUp size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
                          {queueItems && index < queueItems.length - 1 && plan.status === 'queued' && (
                            <Tooltip label="下移">
                              <ActionIcon
                                variant="subtle"
                                onClick={() => handleMoveDown(plan.id)}
                                loading={isMoving}
                              >
                                <IconChevronDown size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}

                          {/* Remove button (for queued, cancelled, completed, failed status) */}
                          {['queued', 'cancelled', 'completed', 'failed'].includes(plan.status) && (
                            <Tooltip label={plan.status === 'queued' ? '从队列中移除' : '删除'}>
                              <ActionIcon
                                variant="light"
                                color="red"
                                onClick={() => handleRemove(plan.id)}
                              >
                                <IconTrash size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  )
                })
              )}
            </Table.Tbody>
          </Table>
        )}
      </Paper>
    </Stack>
  )
}

export default QueueTab
