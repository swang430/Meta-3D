import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Stack,
  Alert,
  Text,
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
import { parseServerDateTime } from '../../utils/datetime'
import {
  IconHistory,
  IconRefresh,
  IconPlayerPlay,
  IconPlayerPause,
  IconCheck,
  IconX,
  IconClock,
  IconAlertCircle,
  IconEye,
} from '@tabler/icons-react'
import { DigitalTwinExecutionModal } from './DigitalTwinExecutionModal'
import { OtaExecutionModal } from './OtaExecutionModal'
import { ConductedExecutionModal } from './ConductedExecutionModal'
import { TestReportModal } from './TestReportModal'
import { TestMode } from '../../types/roadTest'
import { fetchExecutions } from '../../api/roadTestService'

// Local type definition to avoid Vite ESM issues with type-only exports
type ExecutionStatus = 'idle' | 'initializing' | 'configured' | 'running' | 'paused' | 'completed' | 'failed' | 'stopped'

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
export function VirtualExecutionHistory({ scenarioId, scenarioName, initialExecution, onDismiss }: {
  scenarioId?: string
  scenarioName?: string
  initialExecution?: import('./index').ExecutionLink
  onDismiss: () => void
}) {
  const selected = (mode: TestMode) => initialExecution?.mode === mode
    ? { id: initialExecution.id, name: scenarioName ?? '' } : null
  const [twin, setTwin] = useState<{ id: string; name: string } | null>(() => selected('digital_twin'))
  const [ota, setOta] = useState<{ id: string; name: string } | null>(() => selected('ota'))
  const [conducted, setConducted] = useState<{ id: string; name: string } | null>(() => selected('conducted'))
  const [reportModalOpen, setReportModalOpen] = useState(false)
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null)

  const { data: executions, isLoading, error, refetch } = useQuery({
    queryKey: ['road-test-executions', scenarioId],
    queryFn: () => fetchExecutions({ scenario_id: scenarioId }),
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
                      {MODE_LABELS[exec.mode] || exec.mode}{exec.mode === 'ota' && '（模拟硬件，现场待验）'}{exec.mode === 'conducted' && (exec.conducted?.binding?.execution_mode === 'simulated'
                        ? '（模拟硬件）' : exec.conducted?.binding?.execution_mode === 'real' ? '（真实设备绑定）' : '（绑定待确认）')}
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
                        ? parseServerDateTime(exec.start_time).toLocaleString('zh-CN')
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
                      {exec.mode === 'digital_twin' && <Button size="xs" onClick={() => setTwin({ id: exec.execution_id, name: exec.scenario_name })}>回看模拟执行</Button>}
                      {exec.mode === 'ota' && <Button size="xs" variant="light" onClick={() => setOta({ id: exec.execution_id, name: exec.scenario_name })}>查看执行</Button>}
                      {exec.mode === 'conducted' && <Button size="xs" variant="light" onClick={() =>
                        setConducted({ id: exec.execution_id, name: exec.scenario_name })}>查看执行</Button>}
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

      {twin && <DigitalTwinExecutionModal initialId={twin.id} scenario={twin} onClose={() => { setTwin(null); onDismiss() }} />}
      {conducted && <ConductedExecutionModal key={conducted.id} opened initialId={conducted.id}
        scenario={{ id: '', name: conducted.name }} onClose={() => { setConducted(null); onDismiss() }} />}
      {ota && <OtaExecutionModal key={ota.id} opened initialId={ota.id}
        scenario={{ id: '', name: ota.name }} onClose={() => { setOta(null); onDismiss() }} />}
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
