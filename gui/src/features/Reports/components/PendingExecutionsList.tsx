/**
 * Pending Executions List Component
 *
 * Displays test executions (both test plans and virtual road tests)
 * that have not yet been archived as reports
 */

import { useState } from 'react'
import {
  Card,
  Table,
  Badge,
  Button,
  Group,
  Text,
  Stack,
  ActionIcon,
  Tooltip,
  Loader,
  Center,
  Alert,
  Tabs,
} from '@mantine/core'
import { parseServerDateTime } from '../../../utils/datetime'
import {
  IconFileReport,
  IconRefresh,
  IconAlertCircle,
  IconTestPipe,
  IconCar,
} from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import client from '../../../api/client'
import {
  useReportGeneration,
  type RoadTestExecutionRecord,
} from '../hooks'

// ARCH-1 S2: 待归档行来自 test_executions 本表 (与执行历史同源同形状),
// id 就是 TestExecution.id — 报告 test_execution_ids 直接引用。
interface PendingExecutionItem {
  id: string
  case_name: string | null
  status: string
  duration_sec: number | null
  completed_at: string | null
  executed_by: string | null
}

interface PendingExecutionsResponse {
  total: number
  items: PendingExecutionItem[]
}

// Fetch completed test executions (limit 顶到后端上限, 内审 F2 同源)
async function fetchCompletedExecutions(): Promise<PendingExecutionItem[]> {
  const response = await client.get<PendingExecutionsResponse>('/test-executions', {
    params: { status: 'completed', limit: 1000 },
  })
  return response.data.items
}

// Fetch completed road test executions
async function fetchRoadTestExecutions(): Promise<RoadTestExecutionRecord[]> {
  const response = await client.get<RoadTestExecutionRecord[]>('/road-test/executions')
  return response.data.filter((exec) => exec.status === 'completed')
}

// Fetch existing reports to filter out already archived executions
async function fetchReportExecutionIds(): Promise<{ testPlan: Set<string>; roadTest: Set<string> }> {
  const response = await client.get<{ reports: { test_execution_ids?: string[]; road_test_execution_id?: string }[] }>('/reports')
  const testPlanIds = new Set<string>()
  const roadTestIds = new Set<string>()

  response.data.reports.forEach((report) => {
    report.test_execution_ids?.forEach((id) => testPlanIds.add(id))
    if (report.road_test_execution_id) {
      roadTestIds.add(report.road_test_execution_id)
    }
  })

  return { testPlan: testPlanIds, roadTest: roadTestIds }
}

