/**
 * History Tab - Test Execution History
 *
 * Displays the history of executed test plans with filtering and search.
 * Features:
 * - View completed/failed/cancelled test plans
 * - Search and filter by status
 * - Pagination
 * - View execution details
 * - Delete history records
 *
 * @version 2.0.0
 */

import { useState, useMemo } from 'react'
import {
  Stack,
  Paper,
  Table,
  Badge,
  Group,
  Text,
  TextInput,
  Select,
  Button,
  ActionIcon,
  Tooltip,
  Pagination,
  Loader,
  Center,
  Modal,
} from '@mantine/core'
import {
  IconSearch,
  IconFileText,
  IconRefresh,
  IconTrash,
  IconChartBar,
} from '@tabler/icons-react'
import { useTestHistory, useDeleteExecutionRecord } from '../../hooks'

// Helper functions for status display
function getStatusColor(status: string): string {
  const colorMap: Record<string, string> = {
    completed: 'green',
    failed: 'red',
    cancelled: 'orange',
  }
  return colorMap[status] || 'gray'
}

function getStatusLabel(status: string): string {
  const labelMap: Record<string, string> = {
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return labelMap[status] || status
}

export function HistoryTab() {
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const [currentPage, setCurrentPage] = useState(1)
  const [detailModalOpened, setDetailModalOpened] = useState(false)
  const [selectedRecord, setSelectedRecord] = useState<any>(null)
  const itemsPerPage = 10

  // Query hooks
  const { data: historyRecords, isLoading, refetch } = useTestHistory({
    status: statusFilter as any,
  })

  // Mutation hooks
  const { mutate: deleteRecord } = useDeleteExecutionRecord()

  // Filter and paginate records
  const filteredRecords = useMemo(() => {
    if (!historyRecords) return []

    let filtered = [...historyRecords]

    // Apply search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(
        (record) =>
          record.test_plan_name.toLowerCase().includes(query) ||
          record.started_by.toLowerCase().includes(query),
      )
    }

    return filtered
  }, [historyRecords, searchQuery])

  const paginatedRecords = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage
    return filteredRecords.slice(startIndex, startIndex + itemsPerPage)
  }, [filteredRecords, currentPage])

  const totalPages = Math.ceil(filteredRecords.length / itemsPerPage)

  const handleViewDetails = (record: any) => {
    setSelectedRecord(record)
    setDetailModalOpened(true)
  }

  const handleDelete = (recordId: string) => {
    if (confirm('确定要删除此执行记录吗？此操作无法撤销。')) {
      deleteRecord(recordId)
    }
  }

  const formatDuration = (minutes: number): string => {
    if (minutes < 60) {
      return `${Math.round(minutes)} 分钟`
    }
    const hours = Math.floor(minutes / 60)
    const mins = Math.round(minutes % 60)
    return `${hours} 小时 ${mins} 分钟`
  }

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between">
        <div>
          <Text size="xl" fw={600}>
            执行历史
          </Text>
          <Text size="sm" c="dimmed">
            查看已完成、失败或取消的测试计划执行记录
          </Text>
        </div>
        <Button
          leftSection={<IconRefresh size={16} />}
          variant="light"
          onClick={() => refetch()}
          loading={isLoading}
        >
          刷新
        </Button>
      </Group>

      {/* Statistics */}
      <Paper p="md" withBorder>
        <Group gap="xl">
          <div>
            <Text size="xs" c="dimmed">
              总执行次数
            </Text>
            <Text size="lg" fw={600}>
              {filteredRecords.length}
            </Text>
          </div>
          <div>
            <Text size="xs" c="dimmed">
              成功
            </Text>
            <Text size="lg" fw={600} c="green">
              {filteredRecords.filter((r) => r.status === 'completed').length}
            </Text>
          </div>
          <div>
            <Text size="xs" c="dimmed">
              失败
            </Text>
            <Text size="lg" fw={600} c="red">
              {filteredRecords.filter((r) => r.status === 'failed').length}
            </Text>
          </div>
          <div>
            <Text size="xs" c="dimmed">
              已取消
            </Text>
            <Text size="lg" fw={600} c="orange">
              {filteredRecords.filter((r) => r.status === 'cancelled').length}
            </Text>
          </div>
          <div>
            <Text size="xs" c="dimmed">
              平均成功率
            </Text>
            <Text size="lg" fw={600} c="blue">
              {filteredRecords.length > 0
                ? `${Math.round(
                    (filteredRecords.reduce((sum, r) => sum + r.success_rate, 0) /
                      filteredRecords.length) *
                      100,
                  )}%`
                : '0%'}
            </Text>
          </div>
        </Group>
      </Paper>

      {/* Filters */}
      <Paper p="md" withBorder>
        <Group>
          <TextInput
            placeholder="搜索测试计划或执行者..."
            leftSection={<IconSearch size={16} />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ flex: 1 }}
          />
          <Select
            placeholder="状态筛选"
            clearable
            value={statusFilter}
            onChange={(value) => setStatusFilter(value || undefined)}
            data={[
              { value: 'completed', label: '已完成' },
              { value: 'failed', label: '失败' },
              { value: 'cancelled', label: '已取消' },
            ]}
            style={{ width: 200 }}
          />
        </Group>
      </Paper>

      {/* History Table */}
      <Paper withBorder>
        {isLoading ? (
          <Center p="xl">
            <Loader size="md" />
          </Center>
        ) : (
          <Stack gap={0}>
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>测试计划</Table.Th>
                  <Table.Th>状态</Table.Th>
                  <Table.Th>成功率</Table.Th>
                  <Table.Th>步骤统计</Table.Th>
                  <Table.Th>执行时长</Table.Th>
                  <Table.Th>执行者</Table.Th>
                  <Table.Th>完成时间</Table.Th>
                  <Table.Th>操作</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {paginatedRecords.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={8}>
                      <Stack align="center" gap="xs" py="xl">
                        <IconChartBar size={48} stroke={1.5} color="gray" />
                        <Text c="dimmed" ta="center">
                          {searchQuery || statusFilter
                            ? '未找到匹配的执行记录'
                            : '暂无执行历史'}
                        </Text>
                        <Text size="xs" c="dimmed" ta="center">
                          执行测试计划后，记录将显示在此处
                        </Text>
                      </Stack>
                    </Table.Td>
                  </Table.Tr>
                ) : (
                  paginatedRecords.map((record) => (
                    <Table.Tr key={record.id}>
                      {/* Plan Name */}
                      <Table.Td>
                        <Stack gap={2}>
                          <Text size="sm" fw={500}>
                            {record.test_plan_name}
                          </Text>
                          <Text size="xs" c="dimmed">
                            版本: {record.test_plan_version}
                          </Text>
                        </Stack>
                      </Table.Td>

                      {/* Status */}
                      <Table.Td>
                        <Badge
                          color={getStatusColor(record.status)}
                          variant="light"
                        >
                          {getStatusLabel(record.status)}
                        </Badge>
                      </Table.Td>

                      {/* Success Rate */}
                      <Table.Td>
                        <Text
                          size="sm"
                          fw={600}
                          c={record.success_rate > 0.8 ? 'green' : 'orange'}
                        >
                          {Math.round(record.success_rate * 100)}%
                        </Text>
                      </Table.Td>

                      {/* Step Statistics */}
                      <Table.Td>
                        <Stack gap={2}>
                          <Text size="xs">
                            <Text span c="green">
                              {record.completed_steps}
                            </Text>{' '}
                            /{' '}
                            <Text span c="dimmed">
                              {record.total_steps}
                            </Text>
                          </Text>
                          {record.failed_steps > 0 && (
                            <Text size="xs" c="red">
                              {record.failed_steps} 失败
                            </Text>
                          )}
                        </Stack>
                      </Table.Td>

                      {/* Duration */}
                      <Table.Td>
                        <Text size="sm">
                          {formatDuration(record.duration_minutes)}
                        </Text>
                      </Table.Td>

                      {/* Started By */}
                      <Table.Td>
                        <Text size="sm">{record.started_by}</Text>
                      </Table.Td>

                      {/* Completed At */}
                      <Table.Td>
                        <Tooltip
                          label={new Date(record.completed_at).toLocaleString()}
                        >
                          <Text size="sm" c="dimmed">
                            {new Date(record.completed_at).toLocaleDateString()}
                          </Text>
                        </Tooltip>
                      </Table.Td>

                      {/* Actions */}
                      <Table.Td>
                        <Group gap="xs">
                          <Tooltip label="查看详情">
                            <ActionIcon
                              variant="light"
                              color="blue"
                              onClick={() => handleViewDetails(record)}
                            >
                              <IconFileText size={16} />
                            </ActionIcon>
                          </Tooltip>
                          <Tooltip label="删除记录">
                            <ActionIcon
                              variant="light"
                              color="red"
                              onClick={() => handleDelete(record.id)}
                            >
                              <IconTrash size={16} />
                            </ActionIcon>
                          </Tooltip>
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))
                )}
              </Table.Tbody>
            </Table>

            {/* Pagination */}
            {totalPages > 1 && (
              <Group justify="center" p="md">
                <Pagination
                  value={currentPage}
                  onChange={setCurrentPage}
                  total={totalPages}
                />
              </Group>
            )}
          </Stack>
        )}
      </Paper>

      {/* Detail Modal */}
      <Modal
        opened={detailModalOpened}
        onClose={() => setDetailModalOpened(false)}
        title="执行详情"
        size="lg"
      >
        {selectedRecord && (
          <Stack gap="md">
            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="md">
                基本信息
              </Text>
              <Stack gap="xs">
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    测试计划:
                  </Text>
                  <Text size="sm">{selectedRecord.test_plan_name}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    版本:
                  </Text>
                  <Text size="sm">{selectedRecord.test_plan_version}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    状态:
                  </Text>
                  <Badge
                    color={getStatusColor(selectedRecord.status)}
                    variant="light"
                  >
                    {getStatusLabel(selectedRecord.status)}
                  </Badge>
                </Group>
              </Stack>
            </Paper>

            <Paper p="md" withBorder>
              <Text size="sm" fw={600} mb="md">
                执行统计
              </Text>
              <Stack gap="xs">
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    成功率:
                  </Text>
                  <Text size="sm" fw={600} c="green">
                    {Math.round(selectedRecord.success_rate * 100)}%
                  </Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    总步骤数:
                  </Text>
                  <Text size="sm">{selectedRecord.total_steps}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    完成步骤:
                  </Text>
                  <Text size="sm" c="green">
                    {selectedRecord.completed_steps}
                  </Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    失败步骤:
                  </Text>
                  <Text size="sm" c="red">
                    {selectedRecord.failed_steps}
                  </Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    跳过步骤:
                  </Text>
                  <Text size="sm" c="yellow">
                    {selectedRecord.skipped_steps}
                  </Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    执行时长:
                  </Text>
                  <Text size="sm">
                    {formatDuration(selectedRecord.duration_minutes)}
                  </Text>
                </Group>
              </Stack>
            </Paper>

            {selectedRecord.error_summary && (
              <Paper p="md" withBorder>
                <Text size="sm" fw={600} mb="xs" c="red">
                  错误摘要
                </Text>
                <Text size="sm" c="dimmed">
                  {selectedRecord.error_summary}
                </Text>
              </Paper>
            )}

            {selectedRecord.notes && (
              <Paper p="md" withBorder>
                <Text size="sm" fw={600} mb="xs">
                  备注
                </Text>
                <Text size="sm" c="dimmed">
                  {selectedRecord.notes}
                </Text>
              </Paper>
            )}
          </Stack>
        )}
      </Modal>
    </Stack>
  )
}

export default HistoryTab
