/**
 * P2-8 ② 运行态 — left main zone, titled "最近执行".
 *
 * Honesty note: GET /test-executions returns TERMINAL-STATE history
 * (completed / failed / cancelled), NOT a live-running stream. There is
 * no live-execution endpoint in this build, so this zone deliberately
 * shows the most recent 5 finished executions rather than faking a
 * "正在运行 72%" live row. Empty list → "暂无执行记录" + 一键去 TestManagement.
 *
 * Polls ~5s.
 */
import { useQuery } from '@tanstack/react-query'
import {
  Card,
  Group,
  Stack,
  Text,
  Badge,
  Loader,
  Alert,
  Button,
  Progress,
  Tooltip,
} from '@mantine/core'
import { IconHistory, IconArrowRight, IconClock } from '@tabler/icons-react'
import { fetchTestExecutions } from '../../api/service'
import type { TestExecutionItem, TestExecutionStatus } from '../../types/api'

const STATUS_COLOR: Record<string, string> = {
  completed: 'green',
  failed: 'red',
  cancelled: 'gray',
}

const STATUS_LABEL: Record<string, string> = {
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

function statusColor(status: TestExecutionStatus): string {
  return STATUS_COLOR[status] ?? 'blue'
}

function statusLabel(status: TestExecutionStatus): string {
  return STATUS_LABEL[status] ?? status
}

function formatStarted(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

function ExecutionRow({ item }: { item: TestExecutionItem }) {
  return (
    <Card withBorder radius="sm" padding="sm">
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap">
          <Text fw={600} lineClamp={1} title={item.test_plan_name}>
            {item.test_plan_name}
            <Text span size="xs" c="dimmed" ml={6}>
              v{item.test_plan_version}
            </Text>
          </Text>
          <Badge color={statusColor(item.status)} variant="light">
            {statusLabel(item.status)}
          </Badge>
        </Group>

        <Group gap="xs" wrap="nowrap">
          <Text size="xs" c="dimmed" w={64}>
            成功率
          </Text>
          <Progress
            value={item.success_rate}
            color={statusColor(item.status)}
            size="sm"
            radius="sm"
            style={{ flex: 1 }}
          />
          <Text size="xs" fw={600} w={48} ta="right">
            {item.success_rate.toFixed(0)}%
          </Text>
        </Group>

        <Group gap="md" wrap="wrap">
          <Group gap={4}>
            <IconClock size={13} color="var(--mantine-color-gray-5)" />
            <Text size="xs" c="dimmed">
              {item.duration_minutes.toFixed(0)} 分钟
            </Text>
          </Group>
          <Text size="xs" c="dimmed">
            {item.completed_steps}/{item.total_steps} 步
            {item.failed_steps > 0 ? ` · ${item.failed_steps} 失败` : ''}
          </Text>
          <Text size="xs" c="dimmed">
            {formatStarted(item.started_at)}
          </Text>
        </Group>

        {item.error_summary && (
          <Text size="xs" c="red.7" lineClamp={2} title={item.error_summary}>
            {item.error_summary}
          </Text>
        )}
      </Stack>
    </Card>
  )
}

export function ZoneActiveRun({ onNavigateTestManagement }: { onNavigateTestManagement: () => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['cockpit', 'executions'],
    queryFn: () => fetchTestExecutions({ limit: 5 }),
    refetchInterval: 5_000,
  })

  const items = data?.items ?? []

  return (
    <Card withBorder radius="md" padding="lg" h="100%">
      <Stack gap="md" h="100%">
        <Group justify="space-between">
          <Group gap="xs">
            <IconHistory size={20} />
            <Text fw={700} fz="lg">
              最近执行
            </Text>
          </Group>
          <Tooltip label="终结态历史，非实时运行流">
            <Badge variant="light" color="gray">
              历史
            </Badge>
          </Tooltip>
        </Group>

        {isLoading && (
          <Group gap="xs">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">
              执行记录读取中……
            </Text>
          </Group>
        )}

        {error && (
          <Alert color="red" variant="light" title="执行记录读取失败">
            {(error as Error).message}
          </Alert>
        )}

        {!isLoading && !error && items.length === 0 && (
          <Stack gap="sm" align="center" py="lg">
            <Text fw={600}>暂无执行记录</Text>
            <Text size="sm" c="dimmed">
              尚未运行过任何测试计划
            </Text>
            <Button
              variant="light"
              rightSection={<IconArrowRight size={16} />}
              onClick={onNavigateTestManagement}
            >
              去测试管理
            </Button>
          </Stack>
        )}

        {items.length > 0 && (
          <Stack gap="sm">
            {items.map((item) => (
              <ExecutionRow key={item.id} item={item} />
            ))}
            <Button
              variant="subtle"
              size="xs"
              rightSection={<IconArrowRight size={14} />}
              onClick={onNavigateTestManagement}
            >
              查看全部执行历史
            </Button>
          </Stack>
        )}
      </Stack>
    </Card>
  )
}
