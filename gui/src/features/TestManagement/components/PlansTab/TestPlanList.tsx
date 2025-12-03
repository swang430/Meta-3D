/**
 * Test Plan List Component
 *
 * Displays a list of test plans with filtering, searching, and actions.
 * Uses TanStack Query hooks for data management.
 *
 * @version 2.0.0
 */

import { useState } from 'react'
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
  Select,
  TextInput,
  Progress,
  Tooltip,
  Menu,
  Modal,
  Loader,
  Center,
} from '@mantine/core'
import {
  IconPlus,
  IconRefresh,
  IconPlayerPlay,
  IconPlayerPause,
  IconPlayerStop,
  IconEdit,
  IconTrash,
  IconDots,
  IconClock,
  IconSearch,
  IconCopy,
  IconCheck,
} from '@tabler/icons-react'
import {
  useTestPlans,
  useDeleteTestPlan,
  useDuplicateTestPlan,
  useUpdateTestPlan,
  useQueueTestPlan,
  useStartExecution,
  usePauseExecution,
  useResumeExecution,
  useCancelExecution,
  useRemoveFromQueue,
} from '../../hooks'
import type { TestPlanStatus } from '../../types'

interface TestPlanListProps {
  onCreateNew: () => void
  onEdit: (planId: string) => void
  onSelect?: (planId: string) => void
}

// Helper functions for status display
function getStatusColor(status: TestPlanStatus): string {
  const colorMap: Record<TestPlanStatus, string> = {
    draft: 'gray',
    ready: 'blue',
    queued: 'cyan',
    running: 'green',
    paused: 'yellow',
    completed: 'teal',
    failed: 'red',
    cancelled: 'orange',
  }
  return colorMap[status] || 'gray'
}

