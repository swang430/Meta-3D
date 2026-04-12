/**
 * VirtualRoadTest - 虚拟路测主组件
 * 简化的工作流：场景库 + 执行历史 + OTA映射器
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Stack,
  Alert,
  Text,
  Tabs,
  SegmentedControl,
  Group,
  Badge,
  Paper,
  Table,
  Loader,
  Center,
  ActionIcon,
  Tooltip,
  Button,
} from '@mantine/core'
import {
  IconInfoCircle,
  IconBooks,
  IconHistory,
  IconMapPin,
  IconCpu,
  IconPlugConnected,
  IconRadar2,
  IconRefresh,
  IconPlayerPlay,
  IconPlayerPause,
  IconCheck,
  IconX,
  IconClock,
  IconAlertCircle,
  IconFileReport,
  IconEye,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import ScenarioLibrary from './ScenarioLibrary'
import { OTAMapper } from '../OTAMapper'
import { TestReportModal } from './TestReportModal'
import { TestMode } from '../../types/roadTest'
import { fetchExecutions } from '../../api/roadTestService'

// Local type definition to avoid Vite ESM issues with type-only exports
type ExecutionStatus = 'idle' | 'initializing' | 'configured' | 'running' | 'paused' | 'completed' | 'failed' | 'stopped'

// 测试模式配置
const TEST_MODES = [
  {
    value: TestMode.DIGITAL_TWIN,
    label: '数字孪生',
    icon: IconCpu,
    color: 'blue',
    description: '纯软件仿真，成本最低',
  },
  {
    value: TestMode.CONDUCTED,
    label: '传导测试',
    icon: IconPlugConnected,
    color: 'green',
    description: '仪表直连，精度较高',
  },
  {
    value: TestMode.OTA,
    label: 'OTA测试',
    icon: IconRadar2,
    color: 'orange',
    description: 'MPAC暗室，精度最高',
  },
]

export function VirtualRoadTest() {
  const [activeTab, setActiveTab] = useState<string>('library')
  const [selectedMode, setSelectedMode] = useState<TestMode>(TestMode.CONDUCTED)

  const currentMode = TEST_MODES.find((m) => m.value === selectedMode)

  return (
    <Stack gap="md">
      {/* 顶部信息栏 */}
      <Alert variant="light" color="blue" icon={<IconInfoCircle />}>
        <Text size="sm">
          <strong>虚拟路测平台</strong> - 在实验室环境中复现真实道路测试场景，支持三种测试模式：数字孪生、传导测试、OTA辐射测试
        </Text>
      </Alert>

      {/* 测试模式选择器 */}
      <Paper p="md" withBorder>
        <Group justify="space-between" align="center">
          <Group gap="md">
            <Text size="sm" fw={500} c="dimmed">
              测试模式：
            </Text>
            <SegmentedControl
              value={selectedMode}
              onChange={(value) => setSelectedMode(value as TestMode)}
              data={TEST_MODES.map((mode) => ({
                value: mode.value,
                label: (
                  <Group gap="xs">
                    <mode.icon size={16} />
                    <span>{mode.label}</span>
                  </Group>
                ),
              }))}
            />
          </Group>
          {currentMode && (
            <Badge color={currentMode.color} variant="light" size="lg">
              {currentMode.description}
            </Badge>
          )}
        </Group>
      </Paper>

      {/* 标签页 */}
      <Tabs value={activeTab} onChange={(value) => setActiveTab(value || 'library')}>
        <Tabs.List>
          <Tabs.Tab value="library" leftSection={<IconBooks size={16} />}>
            场景库
          </Tabs.Tab>
          <Tabs.Tab value="history" leftSection={<IconHistory size={16} />}>
            执行历史
          </Tabs.Tab>
          <Tabs.Tab value="ota-mapper" leftSection={<IconMapPin size={16} />}>
            OTA映射器
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="library" pt="md">
          <ScenarioLibrary testMode={selectedMode} />
        </Tabs.Panel>

        <Tabs.Panel value="history" pt="md">
          <ExecutionHistory />
        </Tabs.Panel>

        <Tabs.Panel value="ota-mapper" pt="md">
          <OTAMapper />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}

