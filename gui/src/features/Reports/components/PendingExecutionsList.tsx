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
  type TestPlanExecutionRecord,
  type RoadTestExecutionRecord,
} from '../hooks'

interface TestPlanExecutionsResponse {
  total: number
  items: TestPlanExecutionRecord[]
}

// Fetch completed test plan executions
async function fetchTestPlanExecutions(): Promise<TestPlanExecutionRecord[]> {
  const response = await client.get<TestPlanExecutionsResponse>('/test-executions', {
    params: { status: 'completed' },
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
  const { generateTestPlanReport, generateVRTReport, isGenerating } = useReportGeneration()

  // Fetch test plan executions
  const { data: testPlanExecutions, isLoading: loadingTestPlans, refetch: refetchTestPlans } = useQuery({
    queryKey: ['pending-test-plan-executions'],
    queryFn: fetchTestPlanExecutions,
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
  const pendingTestPlans = testPlanExecutions?.filter(
    (exec) => !archivedIds?.testPlan.has(exec.id)
  ) || []

  const pendingRoadTests = roadTestExecutions?.filter(
    (exec) => !archivedIds?.roadTest.has(exec.execution_id)
  ) || []

  // Use unified report generation hook
  const handleGenerateTestPlanReport = (record: TestPlanExecutionRecord) => {
    generateTestPlanReport(record)
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

  const formatDuration = (minutes: number): string => {
    if (minutes < 60) {
      return `${Math.round(minutes)} 分钟`
    }
    const hours = Math.floor(minutes / 60)
    const mins = Math.round(minutes % 60)
    return `${hours} 小时 ${mins} 分钟`
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
          共 {totalPending} 个待归档的执行记录 (测试计划: {pendingTestPlans.length}, 虚拟路测: {pendingRoadTests.length})
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
            测试计划
          </Tabs.Tab>
          <Tabs.Tab
            value="road-tests"
            leftSection={<IconCar size={16} />}
            rightSection={pendingRoadTests.length > 0 ? <Badge size="sm">{pendingRoadTests.length}</Badge> : null}
          >
            虚拟路测
          </Tabs.Tab>
        </Tabs.List>

        {/* Test Plans Tab */}
        <Tabs.Panel value="test-plans" pt="md">
          {pendingTestPlans.length === 0 ? (
            <Alert icon={<IconAlertCircle size={16} />} color="gray">
              没有待归档的测试计划执行记录
            </Alert>
          ) : (
            <Card withBorder>
              <Table highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>测试计划</Table.Th>
                    <Table.Th>成功率</Table.Th>
                    <Table.Th>执行时长</Table.Th>
                    <Table.Th>完成时间</Table.Th>
                    <Table.Th>执行者</Table.Th>
                    <Table.Th>操作</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {pendingTestPlans.map((record) => (
                    <Table.Tr key={record.id}>
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
                      <Table.Td>
                        <Text
                          size="sm"
                          fw={600}
                          c={record.success_rate > 0.8 ? 'green' : 'orange'}
                        >
                          {Math.round(record.success_rate * 100)}%
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{formatDuration(record.duration_minutes)}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" c="dimmed">
                          {new Date(record.completed_at).toLocaleDateString()}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{record.started_by}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Tooltip label="生成报告并归档">
                          <ActionIcon
                            variant="light"
                            color="green"
                            onClick={() => handleGenerateTestPlanReport(record)}
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
                            ? new Date(record.end_time).toLocaleDateString()
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
