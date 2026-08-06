/**
 * History Tab - Test Execution History
 *
 * ARCH-1 S2: 数据源换到 test_executions 本表 — 每次执行一行
 * (用例直接执行 / 计划链每步 / 暗室首测 / 单相位诊断), VRT 除外。
 * 行 id 就是 TestExecution.id, 「生成报告」直接引用它 (换源前递的是
 * 计划摘要表主键, 报告收集器查不到任何行 — 设计稿 §1.4 的断线)。
 *
 * - 历史里会出现 running 行 (进行中样式, 不是"坏记录")
 * - phases_* 为 null = 该执行链不记相位进度, 显示 "—"
 * - 删除按钮已退场 (删执行行会毁报告引用, 清理走脚本 — 待决① 拍板)
 *
 * @version 3.0.0 (ARCH-1 S2)
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
import { parseServerDateTime, formatExecutionTag } from '../../../../utils/datetime'
import { CopyableId } from '../../../../components/CopyableId'
import {
  IconArticle,
  IconSearch,
  IconFileText,
  IconRefresh,
  IconChartBar,
  IconFileReport,
} from '@tabler/icons-react'
import { useTestHistory } from '../../hooks'
import { useReportGeneration } from '../../../Reports/hooks'
import type { TestExecutionRecord } from '../../types'

// Helper functions for status display
// 状态表要覆盖 test_executions.status 的全部合法值 (内审 F5): 换源后
// pending (会话建行未跑) 与 skipped (单相位诊断跳过) 都会出现在历史里,
// 漏了会 fallback 成原始英文
function getStatusColor(status: string): string {
  const colorMap: Record<string, string> = {
    running: 'blue',
    completed: 'green',
    failed: 'red',
    cancelled: 'orange',
    skipped: 'yellow',
    pending: 'gray',
  }
  return colorMap[status] || 'gray'
}

function getStatusLabel(status: string): string {
  const labelMap: Record<string, string> = {
    running: '进行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    skipped: '已跳过',
    pending: '待执行',
  }
  return labelMap[status] || status
}

// 来源链显示名 (executed_by 列)
function getSourceLabel(executedBy: string | null): string {
  const sourceMap: Record<string, string> = {
    test_case_runner: '用例执行',
    test_plan_runner: '计划链(旧)',
    commissioning_api: '暗室首测',
    commissioning_adhoc: '单相位诊断',
  }
  return (executedBy && sourceMap[executedBy]) || executedBy || '—'
}

// 相位进度: null = 该执行链不记相位进度 (显示 "—", 不伪造 0/N)
function formatPhases(record: TestExecutionRecord): string {
  if (record.phases_done === null || record.phases_total === null) return '—'
  return `${record.phases_done}/${record.phases_total}`
}

function formatDurationSec(seconds: number | null): string {
  if (seconds === null) return '—'
  if (seconds < 60) return `${Math.round(seconds)} 秒`
  const minutes = seconds / 60
  if (minutes < 60) return `${Math.round(minutes)} 分钟`
  const hours = Math.floor(minutes / 60)
  const mins = Math.round(minutes % 60)
  return `${hours} 小时 ${mins} 分钟`
}

interface HistoryTabProps {
  /**
   * P1-39: 点「查看日志」时回调, 参数是**完整 `execution_id`**。
   * 由 App 层接到「切到报告页 + 预填日志过滤」上。
   * 不传 = 不渲染该按钮（见下方 `onViewLogs &&`）—— 不留点了没反应的按钮。
   */
  onViewLogs?: (executionId: string) => void
}