export function PendingExecutionsList() {
  const [activeTab, setActiveTab] = useState<string | null>('test-plans')

  // Report generation hook (unified with HistoryTab)
  const { generateExecutionReport, generateVRTReport, isGenerating } = useReportGeneration()

  // Fetch completed test executions
  // (ARCH-1 S2: key 换代 — 数据形状变了必须换 queryKey, 旧缓存是计划摘要形状)
  const { data: completedExecutions, isLoading: loadingTestPlans, refetch: refetchTestPlans } = useQuery({
    queryKey: ['pending-executions', 'v2'],
    queryFn: fetchCompletedExecutions,
  })

  // Fetch road test executions
  const { data: roadTestExecutions, isLoading: loadingRoadTests, refetch: refetchRoadTests } = useQuery({
    queryKey: ['pending-road-test-executions'],
    queryFn: fetchRoadTestExecutions,
  })

  // Fetch report execution IDs
  const { data: archivedIds, isLoading: loadingReports } = useQuery({
    queryKey: ['archived-execution-ids'],
    queryFn: fetchReportExecutionIds,
  })

  // Filter to get only pending (unarchived) executions
  // 内审 F2: 单相位诊断行收尾后也是 completed, 但它不是"可归档的正式
  // 执行" (没有相位进度, 出的报告近乎空) — 与 commissioning 列表隐藏
  // diagnostic_ad_hoc 的既定约定同源, 这里按来源链排除
  const pendingTestPlans = completedExecutions?.filter(
    (exec) =>
      !archivedIds?.testPlan.has(exec.id) &&
      exec.executed_by !== 'commissioning_adhoc'
  ) || []

  const pendingRoadTests = roadTestExecutions?.filter(
    (exec) => !archivedIds?.roadTest.has(exec.execution_id)
  ) || []

  // Use unified report generation hook
  const handleGenerateExecutionReport = (record: PendingExecutionItem) => {
    generateExecutionReport(record)
  }

  // Use unified report generation hook with VRT content_data fetching
  const handleGenerateRoadTestReport = (record: RoadTestExecutionRecord) => {
    generateVRTReport(record)
  }

  const handleRefresh = () => {
    refetchTestPlans()
    refetchRoadTests()
  }

  const isLoading = loadingTestPlans || loadingRoadTests || loadingReports

  // ARCH-1 S2: 执行行的时长是秒 (duration_sec), null 显示 "—"
  const formatDurationSec = (seconds: number | null): string => {
    if (seconds === null) return '—'
    if (seconds < 60) return `${Math.round(seconds)} 秒`
    const minutes = seconds / 60
    if (minutes < 60) return `${Math.round(minutes)} 分钟`
    const hours = Math.floor(minutes / 60)
    const mins = Math.round(minutes % 60)
    return `${hours} 小时 ${mins} 分钟`
  }

  // 来源链显示名 (与 HistoryTab 同映射)
  const sourceLabel = (executedBy: string | null): string => {
    const sourceMap: Record<string, string> = {
      test_case_runner: '用例执行',
      test_plan_runner: '计划链(旧)',
      commissioning_api: '暗室首测',
      commissioning_adhoc: '单相位诊断',
    }
    return (executedBy && sourceMap[executedBy]) || executedBy || '—'
  }

  const formatSeconds = (seconds: number): string => {
    if (seconds < 60) {
      return `${Math.round(seconds)} 秒`
    }
    return `${Math.round(seconds / 60)} 分钟`
  }

  if (isLoading) {
    return (
      <Center p="xl">
        <Loader size="md" />
        <Text ml="md" c="dimmed">加载待归档执行...</Text>
      </Center>
    )
  }

  const totalPending = pendingTestPlans.length + pendingRoadTests.length

  if (totalPending === 0) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} color="gray" title="无待归档执行">
        所有已完成的测试执行都已生成报告
      </Alert>
    )
  }

  return (
    <Stack gap="md">
      {/* Header */}
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          共 {totalPending} 个待归档的执行记录 (测试执行: {pendingTestPlans.length}, 虚拟路测: {pendingRoadTests.length})
        </Text>
        <Button
          variant="light"
          leftSection={<IconRefresh size={16} />}
          onClick={handleRefresh}
        >
          刷新
        </Button>
      </Group>

      {/* Tabs for different execution types */}
      <Tabs value={activeTab} onChange={setActiveTab}>
        <Tabs.List>
          <Tabs.Tab
            value="test-plans"
            leftSection={<IconTestPipe size={16} />}
            rightSection={pendingTestPlans.length > 0 ? <Badge size="sm">{pendingTestPlans.length}</Badge> : null}
          >
            测试执行
          </Tabs.Tab>
          <Tabs.Tab
            value="road-tests"
            leftSection={<IconCar size={16} />}
            rightSection={pendingRoadTests.length > 0 ? <Badge size="sm">{pendingRoadTests.length}</Badge> : null}
          >
            虚拟路测
          </Tabs.Tab>
        </Tabs.List>

        {/* Test Executions Tab (ARCH-1 S2: 行来自 test_executions 本表) */}
        <Tabs.Panel value="test-plans" pt="md">
          {pendingTestPlans.length === 0 ? (
            <Alert icon={<IconAlertCircle size={16} />} color="gray">
              没有待归档的测试执行记录
            </Alert>
          ) : (
            <Card withBorder>
              <Table highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>测试用例</Table.Th>
                    <Table.Th>执行时长</Table.Th>
                    <Table.Th>完成时间</Table.Th>
                    <Table.Th>来源</Table.Th>
                    <Table.Th>操作</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {pendingTestPlans.map((record) => (
                    <Table.Tr key={record.id}>
                      <Table.Td>
                        <Text size="sm" fw={500}>
                          {record.case_name ?? '未命名用例'}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{formatDurationSec(record.duration_sec)}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" c="dimmed">
                          {record.completed_at
                            ? parseServerDateTime(record.completed_at).toLocaleDateString()
                            : '—'}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{sourceLabel(record.executed_by)}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Tooltip label="生成报告并归档">
                          <ActionIcon
                            variant="light"
                            color="green"
                            onClick={() => handleGenerateExecutionReport(record)}
                            loading={isGenerating(record.id)}
                          >
                            <IconFileReport size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Card>
          )}
        </Tabs.Panel>

        {/* Road Tests Tab */}
        <Tabs.Panel value="road-tests" pt="md">
          {pendingRoadTests.length === 0 ? (
            <Alert icon={<IconAlertCircle size={16} />} color="gray" title="没有待归档的虚拟路测执行记录">
              <Text size="sm">
                虚拟路测执行数据存储在当前会话中。如果服务已重启，请在"虚拟路测"页面重新执行测试。
                已生成的报告可以在"我的报告"标签页中查看。
              </Text>
            </Alert>
          ) : (
            <Card withBorder>
              <Table highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>场景名称</Table.Th>
                    <Table.Th>测试模式</Table.Th>
                    <Table.Th>执行时长</Table.Th>
                    <Table.Th>完成时间</Table.Th>
                    <Table.Th>操作</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {pendingRoadTests.map((record) => (
                    <Table.Tr key={record.execution_id}>
                      <Table.Td>
                        <Text size="sm" fw={500}>
                          {record.scenario_name}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge size="sm" variant="light">
                          {record.mode === 'ota' ? 'OTA测试' :
                           record.mode === 'conducted' ? '传导测试' : '数字孪生'}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">
                          {record.duration_s ? formatSeconds(record.duration_s) : '-'}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" c="dimmed">
                          {record.end_time
                            ? parseServerDateTime(record.end_time).toLocaleDateString()
                            : '-'}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Tooltip label="生成报告并归档">
                          <ActionIcon
                            variant="light"
                            color="green"
                            onClick={() => handleGenerateRoadTestReport(record)}
                            loading={isGenerating(record.execution_id)}
                          >
                            <IconFileReport size={16} />
                          </ActionIcon>
                        </Tooltip>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Card>
          )}
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}
