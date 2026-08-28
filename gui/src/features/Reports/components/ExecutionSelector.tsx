/**
 * Execution Selector Component
 *
 * 报告向导「选择数据」步骤: 挑要进报告的执行记录。
 *
 * ARCH-1 S4a 换源 (外审 Codex #243 round-2 P1): 原先读
 * `GET /test-plans/{planId}/executions`, 必须先在上一步选一个测试计划。
 * 计划链拆除后那条路 404, 且**编译门和 happy-path 浏览器门都抓不到** ——
 * 前者语法合法, 后者不会去点一个"本来就该没有的步骤"。
 * 现在直接读 `/test-executions` (与 PendingExecutionsList 同源, S2 已验证),
 * 向导的「选择测试计划」那一步随之取消。
 */

import {
  Stack,
  Paper,
  Text,
  Group,
  Badge,
  Checkbox,
  Loader,
  Center,
  Alert,
  ScrollArea,
  Button,
} from '@mantine/core'
import { parseServerDateTime } from '../../../utils/datetime'
import {
  IconAlertCircle,
  IconClock,
  IconSelectAll,
} from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import client from '../../../api/client'
import { FORMAL_EXECUTION_CHAINS } from '../types'

export interface ExecutionOption {
  id: string
  case_name: string | null
  status: string
  validation_pass: boolean | null
  execution_classification: 'formal' | 'diagnostic' | 'legacy'
  started_at?: string
  completed_at?: string
  duration_sec?: number
}

interface ExecutionsResponse {
  total: number
  items: ExecutionOption[]
}

/** 端点 limit 的硬上限 (test_execution.py: `Query(100, ge=1, le=1000)`)。 */
const FETCH_LIMIT = 1000

interface ExecutionsPage {
  items: ExecutionOption[]
  /** 库里符合条件的总数 — 与 items.length 不等即被截断。 */
  total: number
}

interface ExecutionSelectorProps {
  value: string[]
  onChange: (executionIds: string[]) => void
  disabled?: boolean
}

async function fetchExecutions(): Promise<ExecutionsPage> {
  const response = await client.get<ExecutionsResponse>('/test-executions', {
    params: {
      // ⚠️ 只列已完成执行 —— 与「待归档执行」同一约定。失败执行**进不了报告**。
      // 换源前是"该计划下的全部执行"(含 failed), 这是一处**有意收窄**:
      // 代价不对称 —— 少列 = 建不出想要的报告(可发现), 多列 = 报告里混进
      // 半截数据(不可发现)。要给失败执行留档需显式拍板后放开。
      status: 'completed',
      limit: FETCH_LIMIT,
      executed_by: FORMAL_EXECUTION_CHAINS,
    },
    // axios 默认序列化成 executed_by[]=a, FastAPI 的可重复参数收不到 →
    // 静默返回全部行。repeat 模式 = executed_by=a&executed_by=b。
    // (这个坑在 S2 是靠浏览器网络面板抓到的, 只看代码会以为收窄生效了。)
    paramsSerializer: { indexes: null },
  })
  return { items: response.data.items, total: response.data.total }
}