// 状态图标和颜色映射
const STATUS_CONFIG: Record<ExecutionStatus, { icon: typeof IconCheck; color: string; label: string }> = {
  idle: { icon: IconClock, color: 'gray', label: '空闲' },
  initializing: { icon: IconClock, color: 'blue', label: '初始化中' },
  configured: { icon: IconCheck, color: 'cyan', label: '已配置' },
  running: { icon: IconPlayerPlay, color: 'blue', label: '运行中' },
  paused: { icon: IconPlayerPause, color: 'yellow', label: '已暂停' },
  completed: { icon: IconCheck, color: 'green', label: '已完成' },
  failed: { icon: IconX, color: 'red', label: '失败' },
  stopped: { icon: IconX, color: 'orange', label: '已停止' },
}

// 测试模式标签
const MODE_LABELS: Record<TestMode, string> = {
  [TestMode.DIGITAL_TWIN]: '数字孪生',
  [TestMode.CONDUCTED]: '传导测试',
  [TestMode.OTA]: 'OTA测试',
}

/**
 * 执行历史组件 - 显示虚拟路测的执行记录
 */
function ExecutionHistory() {
  const [reportModalOpen, setReportModalOpen] = useState(false)
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null)

  const { data: executions, isLoading, error, refetch } = useQuery({
    queryKey: ['road-test-executions'],
    queryFn: () => fetchExecutions(),
    refetchInterval: 5000, // 每5秒刷新一次
  })

  const handleViewReport = (executionId: string) => {
    setSelectedExecutionId(executionId)
    setReportModalOpen(true)
  }

  const handleCloseReport = () => {
    setReportModalOpen(false)
    setSelectedExecutionId(null)
  }

  if (isLoading) {
    return (
      <Center py="xl">
        <Loader size="md" />
        <Text c="dimmed" ml="md">加载执行历史...</Text>
      </Center>
    )
  }

  if (error) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} title="加载失败" color="red">
        无法加载执行历史: {(error as Error).message}
      </Alert>
    )
  }

  if (!executions || executions.length === 0) {
    return (
      <Paper p="xl" withBorder>
        <Stack align="center" gap="md">
          <IconHistory size={48} stroke={1.5} color="gray" />
          <Text c="dimmed" ta="center">
            暂无执行记录
          </Text>
          <Text size="sm" c="dimmed" ta="center">
            在场景库中选择场景并执行测试后，执行记录将显示在此处
          </Text>
          <Button variant="light" leftSection={<IconRefresh size={16} />} onClick={() => refetch()}>
            刷新
          </Button>
        </Stack>
      </Paper>
    )
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Text fw={500}>执行历史 ({executions.length} 条记录)</Text>
        <Tooltip label="刷新">
          <ActionIcon variant="subtle" onClick={() => refetch()}>
            <IconRefresh size={16} />
          </ActionIcon>
        </Tooltip>
      </Group>

      <Paper withBorder>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>执行 ID</Table.Th>
              <Table.Th>场景</Table.Th>
              <Table.Th>模式</Table.Th>
              <Table.Th>状态</Table.Th>
              <Table.Th>进度</Table.Th>
              <Table.Th>开始时间</Table.Th>
              <Table.Th>持续时间</Table.Th>
              <Table.Th>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {executions.map((exec) => {
              const statusConfig = STATUS_CONFIG[exec.status] || STATUS_CONFIG.idle
              const StatusIcon = statusConfig.icon
              const isCompleted = exec.status === 'completed'

              return (
                <Table.Tr key={exec.execution_id}>
                  <Table.Td>
                    <Text size="sm" ff="monospace">{exec.execution_id.slice(0, 12)}...</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{exec.scenario_name}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge size="sm" variant="light">
                      {MODE_LABELS[exec.mode] || exec.mode}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      size="sm"
                      color={statusConfig.color}
                      leftSection={<StatusIcon size={12} />}
                    >
                      {statusConfig.label}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{exec.progress_percent}%</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {exec.start_time
                        ? new Date(exec.start_time).toLocaleString('zh-CN')
                        : '-'}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {exec.duration_s ? `${Math.round(exec.duration_s)}s` : '-'}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      {isCompleted && (
                        <Tooltip label="查看报告">
                          <ActionIcon
                            variant="light"
                            color="blue"
                            onClick={() => handleViewReport(exec.execution_id)}
                          >
                            <IconEye size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </Paper>

      {/* Report Modal */}
      {selectedExecutionId && (
        <TestReportModal
          opened={reportModalOpen}
          onClose={handleCloseReport}
          executionId={selectedExecutionId}
        />
      )}
    </Stack>
  )
}
