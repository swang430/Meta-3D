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
  IconTrash,
  IconChevronUp,
  IconChevronDown,
  IconClock,
} from '@tabler/icons-react'
import {
  useTestQueue,
  useRemoveFromQueue,
  useStartExecution,
} from '../../hooks'

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

  const handleStart = (queueItemId: string, planId: string) => {
    startExecution({
      planId,
      payload: { started_by: '当前用户' },
    })
  }

  const handleRemove = (queueItemId: string) => {
    if (confirm('确定要从队列中移除此测试计划吗？')) {
      removeFromQueue(queueItemId)
    }
  }

  // TODO: Implement move up/down with reorderQueue hook
  // const handleMoveUp = (queueItemId: string) => { }
  // const handleMoveDown = (queueItemId: string) => { }

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
                                  handleStart(queueItem.id, plan.id)
                                }
                              >
                                <IconPlayerPlay size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}

                          {/* Move up/down buttons */}
                          {/* TODO: Implement after adding reorderQueue hook
                          {index > 0 && plan.status === 'queued' && (
                            <Tooltip label="上移">
                              <ActionIcon
                                variant="subtle"
                                onClick={() => handleMoveUp(queueItem.id)}
                              >
                                <IconChevronUp size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
                          {index < queueItems.length - 1 && plan.status === 'queued' && (
                            <Tooltip label="下移">
                              <ActionIcon
                                variant="subtle"
                                onClick={() => handleMoveDown(queueItem.id)}
                              >
                                <IconChevronDown size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
                          */}

                          {/* Remove button (only for queued status) */}
                          {plan.status === 'queued' && (
                            <Tooltip label="从队列中移除">
                              <ActionIcon
                                variant="light"
                                color="red"
                                onClick={() => handleRemove(queueItem.id)}
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
