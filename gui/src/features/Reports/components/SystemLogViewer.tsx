/**
 * SystemLogViewer — 系统日志查看器
 *
 * 集成到"数据归档与报告"页面，提供对后端 app.log / scpi.log 的
 * 实时查看、级别过滤、关键词搜索和文件下载功能。
 */

import { Fragment, useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  Stack,
  Group,
  Select,
  TextInput,
  Button,
  Badge,
  Paper,
  Text,
  Table,
  ScrollArea,
  ActionIcon,
  Tooltip,
  Code,
  SegmentedControl,
  Chip,
  Loader,
  Alert,
  Menu,
} from '@mantine/core'
import {
  IconSearch,
  IconRefresh,
  IconDownload,
  IconChevronDown,
  IconChevronRight,
  IconTerminal2,
  IconAlertCircle,
  IconPlayerPlay,
  IconPlayerPause,
  IconArrowUp,
} from '@tabler/icons-react'
import apiClient from '../../../api/client'
import { formatLogDate, formatLogTime } from '../../../utils/datetime'
import {
  groupLogContinuations,
  type GroupedSystemLogEntry,
} from '../../../utils/logEntries'
import {
  buildLogFileCatalog,
  type LogFileInfo,
} from '../logFileCatalog'


// ── Types ──────────────────────────────────────────────────────

// ⚠ 别在这里手写一份日志条目的形状 —— 用共享类型。
// 本文件原先有一份逐字副本，P1-36 加 `execution_id` 时它当场漂了
// （共享类型有、副本没有）。手写镜像迟早跟真值源分家，这是 P1-25
// 「手写类型审计」的同一个母题。
import type { SystemLogEntry as LogEntry } from '../../../types/api'

// ── Constants ──────────────────────────────────────────────────

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'gray',
  INFO: 'blue',
  WARNING: 'yellow',
  ERROR: 'red',
  CRITICAL: 'grape',
  RAW: 'dark',
}

// P1-35 定义的「仅异常」级别集；P2-33 起它是**多选快捷键的预设**，
// 不再对应任何哨兵值。消费时只准整体取（Array.from），不得中途切筛 ——
// `.slice(0, 1)` 会静默退化成只看 WARNING（test_p1_35 立门实证）。
const ISSUE_LEVELS = ['WARNING', 'ERROR', 'CRITICAL'] as const

// P2-33：级别过滤改**多选** —— 单选没有任何一档能表达「去掉 DEBUG 心跳但
// 保留 INFO 及以上」（实测最近 400 行里 253 行是 DEBUG 心跳）。空选 = 全部。
// 后端 `level` 收逗号集合（P1-35），一次请求即可 —— 不做前端并流（导出是
// 下载链接、天然合不了流）。⚠ 集合语义不是门槛：别改成 `>=`，
// ZoneLogsAlerts 的跨流去重依赖不同 level 的流互不相交。
const LEVEL_CHOICES: Array<{ value: string; label: string }> = [
  { value: 'DEBUG', label: '🔍 DEBUG' },
  { value: 'INFO', label: 'ℹ️ INFO' },
  { value: 'WARNING', label: '⚠️ WARN' },
  { value: 'ERROR', label: '❌ ERROR' },
  { value: 'CRITICAL', label: '🟣 CRIT' },
]

/**
 * 屏幕与「导出过滤结果」共用的**唯一**一处过滤条件构造。
 *
 * ⚠ 别在调用点各写一份。内审 F1 实证：早前这两处各有一份逐字相同的三元
 * 表达式，于是「改一处忘另一处」有两个入口 —— 而这正是 P1-34 内审 F3
 * 的母题（屏幕 5 条、导出全量）。合成一份之后，那类分叉**结构上不可能**。
 *
 * `level` 归一化只在这里发生：空选 = 全部（不发参数），
 * 非空 = 逗号集合。多选模型没有哨兵态 —— 「哨兵值漏发给后端 →
 * 精确匹配 0 行」这一类风险从源头消失（P2-33）。
 */
