/**
 * P2-8 ④ 实时日志 + 告警 — bottom wide bar, split left / right.
 *
 * 左 日志: GET /system-logs/tail — level 多选过滤 (INFO/WARN/ERROR) +
 *   关键字搜索 + 自动滚动开关 + filename 下拉. Polls ~3s (pausable via
 *   自动刷新 toggle) + 手动刷新按钮.
 * 右 告警: GET /dashboard/alerts (按 severity 颜色排) + /alerts/summary
 *   做顶部计数. Polls ~10s.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Card,
  Grid,
  Group,
  Stack,
  Text,
  Badge,
  Loader,
  Alert,
  ScrollArea,
  TextInput,
  Select,
  Switch,
  ActionIcon,
  Tooltip,
  Chip,
  Code,
} from '@mantine/core'
import {
  IconRefresh,
  IconTerminal2,
  IconBellRinging,
  IconSearch,
} from '@tabler/icons-react'
import { fetchSystemLogsTail, fetchAlerts, fetchAlertSummary } from '../../api/service'
import type {
  SystemLogEntry,
  SystemLogLevel,
  DashboardAlert,
  DashboardAlertSeverity,
} from '../../types/api'

// ── 日志级别 → 颜色 ──
const LOG_LEVEL_COLOR: Record<string, string> = {
  ERROR: 'red',
  WARNING: 'yellow',
  INFO: 'blue',
  DEBUG: 'gray',
  RAW: 'gray',
}

// 级别多选过滤选项. backend uses WARNING (not WARN); map the chip token.
const LEVEL_FILTERS: Array<{ value: string; label: string }> = [
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARN' },
  { value: 'ERROR', label: 'ERROR' },
]

const LOG_FILES = ['app.log', 'scpi.log', 'channel_engine.log', 'calibration.log', 'audit.log']

function logLevelColor(level: SystemLogLevel): string {
  return LOG_LEVEL_COLOR[level.toUpperCase()] ?? 'gray'
}

// ── 告警 severity → 颜色 / 排序权重 ──
const ALERT_SEVERITY_COLOR: Record<string, string> = {
  critical: 'red',
  error: 'red',
  warning: 'yellow',
  info: 'blue',
}

const SEVERITY_RANK: Record<string, number> = {
  critical: 0,
  error: 1,
  warning: 2,
  info: 3,
}

function alertColor(severity: DashboardAlertSeverity): string {
  return ALERT_SEVERITY_COLOR[severity] ?? 'gray'
}

function LogPanel() {
  const [enabledLevels, setEnabledLevels] = useState<string[]>(['INFO', 'WARNING', 'ERROR'])
  const [keyword, setKeyword] = useState('')
  const [filename, setFilename] = useState<string>('app.log')
  const [autoScroll, setAutoScroll] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const viewportRef = useRef<HTMLDivElement>(null)

  // 单 level 才下推后端 (后端 tail 只接受单个 level)；多选时拉全量本地过滤。
  const serverLevel = enabledLevels.length === 1 ? enabledLevels[0] : undefined

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['cockpit', 'logs', filename, serverLevel, keyword],
    queryFn: () =>
      fetchSystemLogsTail({
        filename,
        lines: 200,
        level: serverLevel,
        keyword: keyword || undefined,
      }),
    refetchInterval: autoRefresh ? 3_000 : false,
  })

  // 客户端过滤兜底 (多选 level 时后端没法只过滤一个)。
  const entries = useMemo<SystemLogEntry[]>(() => {
    const all = data?.entries ?? []
    if (enabledLevels.length === 0) return []
    return all.filter((e) => {
      const up = e.level.toUpperCase()
      // RAW continuation lines follow whatever line preceded them — keep
      // them visible whenever any level is enabled so tracebacks aren't lost.
      if (up === 'RAW') return true
      return enabledLevels.includes(up)
    })
  }, [data, enabledLevels])

  useEffect(() => {
    if (autoScroll && viewportRef.current) {
      viewportRef.current.scrollTo({ top: viewportRef.current.scrollHeight })
    }
  }, [entries, autoScroll])

  return (
    <Card withBorder radius="md" padding="md" h="100%">
      <Stack gap="sm" h="100%">
        <Group justify="space-between">
          <Group gap="xs">
            <IconTerminal2 size={18} />
            <Text fw={700}>实时日志</Text>
            {data && (
              <Badge size="sm" variant="light" color="gray">
                {entries.length} 条
              </Badge>
            )}
          </Group>
          <Group gap="xs">
            <Switch
              size="xs"
              label="自动滚动"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.currentTarget.checked)}
            />
            <Switch
              size="xs"
              label="自动刷新"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.currentTarget.checked)}
            />
            <Tooltip label="手动刷新">
              <ActionIcon variant="subtle" onClick={() => refetch()} loading={isFetching}>
                <IconRefresh size={16} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>

        <Group gap="xs" wrap="wrap">
          <Select
            size="xs"
            w={170}
            data={LOG_FILES}
            value={filename}
            onChange={(v) => v && setFilename(v)}
            aria-label="日志文件"
          />
          <Chip.Group multiple value={enabledLevels} onChange={setEnabledLevels}>
            <Group gap={4}>
              {LEVEL_FILTERS.map((f) => (
                <Chip key={f.value} value={f.value} size="xs" color={logLevelColor(f.value)}>
                  {f.label}
                </Chip>
              ))}
            </Group>
          </Chip.Group>
          <TextInput
            size="xs"
            placeholder="搜索 msg / logger"
            leftSection={<IconSearch size={14} />}
            value={keyword}
            onChange={(e) => setKeyword(e.currentTarget.value)}
            style={{ flex: 1, minWidth: 140 }}
          />
        </Group>

        {error && (
          <Alert color="red" variant="light" title="日志读取失败">
            {(error as Error).message}
          </Alert>
        )}

        <ScrollArea h={280} viewportRef={viewportRef} type="auto">
          {isLoading ? (
            <Group gap="xs" p="sm">
              <Loader size="sm" />
              <Text size="sm" c="dimmed">
                日志读取中……
              </Text>
            </Group>
          ) : entries.length === 0 ? (
            <Text size="sm" c="dimmed" p="sm">
              无匹配日志
            </Text>
          ) : (
            <Stack gap={2} p={4}>
              {entries.map((e, i) => (
                <Group key={`${e.ts}-${i}`} gap="xs" wrap="nowrap" align="flex-start">
                  <Text size="xs" c="dimmed" style={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                    {e.ts ? e.ts.split('T')[1]?.slice(0, 8) ?? e.ts : '—'}
                  </Text>
                  <Badge size="xs" color={logLevelColor(e.level)} variant="light" w={64}>
                    {e.level}
                  </Badge>
                  <Code style={{ flex: 1, background: 'transparent', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {e.logger && e.logger !== '' ? `[${e.logger}] ` : ''}
                    {e.msg}
                  </Code>
                </Group>
              ))}
            </Stack>
          )}
        </ScrollArea>
      </Stack>
    </Card>
  )
}

function AlertPanel() {
  const summaryQuery = useQuery({
    queryKey: ['cockpit', 'alert-summary'],
    queryFn: fetchAlertSummary,
    refetchInterval: 10_000,
  })
  const alertsQuery = useQuery({
    queryKey: ['cockpit', 'alerts'],
    queryFn: () => fetchAlerts({ status: 'active', limit: 20 }),
    refetchInterval: 10_000,
  })

  const summary = summaryQuery.data
  const alerts = useMemo<DashboardAlert[]>(() => {
    const list = alertsQuery.data?.alerts ?? []
    // 按 severity 排 (critical 最前)，同级按 created_at 倒序。
    return [...list].sort((a, b) => {
      const rA = SEVERITY_RANK[a.severity] ?? 99
      const rB = SEVERITY_RANK[b.severity] ?? 99
      if (rA !== rB) return rA - rB
      return b.created_at.localeCompare(a.created_at)
    })
  }, [alertsQuery.data])

  return (
    <Card withBorder radius="md" padding="md" h="100%">
      <Stack gap="sm" h="100%">
        <Group justify="space-between">
          <Group gap="xs">
            <IconBellRinging size={18} />
            <Text fw={700}>活动告警</Text>
          </Group>
          {summary && (
            <Group gap={6}>
              {summary.critical_count > 0 && (
                <Badge size="sm" color="red" variant="filled">
                  严重 {summary.critical_count}
                </Badge>
              )}
              {summary.error_count > 0 && (
                <Badge size="sm" color="red" variant="light">
                  错误 {summary.error_count}
                </Badge>
              )}
              {summary.warning_count > 0 && (
                <Badge size="sm" color="yellow" variant="light">
                  警告 {summary.warning_count}
                </Badge>
              )}
              {summary.info_count > 0 && (
                <Badge size="sm" color="blue" variant="light">
                  信息 {summary.info_count}
                </Badge>
              )}
              {summary.total_active === 0 && (
                <Badge size="sm" color="green" variant="light">
                  无活动告警
                </Badge>
              )}
            </Group>
          )}
        </Group>

        {alertsQuery.error && (
          <Alert color="red" variant="light" title="告警读取失败">
            {(alertsQuery.error as Error).message}
          </Alert>
        )}

        <ScrollArea h={280} type="auto">
          {alertsQuery.isLoading ? (
            <Group gap="xs" p="sm">
              <Loader size="sm" />
              <Text size="sm" c="dimmed">
                告警读取中……
              </Text>
            </Group>
          ) : alerts.length === 0 ? (
            <Stack gap={4} p="sm" align="center">
              <Text fw={600}>暂无活动告警</Text>
              <Text size="sm" c="dimmed">
                系统运行正常
              </Text>
            </Stack>
          ) : (
            <Stack gap="xs" p={4}>
              {alerts.map((a) => (
                <Card key={a.id} withBorder radius="sm" padding="xs">
                  <Group justify="space-between" align="flex-start" wrap="nowrap">
                    <Stack gap={2} style={{ flex: 1 }}>
                      <Text fw={600} size="sm" lineClamp={1} title={a.title}>
                        {a.title}
                      </Text>
                      {a.message && (
                        <Text size="xs" c="dimmed" lineClamp={2} title={a.message}>
                          {a.message}
                        </Text>
                      )}
                      <Text size="xs" c="dimmed">
                        #{a.id} · {new Date(a.created_at).toLocaleString('zh-CN', { hour12: false })}
                      </Text>
                    </Stack>
                    <Badge color={alertColor(a.severity)} variant="light">
                      {a.severity.toUpperCase()}
                    </Badge>
                  </Group>
                </Card>
              ))}
            </Stack>
          )}
        </ScrollArea>
      </Stack>
    </Card>
  )
}

export function ZoneLogsAlerts() {
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, lg: 7 }}>
        <LogPanel />
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 5 }}>
        <AlertPanel />
      </Grid.Col>
    </Grid>
  )
}
