/**
 * P2-8 ④ 实时日志 + 紧凑告警计数 — bottom wide bar.
 *
 * 左 日志: GET /system-logs/tail — level 多选过滤 (INFO/WARN/ERROR/CRITICAL, P2-33 补 CRITICAL) +
 *   关键字搜索 + 自动滚动开关 + filename 下拉. Polls ~3s (pausable via
 *   自动刷新 toggle) + 手动刷新按钮.
 * 告警计数: GET /dashboard/alerts/summary 放在日志标题栏. Polls ~10s.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Card,
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
import { fetchSystemLogsTail, fetchAlertSummary } from '../../api/service'
import { formatLogTime } from '../../utils/datetime'
import { filterGroupedLogEntries } from '../../utils/logEntries'
import type { SystemLogTailResponse } from '../../types/api'
import type { SystemLogEntry, SystemLogLevel } from '../../types/api'

// ── 日志级别 → 颜色 ──
const LOG_LEVEL_COLOR: Record<string, string> = {
  CRITICAL: 'grape',
  ERROR: 'red',
  WARNING: 'yellow',
  INFO: 'blue',
  DEBUG: 'gray',
  RAW: 'gray',
}

// 级别多选过滤选项. backend uses WARNING (not WARN); map the chip token.
// P2-33: CRITICAL 补上 —— 此前这里没有它的开关, CRITICAL 行被下方的
// 客户端过滤恒滤掉 (P1-35 内审 F8「两个面板对异常有两个定义」)。
const LEVEL_FILTERS: Array<{ value: string; label: string }> = [
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARN' },
  { value: 'ERROR', label: 'ERROR' },
  { value: 'CRITICAL', label: 'CRIT' },
]

const LOG_FILES = ['app.log', 'scpi.log', 'channel_engine.log', 'calibration.log', 'audit.log']

function logLevelColor(level: SystemLogLevel): string {
  return LOG_LEVEL_COLOR[level.toUpperCase()] ?? 'gray'
}

function AlertSummaryBadge() {
  const summaryQuery = useQuery({
    queryKey: ['cockpit', 'alert-summary'],
    queryFn: fetchAlertSummary,
    refetchInterval: 10_000,
  })

  if (summaryQuery.isLoading) {
    return (
      <Tooltip label="活动告警计数读取中">
        <Loader size="xs" />
      </Tooltip>
    )
  }

  if (summaryQuery.error || !summaryQuery.data) {
    return (
      <Badge size="sm" color="red" variant="light">
        告警计数不可用
      </Badge>
    )
  }

  const summary = summaryQuery.data
  const knownTotal = summary.critical_count
    + summary.error_count
    + summary.warning_count
    + summary.info_count
  if (knownTotal !== summary.total_active) {
    return (
      <Badge size="sm" color="red" variant="filled">
        告警计数不一致
      </Badge>
    )
  }

  if (summary.total_active === 0) {
    return (
      <Badge size="sm" color="green" variant="light">
        无活动告警
      </Badge>
    )
  }

  const color = summary.critical_count > 0 || summary.error_count > 0
    ? 'red'
    : summary.warning_count > 0
      ? 'yellow'
      : 'blue'

  return (
    <Tooltip
      multiline
      label={(
        <Stack gap={0}>
          <Text size="xs">严重 {summary.critical_count}</Text>
          <Text size="xs">错误 {summary.error_count}</Text>
          <Text size="xs">警告 {summary.warning_count}</Text>
          <Text size="xs">信息 {summary.info_count}</Text>
        </Stack>
      )}
    >
      <Badge
        size="sm"
        color={color}
        variant="light"
        leftSection={<IconBellRinging size={12} />}
      >
        活动告警 {summary.total_active}
      </Badge>
    </Tooltip>
  )
}

function LogPanel() {
  const [enabledLevels, setEnabledLevels] = useState<string[]>(['INFO', 'WARNING', 'ERROR', 'CRITICAL'])
  const [keyword, setKeyword] = useState('')
  const [filename, setFilename] = useState<string>('app.log')
  const [autoScroll, setAutoScroll] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [sortDesc, setSortDesc] = useState(true)
  const viewportRef = useRef<HTMLDivElement>(null)

  // P2-19: 主流 (无过滤 200 行, 保 RAW/traceback 与最新行邻接) +
  // WARN/ERROR/CRIT 各一路下推补充流 — 低频失败行有独立的 200 条窗口,
  // 不再被 INFO 刷屏 ~48s 冲出 (P2-11 失效模式的收尾)。INFO 是刷屏主体不补;
  // RAW 行无 ts 且后端 level 精确匹配会丢它, 只在主流里保邻接, 补充流的
  // 旧行无 traceback 可接受 (行本身可见已达排障目的)。
  // P2-33: CRITICAL 与 WARNING/ERROR 同为低频异常, 补第三路 —— 只加 chip
  // 不加 boost 的话, 刷屏时 CRITICAL 仍会被冲出主流窗口。三路集合与
  // SystemLogViewer 的 ISSUE_LEVELS 保持相等 (test_p2_33 不变量门)。
  const levelsKey = [...enabledLevels].sort().join(',')
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['cockpit', 'logs', filename, levelsKey, keyword],
    queryFn: async () => {
      const main = await fetchSystemLogsTail({
        filename,
        lines: 200,
        keyword: keyword || undefined,
      })
      const boosts = ['WARNING', 'ERROR', 'CRITICAL'].filter((l) => enabledLevels.includes(l))
      // 补充流失败不连坐主流 (内审 F5): 单路 500 降级为无补充
      const settled = await Promise.allSettled(
        boosts.map((l) =>
          fetchSystemLogsTail({
            filename,
            lines: 200,
            level: l,
            keyword: keyword || undefined,
          }),
        ),
      )
      const extra = settled
        .filter((r): r is PromiseFulfilledResult<SystemLogTailResponse> => r.status === 'fulfilled')
        .map((r) => r.value)
      const key = (e: SystemLogEntry) => `${e.ts}|${e.logger}|${e.msg}`
      // 只做跨流去重 (内审 F4): boost 三流 (WARNING/ERROR/CRITICAL) 按 level 天然不相交, 流内重复必是
      // 真实重复行, 不互相吞
      const seen = new Set(main.entries.map(key))
      // cutoff 取主流首条带 ts 的行 (Codex #258: 窗口首行可能是 RAW 连续行
      // ts 为空, 会让间隙护栏失效)
      const mainOldestTs = main.entries.find((e) => e.ts)?.ts ?? ''
      const older: SystemLogEntry[] = []
      for (const r of extra) {
        for (const e of r.entries) {
          // 两次请求间隙新落盘的行只在补充流出现 (内审 F3): ts 不早于主流
          // 最旧行的丢弃, 下一轮主流必含它, 不错位到面板顶端
          if (mainOldestTs && e.ts >= mainOldestTs) continue
          if (!seen.has(key(e))) older.push(e)
        }
      }
      // 补充的旧行按时间升序放在主流前面 (老→新, 滚动方向一致)
      older.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0))
      const totalScanned = Math.max(
        main.total_lines_read || 0,
        ...extra.map((r) => r.total_lines_read || 0),
        0,
      )
      return { entries: [...older, ...main.entries], total_scanned: totalScanned }
    },
    refetchInterval: autoRefresh ? 3_000 : false,
  })

  const groupedEntries = useMemo(
    () => filterGroupedLogEntries(data?.entries ?? [], (entry) => (
      enabledLevels.length > 0 && enabledLevels.includes(entry.level.toUpperCase())
    )),
    [data, enabledLevels],
  )
  const entries = sortDesc ? [...groupedEntries].reverse() : groupedEntries

  useEffect(() => {
    if (autoScroll && viewportRef.current) {
      viewportRef.current.scrollTo({ top: sortDesc ? 0 : viewportRef.current.scrollHeight })
    }
  }, [entries, autoScroll, sortDesc])

  return (
    <Card withBorder radius="md" padding="md" h="100%">
      <Stack gap="sm" h="100%">
        <Group justify="space-between">
          <Group gap="xs">
            <IconTerminal2 size={18} />
            <Text fw={700}>实时日志</Text>
            <AlertSummaryBadge />
            {data && (
              <Badge size="sm" variant="light" color="gray">
                {entries.length} 条 · 最深已扫 {data.total_scanned} 行
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
            <Switch
              size="xs"
              label="最新在上"
              checked={sortDesc}
              onChange={(e) => setSortDesc(e.currentTarget.checked)}
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
            placeholder="搜索 msg / logger / traceback"
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
                    {/* P1-34: 本地时区。原写法 split('T')[1].slice(0,8) 丢掉了
                        后端给的时区偏移（容器 UTC），显示比手表慢 8 小时。
                        侧栏窄，不带毫秒；查看器那侧带。 */}
                    {formatLogTime(e.ts, { millis: false })}
                  </Text>
                  <Badge size="xs" color={logLevelColor(e.level)} variant="light" w={64}>
                    {e.level}
                  </Badge>
                  <Code style={{ flex: 1, background: 'transparent', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {e.logger && e.logger !== '' ? `[${e.logger}] ` : ''}
                    {[e.msg, ...e.continuation_lines].filter(Boolean).join('\n')}
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

export function ZoneLogsAlerts() {
  return <LogPanel />
}