export function ExecutionSelector({
  value,
  onChange,
  disabled = false,
}: ExecutionSelectorProps) {
  const {
    data: page,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['report-selectable-executions'],
    queryFn: fetchExecutions,
  })

  const handleToggle = (executionId: string) => {
    if (disabled) return

    if (value.includes(executionId)) {
      onChange(value.filter((id) => id !== executionId))
    } else {
      onChange([...value, executionId])
    }
  }

  const executions = page?.items
  // ⚠️ 截断不静默 (Codex #244 C-2): 全局池会一直涨, 而端点 limit 硬上限 1000
  // 且按 executed_at 倒序 —— 超过 1000 之后**老执行永久选不到**。换源前是
  // "该计划下的全部执行"(有界), 现在是全局池(无界)。完整分页/搜索是加机制,
  // 留 backlog; 但"悄悄少列"这个性质必须去掉: 少列的代价是用户建不出想要的
  // 报告, 而他看不出为什么。
  const truncated = page ? page.total > page.items.length : false

  const handleSelectAll = () => {
    if (!executions || disabled) return

    if (value.length === executions.length) {
      onChange([])
    } else {
      onChange(executions.map((e) => e.id))
    }
  }

  const formatDuration = (seconds?: number): string => {
    if (!seconds) return '-'
    if (seconds < 60) return `${seconds}秒`
    if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
    return `${(seconds / 3600).toFixed(1)}小时`
  }

  const getStatusBadge = (
    status: string,
    pass: boolean | null,
    classification: ExecutionOption['execution_classification'],
  ) => {
    if (status === 'completed') {
      if (classification === 'diagnostic') {
        return (
          <Badge size="xs" color="yellow" variant="light">
            仅诊断
          </Badge>
        )
      }
      // ⚠️ validation_pass 是**三态** (true / false / null), 不是二值。
      // case-runner 目前一处都不写它 (全为 null), 若把 null 当 false, 挑报告
      // 数据的这一屏会显示"清一色失败" —— 跟同源的「待归档执行」列表矛盾
      // (那边刻意不画判决)。判决权在 runner, 展示层不替它拍板。
      if (pass === null || pass === undefined) {
        return (
          <Badge size="xs" color="gray" variant="light">
            未判定
          </Badge>
        )
      }
      return pass ? (
        <Badge size="xs" color="green" variant="light">
          通过
        </Badge>
      ) : (
        <Badge size="xs" color="red" variant="light">
          失败
        </Badge>
      )
    }
    if (status === 'running') {
      return (
        <Badge size="xs" color="blue" variant="light">
          执行中
        </Badge>
      )
    }
    if (status === 'pending') {
      return (
        <Badge size="xs" color="gray" variant="light">
          待执行
        </Badge>
      )
    }
    return (
      <Badge size="xs" color="gray" variant="light">
        {status}
      </Badge>
    )
  }

  if (isLoading) {
    return (
      <Center p="xl">
        <Loader size="sm" />
        <Text ml="sm" size="sm" c="dimmed">
          加载执行记录...
        </Text>
      </Center>
    )
  }

  if (error) {
    return (
      <Alert
        icon={<IconAlertCircle size={16} />}
        title="加载失败"
        color="red"
      >
        无法加载执行记录，请稍后重试
      </Alert>
    )
  }

  if (!executions || executions.length === 0) {
    return (
      <Alert
        icon={<IconAlertCircle size={16} />}
        title="暂无执行记录"
        color="yellow"
      >
库里还没有已完成的执行记录。请先在「测试管理 → 测试用例库」执行一个用例, 再回来生成报告。
      </Alert>
    )
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          共 {executions.length} 条执行记录，已选择 {value.length} 条
        </Text>
        <Button
          variant="subtle"
          size="xs"
          leftSection={<IconSelectAll size={14} />}
          onClick={handleSelectAll}
          disabled={disabled}
        >
          {value.length === executions.length ? '取消全选' : '全选'}
        </Button>
      </Group>

      {truncated && (
        <Alert icon={<IconAlertCircle size={16} />} title="列表已截断" color="yellow">
          库里共 {page?.total} 条已完成执行，此处只列出最近 {executions.length} 条。
          更早的执行暂时无法在这里选到（分页/搜索待实现）。
        </Alert>
      )}

      <ScrollArea h={300} type="auto">
        <Stack gap="xs">
          {executions.map((exec) => (
            <Paper
              key={exec.id}
              p="sm"
              withBorder
              style={{
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.6 : 1,
                backgroundColor: value.includes(exec.id)
                  ? 'var(--mantine-color-blue-light)'
                  : undefined,
              }}
              onClick={() => handleToggle(exec.id)}
            >
              <Group justify="space-between" wrap="nowrap">
                <Group gap="sm" wrap="nowrap">
                  <Checkbox
                    checked={value.includes(exec.id)}
                    onChange={() => handleToggle(exec.id)}
                    disabled={disabled}
                    styles={{
                      input: { cursor: disabled ? 'not-allowed' : 'pointer' },
                    }}
                  />
                  <Stack gap={2}>
                    <Group gap="xs">
                      <Text size="sm" fw={500}>
                        {exec.case_name || '(未命名执行)'}
                      </Text>
                      {getStatusBadge(
                        exec.status,
                        exec.validation_pass,
                        exec.execution_classification,
                      )}
                    </Group>
                    <Group gap="xs">
                      {exec.started_at && (
                        <Text size="xs" c="dimmed">
                          {parseServerDateTime(exec.started_at).toLocaleString('zh-CN')}
                        </Text>
                      )}
                    </Group>
                  </Stack>
                </Group>

                <Group gap="md">
                  <Stack gap={0} align="flex-end">
                    <Group gap={4}>
                      <IconClock size={12} />
                      <Text size="xs">{formatDuration(exec.duration_sec)}</Text>
                    </Group>
                  </Stack>
                </Group>
              </Group>
            </Paper>
          ))}
        </Stack>
      </ScrollArea>

      {value.length > 0 && (
        <Paper p="xs" withBorder bg="blue.0">
          <Text size="sm">
            已选择 {value.length} 条执行记录用于报告生成
          </Text>
        </Paper>
      )}
    </Stack>
  )
}

export default ExecutionSelector
