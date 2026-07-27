/**
 * P2-8 ② 运行态 — left main zone, titled "最近执行".
 *
 * ARCH-1 S2: 数据源换到 test_executions 本表 — 每次执行一行 (用例执行 /
 * 暗室首测 / 诊断), **含 running 行** (旧版"只有终态"的注记随换源作废)。
 * 进度单位是相位 (phases_done/phases_total), 不再是伪造的"成功率"。
 * phases_* 为 null = 该执行链不记相位进度, 进度条不渲染。
 * Empty list → "暂无执行记录" + 一键去 TestManagement.
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
  running: 'blue',
  completed: 'green',
  failed: 'red',
  cancelled: 'gray',
  pending: 'gray',
}

const STATUS_LABEL: Record<string, string> = {
  running: '进行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  pending: '待执行',
}

// 来源链显示名 (executed_by)
const SOURCE_LABEL: Record<string, string> = {
  test_case_runner: '用例执行',
  test_plan_runner: '计划链(旧)',
  commissioning_api: '暗室首测',
  commissioning_adhoc: '单相位诊断',
}

function statusColor(status: TestExecutionStatus): string {
  return STATUS_COLOR[status] ?? 'blue'
}

function statusLabel(status: TestExecutionStatus): string {
  return STATUS_LABEL[status] ?? status
}

function formatStarted(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

function formatDurationSec(seconds: number | null): string {
  if (seconds === null) return '—'
  if (seconds < 60) return `${Math.round(seconds)} 秒`
  return `${Math.round(seconds / 60)} 分钟`
}

function ExecutionRow({ item }: { item: TestExecutionItem }) {
  const hasPhases = item.phases_done !== null && item.phases_total !== null
  return (
    <Card withBorder radius="sm" padding="sm">
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap">
          <Text fw={600} lineClamp={1} title={item.case_name ?? '未命名用例'}>
            {item.case_name ?? '未命名用例'}
            <Text span size="xs" c="dimmed" ml={6}>
              {(item.executed_by && SOURCE_LABEL[item.executed_by]) ||
                item.executed_by ||
                ''}
            </Text>
          </Text>
          <Badge color={statusColor(item.status)} variant="light">
            {statusLabel(item.status)}
          </Badge>
        </Group>

        {hasPhases && (
          <Group gap="xs" wrap="nowrap">
            <Text size="xs" c="dimmed" w={64}>
              相位
            </Text>
            <Progress
              value={
                item.phases_total! > 0
                  ? (item.phases_done! / item.phases_total!) * 100
                  : 0
              }
              color={statusColor(item.status)}
              size="sm"
              radius="sm"
              style={{ flex: 1 }}
            />
            <Text size="xs" fw={600} w={48} ta="right">
              {item.phases_done}/{item.phases_total}
            </Text>
          </Group>
        )}

        <Group gap="md" wrap="wrap">
          <Group gap={4}>
            <IconClock size={13} color="var(--mantine-color-gray-5)" />
            <Text size="xs" c="dimmed">
              {formatDurationSec(item.duration_sec)}
            </Text>
          </Group>
          {item.phases_failed !== null && item.phases_failed > 0 && (
            <Text size="xs" c="red">
              {item.phases_failed} 相位失败
            </Text>
          )}
          <Text size="xs" c="dimmed">
            {formatStarted(item.started_at)}
          </Text>
        </Group>

        {item.error_message && (
          <Text size="xs" c="red.7" lineClamp={2} title={item.error_message}>
            {item.error_message}
          </Text>
        )}
      </Stack>
    </Card>
  )
}

export function ZoneActiveRun({ onNavigateTestManagement }: { onNavigateTestManagement: () => void }) {
  const { data, isLoading, error } = useQuery({
    // ARCH-1 S2: key 换代 — 返回形状变了必须换 queryKey (旧缓存是计划摘要形状)
    queryKey: ['cockpit', 'executions', 'v2'],
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
              尚未运行过任何测试用例
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