function getStatusLabel(status: TestPlanStatus): string {
  const labelMap: Record<TestPlanStatus, string> = {
    draft: '草稿',
    ready: '就绪',
    queued: '已排队',
    running: '执行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return labelMap[status] || status
}

export function TestPlanList({ onCreateNew, onEdit, onSelect }: TestPlanListProps) {
  const [statusFilter, setStatusFilter] = useState<TestPlanStatus | undefined>(undefined)
  const [searchQuery, setSearchQuery] = useState('')
  const [deleteModalOpened, setDeleteModalOpened] = useState(false)
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null)

  // Query hooks
  const { data: plansData, isLoading, refetch } = useTestPlans({ status: statusFilter })

  // Mutation hooks
  const { mutate: deletePlan } = useDeleteTestPlan()
  const { mutate: duplicatePlan } = useDuplicateTestPlan()
  const { mutate: updatePlan } = useUpdateTestPlan()
  const { mutate: queuePlan } = useQueueTestPlan()
  const { mutate: startExecution } = useStartExecution()
  const { mutate: pauseExecution } = usePauseExecution()
  const { mutate: resumeExecution } = useResumeExecution()
  const { mutate: cancelExecution } = useCancelExecution()
  const { mutate: removeFromQueue } = useRemoveFromQueue()

  // Handlers
  const handleDelete = () => {
    if (!selectedPlanId) return
    deletePlan(selectedPlanId, {
      onSuccess: () => {
        setDeleteModalOpened(false)
        setSelectedPlanId(null)
      },
    })
  }

  const openDeleteModal = (planId: string) => {
    setSelectedPlanId(planId)
    setDeleteModalOpened(true)
  }

  const handleDuplicate = (planId: string) => {
    duplicatePlan(planId)
  }

  const handleQueue = (planId: string) => {
    queuePlan({
      test_plan_id: planId,
      priority: 5,
      queued_by: '当前用户', // TODO: Get from auth context
    })
  }

  const handleStart = (planId: string) => {
    startExecution({
      planId,
      payload: { started_by: '当前用户' },
    })
  }

  const handlePause = (planId: string) => {
    pauseExecution({
      planId,
      payload: { paused_by: '当前用户' },
    })
  }

  const handleCancel = (planId: string) => {
    cancelExecution({
      planId,
      payload: { cancelled_by: '当前用户', reason: '用户手动取消' },
    })
  }

  const handleMarkReady = (planId: string) => {
    updatePlan({
      planId,
      payload: { status: 'ready' },
    })
  }

  const handleResume = (planId: string) => {
    resumeExecution({
      planId,
      payload: { resumed_by: '当前用户' },
    })
  }

  const handleRemoveFromQueue = (planId: string) => {
    // Remove from queue and set status back to ready
    // Note: removeFromQueue expects queue item ID, but we'll pass plan ID
    // The API should handle finding the queue item by plan ID
    removeFromQueue(planId, {
      onSuccess: () => {
        // Update plan status to ready after removing from queue
        updatePlan({
          planId,
          payload: { status: 'ready' },
        })
      },
    })
  }

  const handleResetToDraft = (planId: string) => {
    updatePlan({
      planId,
      payload: { status: 'draft' },
    })
  }

  // Filter plans by search query
  const filteredPlans =
    plansData?.items.filter((plan) =>
      plan.name.toLowerCase().includes(searchQuery.toLowerCase()),
    ) || []

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between">
        <Title order={2}>测试计划管理</Title>
        <Group>
          <Button
            leftSection={<IconRefresh size={16} />}
            variant="light"
            onClick={() => refetch()}
            loading={isLoading}
          >
            刷新
          </Button>
          <Button leftSection={<IconPlus size={16} />} onClick={onCreateNew}>
            创建测试计划
          </Button>
        </Group>
      </Group>

      {/* Filters */}
      <Paper p="md" withBorder>
        <Group>
          <TextInput
            placeholder="搜索测试计划..."
            leftSection={<IconSearch size={16} />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ flex: 1 }}
          />
          <Select
            placeholder="状态筛选"
            clearable
            value={statusFilter}
            onChange={(value) => setStatusFilter(value as TestPlanStatus | undefined)}
            data={[
              { value: 'draft', label: '草稿' },
              { value: 'ready', label: '就绪' },
              { value: 'queued', label: '已排队' },
              { value: 'running', label: '执行中' },
              { value: 'paused', label: '已暂停' },
              { value: 'completed', label: '已完成' },
              { value: 'failed', label: '失败' },
              { value: 'cancelled', label: '已取消' },
            ]}
            style={{ width: 200 }}
          />
        </Group>
      </Paper>

      {/* Table */}
      <Paper withBorder>
        {isLoading ? (
          <Center p="xl">
            <Loader size="md" />
          </Center>
        ) : (
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>名称</Table.Th>
                <Table.Th>状态</Table.Th>
                <Table.Th>进度</Table.Th>
                <Table.Th>测试用例</Table.Th>
                <Table.Th>优先级</Table.Th>
                <Table.Th>创建者</Table.Th>
                <Table.Th>创建时间</Table.Th>
                <Table.Th>操作</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {filteredPlans.length === 0 ? (
                <Table.Tr>
                  <Table.Td colSpan={8}>
                    <Text ta="center" c="dimmed" py="xl">
                      暂无测试计划
                    </Text>
                  </Table.Td>
                </Table.Tr>
              ) : (
                filteredPlans.map((plan) => {
                  const progress =
                    plan.total_test_cases > 0
                      ? Math.round(
                          (plan.completed_test_cases / plan.total_test_cases) * 100,
                        )
                      : 0

                  return (
                    <Table.Tr
                      key={plan.id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => onSelect?.(plan.id)}
                    >
                      <Table.Td>
                        <Text fw={500}>{plan.name}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge color={getStatusColor(plan.status)} variant="light">
                          {getStatusLabel(plan.status)}
                        </Badge>
                      </Table.Td>
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
                      <Table.Td>
                        <Text size="sm">{plan.total_test_cases}</Text>
                        {plan.failed_test_cases > 0 && (
                          <Text size="xs" c="red">
                            {plan.failed_test_cases} 失败
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        <Badge size="sm" color="gray" variant="outline">
                          P{plan.priority}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{plan.created_by}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Tooltip label={new Date(plan.created_at).toLocaleString()}>
                          <Text size="sm" c="dimmed">
                            {new Date(plan.created_at).toLocaleDateString()}
                          </Text>
                        </Tooltip>
                      </Table.Td>
                      <Table.Td onClick={(e) => e.stopPropagation()}>
                        <Group gap="xs">
                          {/* Status-based action buttons */}
                          {plan.status === 'draft' && (
                            <Tooltip label="标记为就绪">
                              <ActionIcon
                                variant="light"
                                color="green"
                                onClick={() => handleMarkReady(plan.id)}
                              >
                                <IconCheck size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
                          {plan.status === 'ready' && (
                            <Tooltip label="添加到队列">
                              <ActionIcon
                                variant="light"
                                color="blue"
                                onClick={() => handleQueue(plan.id)}
                              >
                                <IconClock size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
                          {plan.status === 'queued' && (
                            <Tooltip label="开始执行">
                              <ActionIcon
                                variant="light"
                                color="green"
                                onClick={() => handleStart(plan.id)}
                              >
                                <IconPlayerPlay size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
                          {plan.status === 'running' && (
                            <Tooltip label="暂停">
                              <ActionIcon
                                variant="light"
                                color="orange"
                                onClick={() => handlePause(plan.id)}
                              >
                                <IconPlayerPause size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
                          {plan.status === 'paused' && (
                            <Tooltip label="恢复执行">
                              <ActionIcon
                                variant="light"
                                color="green"
                                onClick={() => handleResume(plan.id)}
                              >
                                <IconPlayerPlay size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}
                          {plan.status === 'queued' && (
                            <Tooltip label="移出队列">
                              <ActionIcon
                                variant="light"
                                color="gray"
                                onClick={() => handleRemoveFromQueue(plan.id)}
                              >
                                <IconPlayerStop size={16} />
                              </ActionIcon>
                            </Tooltip>
                          )}

                          {/* More actions menu */}
                          <Menu position="bottom-end">
                            <Menu.Target>
                              <ActionIcon variant="subtle">
                                <IconDots size={16} />
                              </ActionIcon>
                            </Menu.Target>
                            <Menu.Dropdown>
                              <Menu.Item
                                leftSection={<IconEdit size={14} />}
                                onClick={() => onEdit(plan.id)}
                              >
                                编辑
                              </Menu.Item>
                              <Menu.Item
                                leftSection={<IconCopy size={14} />}
                                onClick={() => handleDuplicate(plan.id)}
                              >
                                复制
                              </Menu.Item>
                              {['running', 'paused', 'queued'].includes(plan.status) && (
                                <Menu.Item
                                  leftSection={<IconPlayerStop size={14} />}
                                  color="orange"
                                  onClick={() => handleCancel(plan.id)}
                                >
                                  取消执行
                                </Menu.Item>
                              )}
                              {['cancelled', 'failed', 'completed'].includes(plan.status) && (
                                <Menu.Item
                                  leftSection={<IconRefresh size={14} />}
                                  color="blue"
                                  onClick={() => handleResetToDraft(plan.id)}
                                >
                                  重置为草稿
                                </Menu.Item>
                              )}
                              <Menu.Divider />
                              <Menu.Item
                                leftSection={<IconTrash size={14} />}
                                color="red"
                                onClick={() => openDeleteModal(plan.id)}
                                disabled={['running', 'queued'].includes(plan.status)}
                              >
                                删除
                              </Menu.Item>
                            </Menu.Dropdown>
                          </Menu>
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

      {/* Delete Confirmation Modal */}
      <Modal
        opened={deleteModalOpened}
        onClose={() => setDeleteModalOpened(false)}
        title="确认删除"
      >
        <Text mb="md">确定要删除此测试计划吗？此操作无法撤销。</Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setDeleteModalOpened(false)}>
            取消
          </Button>
          <Button color="red" onClick={handleDelete}>
            删除
          </Button>
        </Group>
      </Modal>
    </Stack>
  )
}

export default TestPlanList