export function HistoryTab({ onViewLogs }: HistoryTabProps = {}) {
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const [currentPage, setCurrentPage] = useState(1)
  const [detailModalOpened, setDetailModalOpened] = useState(false)
  const [selectedRecord, setSelectedRecord] = useState<TestExecutionRecord | null>(null)
  const itemsPerPage = 10

  // Query hooks (内审 F2: data 是 {total, items} — total 来自后端,
  // "拿到的行数"不再冒充"总执行数")
  const { data: historyPage, isLoading, refetch } = useTestHistory({
    status: statusFilter as 'running' | 'completed' | 'failed' | 'cancelled' | undefined,
  })
  const historyRecords = historyPage?.items
  const backendTotal = historyPage?.total ?? 0

  // Report generation hook (unified with PendingExecutionsList)
  const { generateExecutionReport, isGenerating } = useReportGeneration()

  // Filter and paginate records
  const filteredRecords = useMemo(() => {
    if (!historyRecords) return []

    let filtered = [...historyRecords]

    // Apply search filter (用例名 + 来源链)
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(
        (record) =>
          (record.case_name ?? '').toLowerCase().includes(query) ||
          (record.executed_by ?? '').toLowerCase().includes(query),
      )
    }

    return filtered
  }, [historyRecords, searchQuery])

  const paginatedRecords = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage
    return filteredRecords.slice(startIndex, startIndex + itemsPerPage)
  }, [filteredRecords, currentPage])

  const totalPages = Math.ceil(filteredRecords.length / itemsPerPage)

  const handleViewDetails = (record: TestExecutionRecord) => {
    setSelectedRecord(record)
    setDetailModalOpened(true)
  }

  const handleGenerateReport = (record: TestExecutionRecord) => {
    // record.id 就是 TestExecution.id — 报告收集器按它真查得到执行行
    generateExecutionReport(record)
  }

  const formatCompletedAt = (iso: string | null): { date: string; full: string } => {
    if (!iso) return { date: '—', full: '未完成' }
    const d = parseServerDateTime(iso)
    return { date: d.toLocaleDateString(), full: d.toLocaleString() }
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
            每次执行一行（用例执行 / 暗室首测 / 诊断），进行中的执行也在列
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
              {backendTotal}
            </Text>
            {backendTotal > filteredRecords.length && !searchQuery && (
              <Text size="xs" c="dimmed">
                (显示最近 {filteredRecords.length} 条)
              </Text>
            )}
          </div>
          <div>
            <Text size="xs" c="dimmed">
              进行中
            </Text>
            <Text size="lg" fw={600} c="blue">
              {filteredRecords.filter((r) => r.status === 'running').length}
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
        </Group>
      </Paper>

      {/* Filters */}
      <Paper p="md" withBorder>
        <Group>
          <TextInput
            placeholder="搜索用例名或来源..."
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
              { value: 'running', label: '进行中' },
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
                  <Table.Th>测试用例</Table.Th>
                  {/* P1-39: 执行标签 —— 短标签给人认, 复制给的是完整 execution_id。
                      ⚠ 固定宽度 + nowrap: 不给宽度的话 15 字符的标签会折成两行,
                      并把「状态」列挤到显示「已..」（浏览器实测发现）。 */}
                  <Table.Th w={150}>执行标签</Table.Th>
                  <Table.Th w={92}>状态</Table.Th>
                  <Table.Th>相位</Table.Th>
                  <Table.Th>执行时长</Table.Th>
                  <Table.Th>来源</Table.Th>
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
                          在测试用例库执行用例后，记录将显示在此处
                        </Text>
                      </Stack>
                    </Table.Td>
                  </Table.Tr>
                ) : (
                  paginatedRecords.map((record) => {
                    const completedAt = formatCompletedAt(record.completed_at)
                    return (
                      <Table.Tr key={record.id}>
                        {/* Case Name */}
                        <Table.Td>
                          <Text size="sm" fw={500}>
                            {record.case_name ?? '未命名用例'}
                          </Text>
                        </Table.Td>

                        {/* P1-39 执行标签: 显示本地时间短标签, 复制完整 execution_id。
                            record.id 就是 TestExecution.id
                            (同 handleGenerateReport 依赖的那个 id, 见其上方注释)。 */}
                        <Table.Td style={{ whiteSpace: 'nowrap' }}>
                          <CopyableId
                            value={record.id}
                            display={formatExecutionTag(record.started_at)}
                            label="点击复制完整 execution_id"
                          />
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

                        {/* Phase progress */}
                        <Table.Td>
                          <Text size="sm">
                            {formatPhases(record)}
                            {record.phases_failed !== null &&
                              record.phases_failed > 0 && (
                                <Text span size="xs" c="red" ml={4}>
                                  ({record.phases_failed} 失败)
                                </Text>
                              )}
                          </Text>
                        </Table.Td>

                        {/* Duration */}
                        <Table.Td>
                          <Text size="sm">
                            {formatDurationSec(record.duration_sec)}
                          </Text>
                        </Table.Td>

                        {/* Source chain */}
                        <Table.Td>
                          <Text size="sm">{getSourceLabel(record.executed_by)}</Text>
                        </Table.Td>

                        {/* Completed At */}
                        <Table.Td>
                          <Tooltip label={completedAt.full}>
                            <Text size="sm" c="dimmed">
                              {completedAt.date}
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
                            <Tooltip
                              label={
                                record.status === 'running'
                                  ? '执行中，完成后可生成报告'
                                  : '生成报告'
                              }
                            >
                              <ActionIcon
                                variant="light"
                                color="green"
                                disabled={record.status === 'running'}
                                onClick={() => handleGenerateReport(record)}
                                loading={isGenerating(record.id)}
                              >
                                <IconFileReport size={16} />
                              </ActionIcon>
                            </Tooltip>
                            {/* P1-39 第 4 条: 一键跳日志 —— 带的是**完整 UUID**,
                                不是上面那个给人看的短标签。onViewLogs 未接线时
                                不渲染, 不留一个点了没反应的按钮。 */}
                            {onViewLogs && (
                              <Tooltip label="查看这次执行的日志">
                                <ActionIcon
                                  variant="light"
                                  color="grape"
                                  onClick={() => onViewLogs(record.id)}
                                >
                                  <IconArticle size={16} />
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
                    测试用例:
                  </Text>
                  <Text size="sm">{selectedRecord.case_name ?? '未命名用例'}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    来源:
                  </Text>
                  <Text size="sm">{getSourceLabel(selectedRecord.executed_by)}</Text>
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
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    判定:
                  </Text>
                  <Text size="sm">
                    {selectedRecord.validation_pass === null
                      ? '未判定'
                      : selectedRecord.validation_pass
                        ? '通过'
                        : '不通过'}
                  </Text>
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
                    相位进度:
                  </Text>
                  <Text size="sm">{formatPhases(selectedRecord)}</Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    执行时长:
                  </Text>
                  <Text size="sm">
                    {formatDurationSec(selectedRecord.duration_sec)}
                  </Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    开始时间:
                  </Text>
                  <Text size="sm">
                    {selectedRecord.started_at
                      ? parseServerDateTime(selectedRecord.started_at).toLocaleString()
                      : '—'}
                  </Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">
                    完成时间:
                  </Text>
                  <Text size="sm">
                    {selectedRecord.completed_at
                      ? parseServerDateTime(selectedRecord.completed_at).toLocaleString()
                      : '—'}
                  </Text>
                </Group>
              </Stack>
            </Paper>

            {selectedRecord.error_message && (
              <Paper p="md" withBorder>
                <Text size="sm" fw={600} mb="xs" c="red">
                  错误信息
                </Text>
                <Text size="sm" c="dimmed">
                  {selectedRecord.error_message}
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