function buildLogQuery(opts: {
  levels: string[]
  keyword: string
  sessionFilter: string | null
  executionFilter: string | null
}): Record<string, string> {
  const q: Record<string, string> = {}
  const level = opts.levels.length > 0 ? opts.levels.join(',') : null
  if (level) q.level = level
  if (opts.keyword.trim()) q.keyword = opts.keyword.trim()
  if (opts.sessionFilter) q.session_id = opts.sessionFilter
  if (opts.executionFilter) q.execution_id = opts.executionFilter
  return q
}

const REFRESH_INTERVALS = [
  { value: '0', label: '手动' },
  { value: '5', label: '5秒' },
  { value: '10', label: '10秒' },
  { value: '30', label: '30秒' },
]

// ── Component ──────────────────────────────────────────────────

interface SystemLogViewerProps {
  /**
   * P1-39: 从执行历史「查看日志」跳过来时预填的**完整 `execution_id`**。
   * 上游 (ReportsPage) 是一次性交接：每次跳转都会先清成 null 再设新值。
   */
  initialExecutionFilter?: string | null
}

export function SystemLogViewer({ initialExecutionFilter }: SystemLogViewerProps = {}) {
  // File list
  const [files, setFiles] = useState<LogFileInfo[]>([])
  const [selectedFile, setSelectedFile] = useState<string>('app.log')
  const [filesLoading, setFilesLoading] = useState(false)
  const [logMode, setLogMode] = useState<'current' | 'history'>('current')
  const [historyKind, setHistoryKind] = useState<'category' | 'execution'>('category')
  const fileCatalog = useMemo(() => buildLogFileCatalog(files), [files])
  const selectableFiles = logMode === 'current'
    ? fileCatalog.current
    : historyKind === 'category'
      ? fileCatalog.historyCategory
      : fileCatalog.historyExecution
  const fileActionsDisabled = !selectedFile || filesLoading

  // Log entries
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [totalRead, setTotalRead] = useState(0)
  const [filteredCount, setFilteredCount] = useState(0)
  const [olderCursor, setOlderCursor] = useState<string | null>(null)
  const [hasOlder, setHasOlder] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyPages, setHistoryPages] = useState(0)
  const [sortDesc, setSortDesc] = useState(true)
  // tail / history 共用一代号。文件或过滤变化后，旧请求即使晚返回也不得
  // 覆盖新快照或把上一组条件的历史拼进来。
  const requestGenerationRef = useRef(0)
  // state 的 effect cleanup 不是同步屏障；历史模式必须另有 ref，让已经进入
  // 事件队列的 interval callback 也能在调用 fetchLogs 前立即退出。
  const historyModeRef = useRef(false)

  // Filters
  // P2-33: 级别过滤是多选集合；空数组 = 全部（见 LEVEL_CHOICES 的注释）。
  const [selectedLevels, setSelectedLevels] = useState<string[]>([])
  const [keyword, setKeyword] = useState('')
  const [maxLines] = useState(200)
  // P1-34「只看这一次请求」——把一次操作串成一条链。
  // 后端 /system-logs/tail 的 session_id 精确过滤 + 反向扫描**早就建好了**
  // （见该端点 docstring：带过滤条件时窗口是"最新 N 条匹配行"，所以链条再
  // 靠前也捞得到），只是 `session_id` 此前 100% 是 "-"，这个能力从来没能用。
  // AuditMiddleware 现在每请求写一个 id，这里把它接上。
  const [sessionFilter, setSessionFilter] = useState<string | null>(null)
  // P1-36「只看这次执行」——跟请求链并列的另一条链。
  // ⚠ 两个 id **不是**一回事：一次执行跨多个请求（发起/查询/取消各一次），
  //   也可能压根不在请求里（runner 跑在后台任务上）。所以两个过滤各自独立，
  //   可以同时生效（"这次执行里的这一个请求"）。
  // ⚠ **惰性初值, 不是挂载后再 set**（Codex #292 R3-b）——
  //   取数 effect 声明在本组件前部, 挂载时按声明顺序先跑; 若这里初值为 null、
  //   靠后面的 effect 再 setExecutionFilter, 就会**先发一个不带过滤的 /tail**,
  //   再发第二个带过滤的。两个请求乱序返回时, 未过滤的结果会盖掉已过滤的,
  //   而「只看执行 X」的徽章已经显示出来了 —— 看到的表和徽章说的不是一回事。
  const [executionFilter, setExecutionFilter] = useState<string | null>(
    initialExecutionFilter ?? null,
  )

  // P1-34 / Codex #282 R2：进入「只看这一次请求」时**清掉 level 与 keyword**。
  //
  // 不清的话后端返回的是**交集**而不是整条链：典型场景是操作员先用 ERROR
  // 过滤找到失败那行，再点这个按钮 —— 期待看到这次请求的完整上下文
  // (INFO / HAL / SCPI)，实际只看到这次请求里的 ERROR 行。按钮名叫
  // 「只看这一次请求」，给的却是「这次请求 ∩ 当前过滤」，跟本片在治的
  // 母题一模一样：看起来对，其实不是承诺的那个东西。
  //
  // 选"清掉"而不是"链条视图忽略其它过滤"：后者会让 level / keyword 控件
  // 明明显示着却不生效 —— 那是换了个地方说谎。清掉之后控件肉眼可见被重置。
  // ⚠ 两个 isolate 的策略必须**一致**（内审 F8）：都只清 level / keyword，
  //   **不清对方那条链**。早前 isolateExecution 会清掉 sessionFilter 而
  //   isolateRequest 不清 executionFilter，于是"执行 A ∩ 请求 B"这个组合
  //   只能沿一个方向到达 —— 而两个徽章都显示着，用户没法预期哪个会被清。
  //   两条链本就可以叠加（后端支持同时传），叠加时读作"这次执行里的这个请求"。
  const clearTextFilters = () => {
    setSelectedLevels([])
    setKeyword('')
  }

  const isolateExecution = (eid: string) => {
    setExecutionFilter(eid)
    clearTextFilters()
  }

  const isolateRequest = (sid: string) => {
    setSessionFilter(sid)
    clearTextFilters()
  }

  // Auto-refresh
  const [refreshInterval, setRefreshInterval] = useState('0')
  const intervalRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const stopAutoRefreshForHistory = () => {
    historyModeRef.current = true
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    setRefreshInterval('0')
  }

  const handleLogModeChange = (value: string) => {
    const nextMode = value as 'current' | 'history'
    setLogMode(nextMode)
    if (nextMode === 'history') stopAutoRefreshForHistory()
    else historyModeRef.current = false

    const nextFiles = nextMode === 'current'
      ? fileCatalog.current
      : historyKind === 'category'
        ? fileCatalog.historyCategory
        : fileCatalog.historyExecution
    setSelectedFile(nextFiles[0]?.value ?? '')
  }

  const handleHistoryKindChange = (value: string) => {
    const nextKind = value as 'category' | 'execution'
    setHistoryKind(nextKind)
    stopAutoRefreshForHistory()
    const nextFiles = nextKind === 'category'
      ? fileCatalog.historyCategory
      : fileCatalog.historyExecution
    setSelectedFile(nextFiles[0]?.value ?? '')
  }

  // Expanded rows
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

  const groupedEntries = useMemo(() => groupLogContinuations(entries), [entries])
  const keyedEntries = useMemo(() => {
    const counts = new Map<string, number>()
    const result: Array<{ entry: GroupedSystemLogEntry; key: string }> = new Array(groupedEntries.length)

    // 从最新往最旧编号：加载更早历史页只会在数组前面增加内容，现有条目 key 不漂移。
    for (let i = groupedEntries.length - 1; i >= 0; i -= 1) {
      const e = groupedEntries[i]
      const base = JSON.stringify([
        e.ts, e.level, e.logger, e.hal_mode, e.session_id,
        e.execution_id, e.instrument_id, e.msg, e.raw,
        e.continuation_lines,
      ])
      const n = counts.get(base) ?? 0
      counts.set(base, n + 1)
      result[i] = { entry: e, key: JSON.stringify([base, n]) }
    }
    return result
  }, [groupedEntries])
  const visibleEntries = sortDesc ? [...keyedEntries].reverse() : keyedEntries

  // ── Fetch file list ──
  const fetchFiles = useCallback(async () => {
    setFilesLoading(true)
    try {
      const res = await apiClient.get('/system-logs/files')
      setFiles(res.data.files || [])
    } catch (err: any) {
      console.error('Failed to load log files:', err)
    } finally {
      setFilesLoading(false)
    }
  }, [])

  // ── Fetch log entries ──
  const fetchLogs = useCallback(async () => {
    const requestGeneration = ++requestGenerationRef.current
    if (!selectedFile) {
      setLoading(false)
      setHistoryLoading(false)
      setError(null)
      setEntries([])
      setTotalRead(0)
      setFilteredCount(0)
      setOlderCursor(null)
      setHasOlder(false)
      setHistoryPages(0)
      return
    }
    historyModeRef.current = false
    setHistoryLoading(false)
    setLoading(true)
    setError(null)
    try {
      // 后端 `level` 是**精确相等**不是门槛，收逗号集合（P1-35），多选也是
      // 一个请求搞定 —— 不做前端并流：「导出过滤结果」是下载链接、天然
      // 合不了流，前端并流会让屏幕与导出必然分叉（P1-34 内审 F3 的母题）。
      const params = {
        filename: selectedFile,
        lines: maxLines,
        ...buildLogQuery({ levels: selectedLevels, keyword, sessionFilter, executionFilter }),
      }

      const res = await apiClient.get('/system-logs/tail', { params })
      if (requestGeneration !== requestGenerationRef.current) return
      setEntries(res.data.entries || [])
      setTotalRead(res.data.total_lines_read || 0)
      setFilteredCount(res.data.filtered_count || 0)
      setOlderCursor(res.data.older_cursor || null)
      setHasOlder(Boolean(res.data.has_older))
      setHistoryPages(0)
      setExpandedRows(new Set())
    } catch (err: any) {
      if (requestGeneration !== requestGenerationRef.current) return
      setError(err.response?.data?.detail || err.message)
      setEntries([])
      setOlderCursor(null)
      setHasOlder(false)
      setHistoryPages(0)
    } finally {
      if (requestGeneration === requestGenerationRef.current) setLoading(false)
    }
  }, [selectedFile, selectedLevels, keyword, maxLines, sessionFilter, executionFilter])

  // ── Explicit older page ──
  const loadOlder = useCallback(async () => {
    if (!olderCursor || historyLoading) return
    historyModeRef.current = true
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    const requestGeneration = ++requestGenerationRef.current
    const cursor = olderCursor
    // 历史快照与移动中的实时窗口不能混用；用户重新刷新或开启自动刷新时
    // 会由 fetchLogs 建立一份新的尾部快照。
    setRefreshInterval('0')
    setLoading(false)
    setHistoryLoading(true)
    setError(null)
    try {
      const params = {
        filename: selectedFile,
        lines: maxLines,
        cursor,
        ...buildLogQuery({ levels: selectedLevels, keyword, sessionFilter, executionFilter }),
      }
      const res = await apiClient.get('/system-logs/history', { params })
      if (requestGeneration !== requestGenerationRef.current) return
      const olderEntries = (res.data.entries || []) as LogEntry[]
      setEntries(current => [...olderEntries, ...current])
      setTotalRead(current => current + (res.data.total_lines_read || 0))
      setFilteredCount(current => current + (res.data.filtered_count || 0))
      setOlderCursor(res.data.older_cursor || null)
      setHasOlder(Boolean(res.data.has_older))
      setHistoryPages(current => current + 1)
    } catch (err: any) {
      if (requestGeneration !== requestGenerationRef.current) return
      setError(err.response?.data?.detail || err.message)
      if (err.response?.status === 409) {
        setOlderCursor(null)
        setHasOlder(false)
      }
    } finally {
      if (requestGeneration === requestGenerationRef.current) setHistoryLoading(false)
    }
  }, [
    olderCursor,
    historyLoading,
    selectedFile,
    maxLines,
    selectedLevels,
    keyword,
    sessionFilter,
    executionFilter,
  ])

  // ── Download ──
  const handleDownload = useCallback(() => {
    const url = `${apiClient.defaults.baseURL}/system-logs/download/${selectedFile}`
    window.open(url, '_blank')
  }, [selectedFile])

  // ── Init ──
  useEffect(() => {
    fetchFiles()
  }, [fetchFiles])

  useEffect(() => {
    if (selectableFiles.some((file) => file.value === selectedFile)) return
    setSelectedFile(selectableFiles[0]?.value ?? '')
  }, [selectableFiles, selectedFile])

  useEffect(() => {
    fetchLogs()
  }, [fetchLogs])

  // ── Auto-refresh timer ──
  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    const seconds = parseInt(refreshInterval)
    if (seconds > 0) {
      intervalRef.current = setInterval(() => {
        if (!historyModeRef.current) fetchLogs()
      }, seconds * 1000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [refreshInterval, fetchLogs])

  // ── Toggle row expand ──
  const toggleRow = (key: string) => {
    setExpandedRows(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const renderLogDetail = (entry: GroupedSystemLogEntry) => {
    const raw = entry.grouped_raw
    if (!raw) return null
    return (
      <Table.Tr>
        <Table.Td colSpan={8} p={0}>
          <Paper p="sm" m="xs" bg="gray.0" radius="sm">
            <Group gap="lg" mb="xs">
              <Text size="xs"><b>时间:</b> {formatLogDate(entry.ts)} {formatLogTime(entry.ts)}</Text>
              <Text size="xs" c="dimmed"><b>原始:</b> {entry.ts || '—'}</Text>
              <Text size="xs"><b>Instrument:</b> {entry.instrument_id}</Text>
            </Group>
            <Group gap="xs" mb="xs">
              <Text size="xs"><b>请求 ID:</b> {entry.session_id}</Text>
              {entry.session_id && entry.session_id !== '-' && (
                <Button
                  size="compact-xs"
                  variant="light"
                  color="grape"
                  onClick={() => isolateRequest(entry.session_id)}
                >
                  只看这一次请求
                </Button>
              )}
            </Group>
            <Code block style={{ fontSize: '11px', maxHeight: 200, overflow: 'auto' }}>
              {(() => {
                try {
                  return JSON.stringify(JSON.parse(raw), null, 2)
                } catch {
                  return raw
                }
              })()}
            </Code>
          </Paper>
        </Table.Td>
      </Table.Tr>
    )
  }

  // P1-39: 同一次挂载内再次跳转（换了 execution）时应用新值。
  // 首次挂载由上面的惰性初值负责, 这里只处理"值变了"。
  useEffect(() => {
    if (!initialExecutionFilter) return
    setExecutionFilter(initialExecutionFilter)
    clearTextFilters()
  }, [initialExecutionFilter])

  // ── Format timestamp for display ──
  // P1-34: 时间戳一律走共享的 formatLogTime/formatLogDate（本地时区）。
  // 原实现用正则从字符串里切时分秒，把后端给的时区偏移丢了 —— 容器跑 UTC，
  // 于是宿主机 10:58 的操作在界面上显示成 02:58。详见 utils/datetime.ts。
  // ⚠ 不在这里包一层本地别名：包了就是这个文件自己的一份，早晚跟另一个
  //   面板漂开。直接用导入的那个。

  return (
    <Stack gap="md">
      {/* ── Toolbar ── */}
      <Paper withBorder p="sm" radius="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          {/* Left: Current/history taxonomy + file selector + level filter */}
          <Group gap="sm">
            <SegmentedControl
              value={logMode}
              onChange={handleLogModeChange}
              data={[
                { value: 'current', label: '当前日志' },
                { value: 'history', label: '历史日志' },
              ]}
              size="xs"
            />

            {logMode === 'history' && (
              <SegmentedControl
                value={historyKind}
                onChange={handleHistoryKindChange}
                data={[
                  { value: 'category', label: '分类日志' },
                  { value: 'execution', label: '执行日志' },
                ]}
                size="xs"
              />
            )}

            <Select
              value={selectedFile}
              onChange={(v) => v && setSelectedFile(v)}
              data={selectableFiles}
              placeholder={logMode === 'current' ? '选择当前日志' : '按时间或名称搜索历史日志'}
              searchable
              nothingFoundMessage="没有匹配的日志文件"
              w={420}
              leftSection={<IconTerminal2 size={14} />}
              disabled={filesLoading}
            />

            {/* P2-33: 级别过滤是多选 —— 单选没有任何一档能表达「去掉 DEBUG
                心跳但保留 INFO 及以上」。空选 = 全部；「仅异常」是一键预设
                （WARNING/ERROR/CRITICAL 全选），不再是独立档位。 */}
            <Chip.Group multiple value={selectedLevels} onChange={setSelectedLevels}>
              <Group gap={4} wrap="nowrap">
                {LEVEL_CHOICES.map((f) => (
                  <Chip
                    key={f.value}
                    value={f.value}
                    size="xs"
                    color={LEVEL_COLORS[f.value] || 'gray'}
                  >
                    {f.label}
                  </Chip>
                ))}
              </Group>
            </Chip.Group>
            <Button
              size="compact-xs"
              variant="light"
              color="orange"
              onClick={() => setSelectedLevels(Array.from(ISSUE_LEVELS))}
            >
              🚨 仅异常
            </Button>
            <Button
              size="compact-xs"
              variant="subtle"
              disabled={selectedLevels.length === 0}
              onClick={() => setSelectedLevels([])}
            >
              全部
            </Button>

            <SegmentedControl
              value={sortDesc ? 'desc' : 'asc'}
              onChange={(value) => setSortDesc(value === 'desc')}
              data={[
                { value: 'desc', label: '最新在上' },
                { value: 'asc', label: '最旧在上' },
              ]}
              size="xs"
            />
          </Group>

          {/* Right: Search + actions */}
          <Group gap="sm">
            <TextInput
              value={keyword}
              onChange={(e) => setKeyword(e.currentTarget.value)}
              placeholder="搜索日志内容..."
              leftSection={<IconSearch size={14} />}
              w={200}
              size="sm"
            />

            <Menu shadow="md" width={140}>
              <Menu.Target>
                <Button
                  variant="light"
                  size="sm"
                  disabled={logMode === 'history'}
                  leftSection={
                    refreshInterval !== '0'
                      ? <IconPlayerPlay size={14} />
                      : <IconPlayerPause size={14} />
                  }
                >
                  {refreshInterval === '0' ? '自动刷新' : `${refreshInterval}s`}
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                {REFRESH_INTERVALS.map(ri => (
                  <Menu.Item
                    key={ri.value}
                    onClick={() => {
                      const wasHistorySnapshot = historyModeRef.current
                      if (ri.value !== '0') historyModeRef.current = false
                      setRefreshInterval(ri.value)
                      // 从冻结历史回实时模式时立即重建尾部，不保留有缺口风险的拼接页。
                      if (ri.value !== '0' && (wasHistorySnapshot || historyPages > 0)) fetchLogs()
                    }}
                    style={ri.value === refreshInterval ? { fontWeight: 700 } : undefined}
                  >
                    {ri.label}
                  </Menu.Item>
                ))}
              </Menu.Dropdown>
            </Menu>

            <Tooltip label="手动刷新">
              <ActionIcon
                variant="light"
                onClick={fetchLogs}
                loading={loading}
                disabled={fileActionsDisabled}
              >
                <IconRefresh size={16} />
              </ActionIcon>
            </Tooltip>

            <Tooltip label="导出过滤结果">
              <ActionIcon
                disabled={fileActionsDisabled}
                variant="light"
                color="teal"
                onClick={() => {
                // ⚠ 导出必须跟屏幕上**同一套**过滤条件。内审 F3：加了
                // 「只看这一次请求」之后，屏幕剩 5 条、导出却是全量 ——
                // 这个分叉是本片自己造的，而后端 /export 本来就支持
                // session_id（见 api/system_logs.py 的 export_filtered_logs）。
                // ⚠ 跟屏幕**同一个**构造函数，不再各写一份 —— 那样才谈得上
                // 「导出的就是屏幕上这些」。内审 F1：两份逐字相同的三元，
                // 给「改一处忘另一处」留了两个入口。
                const params = new URLSearchParams(
                  buildLogQuery({ levels: selectedLevels, keyword, sessionFilter, executionFilter }),
                )
                const url = `${apiClient.defaults.baseURL}/system-logs/export/${selectedFile}?${params.toString()}`
                window.open(url, '_blank')
                }}
              >
                <IconDownload size={16} />
              </ActionIcon>
            </Tooltip>

            <Tooltip label="下载原始日志（全量）">
              <ActionIcon
                disabled={fileActionsDisabled}
                variant="light"
                color="blue"
                onClick={handleDownload}
              >
                <IconDownload size={16} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
      </Paper>

      {/* ── Status bar ── */}
      <Group gap="md">
        <Text size="xs" c="dimmed">
          扫描 {totalRead} 行 · 当前显示 {filteredCount} 条
        </Text>
        {loading && <Loader size="xs" />}
        {refreshInterval !== '0' && (
          <Badge size="sm" variant="dot" color="green">自动刷新 {refreshInterval}s</Badge>
        )}
        {logMode === 'history' && (
          <Badge size="sm" variant="light" color="gray">历史文件 · 自动刷新已关闭</Badge>
        )}
        {historyPages > 0 && (
          <Badge size="sm" variant="light" color="cyan">
            历史快照 · 已加载 {historyPages} 页
          </Badge>
        )}
        {/* P1-34: 当前是否只看某一次请求 —— 过滤态必须**看得见**，
            否则"怎么只有几条"会被当成日志丢了。 */}
        {sessionFilter && (
          <Badge
            size="sm"
            color="grape"
            variant="filled"
            rightSection={
              <ActionIcon
                size="xs"
                variant="transparent"
                color="white"
                aria-label="取消只看这一次请求"
                onClick={() => setSessionFilter(null)}
              >
                ✕
              </ActionIcon>
            }
          >
            只看请求 {sessionFilter}
          </Badge>
        )}
        {executionFilter && (
          <Badge
            size="sm"
            color="indigo"
            variant="filled"
            rightSection={
              <ActionIcon
                size="xs"
                variant="transparent"
                color="white"
                aria-label="取消只看这次执行"
                onClick={() => setExecutionFilter(null)}
              >
                ✕
              </ActionIcon>
            }
          >
            只看执行 {executionFilter.slice(0, 8)}
          </Badge>
        )}
        {hasOlder && olderCursor ? (
          <Button
            size="compact-xs"
            variant="light"
            leftSection={<IconArrowUp size={13} />}
            loading={historyLoading}
            disabled={loading}
            onClick={loadOlder}
          >
            加载更早 {maxLines} 条
          </Button>
        ) : historyPages > 0 ? (
          <Text size="xs" c="dimmed">已到当前文件开头</Text>
        ) : null}
      </Group>

      {/* ── Error ── */}
      {error && (
        <Alert color="red" icon={<IconAlertCircle size={16} />} title="加载失败">
          {error}
        </Alert>
      )}

      {/* ── Log table ── */}
      <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
        <ScrollArea h={550} type="auto">
          <Table
            striped
            highlightOnHover
            withTableBorder={false}
            style={{ fontFamily: 'var(--mantine-font-family-monospace, monospace)', fontSize: '12px' }}
          >
            <Table.Thead style={{ position: 'sticky', top: 0, backgroundColor: 'var(--mantine-color-body)', zIndex: 1 }}>
              <Table.Tr>
                <Table.Th w={30}></Table.Th>
                <Table.Th w={100}>时间</Table.Th>
                <Table.Th w={70}>级别</Table.Th>
                {/* P1-34: 请求 ID 必须**在表格里直接看得见**。
                    早前它只在展开详情里 —— 于是这个功能等于不存在：
                    用户反馈原话「没看到 request_id 真的落进日志了」，
                    而实测那 200 行里 47% 是带 id 的。
                    做了但看不见 = 没做。 */}
                <Table.Th w={86}>请求</Table.Th>
                {/* P1-36：执行链跟请求链并排 —— 一次执行跨多个请求，
                    两列同时可见才看得出"这次执行里的这一个请求"。 */}
                <Table.Th w={86}>执行</Table.Th>
                <Table.Th w={60}>模式</Table.Th>
                <Table.Th w={250}>Logger</Table.Th>
                <Table.Th>消息</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {entries.length === 0 && !loading && (
                <Table.Tr>
                  {/* 8 列：展开箭头 / 时间 / 级别 / 请求 / 执行 / 模式 / Logger / 消息。
                      加「请求」「执行」两列前这里写的是 5，本来就少一列。 */}
                  <Table.Td colSpan={8}>
                    <Text ta="center" c="dimmed" py="xl">
                      {error ? '加载出错' : (
                        executionFilter ? (
                          /* 日志按天轮转。P1-43 已把归档文件放进下拉，但仍需明确
                             提示用户切换文件，否则空结果会被误认为链路日志丢失。 */
                          <>
                            这次执行在 <b>{selectedFile}</b> 里没有匹配行。
                            <br />
                            日志按天轮转 —— 若该执行不在当前文件，请在文件下拉中
                            选择发生日期对应的 <b>app.log.YYYY-MM-DD</b> 归档文件。
                          </>
                        ) : '暂无日志条目'
                      )}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
              {visibleEntries.map(({ entry, key }) => (
                <Fragment key={key}>
                  <Table.Tr
                    onClick={() => toggleRow(key)}
                    style={{ cursor: 'pointer' }}
                  >
                  <Table.Td>
                    {expandedRows.has(key)
                      ? <IconChevronDown size={12} />
                      : <IconChevronRight size={12} />
                    }
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed">{formatLogTime(entry.ts)}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      size="xs"
                      color={LEVEL_COLORS[entry.level] || 'gray'}
                      variant={entry.level === 'ERROR' ? 'filled' : 'light'}
                    >
                      {entry.level}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    {/* 点这里直接隔离该请求，不必先展开。id 为 '-' 的行不是
                        请求产生的（启动期 / 后台心跳），如实显示 '—' 不可点。 */}
                    {entry.session_id && entry.session_id !== '-' ? (
                      <Tooltip label={`只看请求 ${entry.session_id}`} withArrow>
                        <Code
                          style={{ cursor: 'pointer', fontSize: '11px' }}
                          c="grape"
                          onClick={(e) => {
                            e.stopPropagation()   // 别顺手把这一行展开了
                            isolateRequest(entry.session_id)
                          }}
                        >
                          {entry.session_id.slice(0, 8)}
                        </Code>
                      </Tooltip>
                    ) : (
                      <Text size="xs" c="dimmed">—</Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    {entry.execution_id && entry.execution_id !== '-' ? (
                      <Tooltip label={`只看执行 ${entry.execution_id}`} withArrow>
                        <Code
                          style={{ cursor: 'pointer', fontSize: '11px' }}
                          c="indigo"
                          onClick={(e) => {
                            e.stopPropagation()
                            isolateExecution(entry.execution_id)
                          }}
                        >
                          {entry.execution_id.slice(0, 8)}
                        </Code>
                      </Tooltip>
                    ) : (
                      <Text size="xs" c="dimmed">—</Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Badge
                      size="xs"
                      color={entry.hal_mode === 'real' ? 'teal' : entry.hal_mode === 'mock' ? 'blue' : 'gray'}
                      variant="dot"
                    >
                      {entry.hal_mode === '-' ? '-' : entry.hal_mode.toUpperCase()}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed">
                      {entry.logger}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" style={{ wordBreak: 'break-all', whiteSpace: 'pre-wrap' }}>
                      {entry.msg}
                    </Text>
                  </Table.Td>
                  </Table.Tr>
                  {expandedRows.has(key) && renderLogDetail(entry)}
                </Fragment>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Paper>
    </Stack>
  )
}
