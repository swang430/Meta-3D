/**
 * SystemLogViewer — 系统日志查看器
 *
 * 集成到"数据归档与报告"页面，提供对后端 app.log / scpi.log 的
 * 实时查看、级别过滤、关键词搜索和文件下载功能。
 */

import { useState, useEffect, useCallback, useRef } from 'react'
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
} from '@tabler/icons-react'
import apiClient from '../../../api/client'
import { formatLogDate, formatLogTime } from '../../../utils/datetime'


// ── Types ──────────────────────────────────────────────────────

interface LogFileInfo {
  filename: string
  size_bytes: number
  size_human: string
  last_modified: string
  is_current: boolean
}

interface LogEntry {
  ts: string
  level: string
  logger: string
  hal_mode: string
  session_id: string
  instrument_id: string
  msg: string
  raw: string | null
}

// ── Constants ──────────────────────────────────────────────────

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'gray',
  INFO: 'blue',
  WARNING: 'yellow',
  ERROR: 'red',
  CRITICAL: 'grape',
  RAW: 'dark',
}

// P1-35：「仅异常」不是一个后端 level，是**几个 level 的并集**（见 fetchLogs）。
// 用哨兵值而不是字面量 'ISSUES'，免得哪天有人真加了个叫 ISSUES 的级别撞上。
const ISSUES = '__ISSUES__'
const ISSUE_LEVELS = ['WARNING', 'ERROR', 'CRITICAL'] as const

/**
 * 屏幕与「导出过滤结果」共用的**唯一**一处过滤条件构造。
 *
 * ⚠ 别在调用点各写一份。内审 F1 实证：早前这两处各有一份逐字相同的三元
 * 表达式，于是「改一处忘另一处」有两个入口 —— 而这正是 P1-34 内审 F3
 * 的母题（屏幕 5 条、导出全量）。合成一份之后，那类分叉**结构上不可能**。
 *
 * `level` 归一化尤其重要：`ISSUES` 是**前端哨兵值**，绝不能发给后端
 * （后端精确匹配 → 0 行）。
 */
function buildLogQuery(opts: {
  levelFilter: string
  keyword: string
  sessionFilter: string | null
}): Record<string, string> {
  const q: Record<string, string> = {}
  const level =
    opts.levelFilter === ISSUES
      ? ISSUE_LEVELS.join(',')
      : opts.levelFilter === 'ALL'
        ? null
        : opts.levelFilter
  if (level) q.level = level
  if (opts.keyword.trim()) q.keyword = opts.keyword.trim()
  if (opts.sessionFilter) q.session_id = opts.sessionFilter
  return q
}

const REFRESH_INTERVALS = [
  { value: '0', label: '手动' },
  { value: '5', label: '5秒' },
  { value: '10', label: '10秒' },
  { value: '30', label: '30秒' },
]

// ── Component ──────────────────────────────────────────────────

export function SystemLogViewer() {
  // File list
  const [files, setFiles] = useState<LogFileInfo[]>([])
  const [selectedFile, setSelectedFile] = useState<string>('app.log')
  const [filesLoading, setFilesLoading] = useState(false)

  // Log entries
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [totalRead, setTotalRead] = useState(0)
  const [filteredCount, setFilteredCount] = useState(0)

  // Filters
  const [levelFilter, setLevelFilter] = useState<string>('ALL')
  const [keyword, setKeyword] = useState('')
  const [maxLines] = useState(200)
  // P1-34「只看这一次请求」——把一次操作串成一条链。
  // 后端 /system-logs/tail 的 session_id 精确过滤 + 反向扫描**早就建好了**
  // （见该端点 docstring：带过滤条件时窗口是"最新 N 条匹配行"，所以链条再
  // 靠前也捞得到），只是 `session_id` 此前 100% 是 "-"，这个能力从来没能用。
  // AuditMiddleware 现在每请求写一个 id，这里把它接上。
  const [sessionFilter, setSessionFilter] = useState<string | null>(null)

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
  const isolateRequest = (sid: string) => {
    setSessionFilter(sid)
    setLevelFilter('ALL')
    setKeyword('')
  }

  // Auto-refresh
  const [refreshInterval, setRefreshInterval] = useState('0')
  const intervalRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Expanded rows
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set())

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
    setLoading(true)
    setError(null)
    try {
      // P1-35「仅异常」：后端 `level` 是**精确相等**不是门槛，所以没有任何
      // 单值能表达「WARNING 及以上」。解法是后端收**逗号集合**，一个请求
      // 搞定 —— 不做前端并流：「导出过滤结果」是下载链接、天然合不了流，
      // 前端并流会让屏幕与导出必然分叉（P1-34 内审 F3 的母题）。
      const params = {
        filename: selectedFile,
        lines: maxLines,
        ...buildLogQuery({ levelFilter, keyword, sessionFilter }),
      }

      const res = await apiClient.get('/system-logs/tail', { params })
      setEntries(res.data.entries || [])
      setTotalRead(res.data.total_lines_read || 0)
      setFilteredCount(res.data.filtered_count || 0)
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message)
      setEntries([])
    } finally {
      setLoading(false)
    }
  }, [selectedFile, levelFilter, keyword, maxLines, sessionFilter])

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
      intervalRef.current = setInterval(fetchLogs, seconds * 1000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [refreshInterval, fetchLogs])

  // ── Toggle row expand ──
  const toggleRow = (index: number) => {
    setExpandedRows(prev => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

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
          {/* Left: File selector + level filter */}
          <Group gap="sm">
            <Select
              value={selectedFile}
              onChange={(v) => v && setSelectedFile(v)}
              data={files.map(f => ({
                value: f.filename,
                label: `${f.filename} (${f.size_human})`,
              }))}
              placeholder="选择日志文件"
              w={280}
              leftSection={<IconTerminal2 size={14} />}
              disabled={filesLoading}
            />

            <SegmentedControl
              value={levelFilter}
              onChange={setLevelFilter}
              data={[
                { value: 'ALL', label: '全部' },
                // 故障分诊的默认落点：WARNING 及以上一次看全。
                // 单选 ERROR 会漏掉 WARNING，单选 WARNING 会漏掉 ERROR ——
                // 后端 level 是精确相等，没有任何单档能给出「及以上」。
                { value: ISSUES, label: '🚨 仅异常' },
                { value: 'ERROR', label: '❌ ERROR' },
                { value: 'WARNING', label: '⚠️ WARN' },
                { value: 'INFO', label: 'ℹ️ INFO' },
                { value: 'DEBUG', label: '🔍 DEBUG' },
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
                    onClick={() => setRefreshInterval(ri.value)}
                    style={ri.value === refreshInterval ? { fontWeight: 700 } : undefined}
                  >
                    {ri.label}
                  </Menu.Item>
                ))}
              </Menu.Dropdown>
            </Menu>

            <Tooltip label="手动刷新">
              <ActionIcon variant="light" onClick={fetchLogs} loading={loading}>
                <IconRefresh size={16} />
              </ActionIcon>
            </Tooltip>

            <Tooltip label="导出过滤结果">
              <ActionIcon variant="light" color="teal" onClick={() => {
                // ⚠ 导出必须跟屏幕上**同一套**过滤条件。内审 F3：加了
                // 「只看这一次请求」之后，屏幕剩 5 条、导出却是全量 ——
                // 这个分叉是本片自己造的，而后端 /export 本来就支持
                // session_id（见 api/system_logs.py 的 export_filtered_logs）。
                // ⚠ 跟屏幕**同一个**构造函数，不再各写一份 —— 那样才谈得上
                // 「导出的就是屏幕上这些」。内审 F1：两份逐字相同的三元，
                // 给「改一处忘另一处」留了两个入口。
                const params = new URLSearchParams(
                  buildLogQuery({ levelFilter, keyword, sessionFilter }),
                )
                const url = `${apiClient.defaults.baseURL}/system-logs/export/${selectedFile}?${params.toString()}`
                window.open(url, '_blank')
              }}>
                <IconDownload size={16} />
              </ActionIcon>
            </Tooltip>

            <Tooltip label="下载原始日志（全量）">
              <ActionIcon variant="light" color="blue" onClick={handleDownload}>
                <IconDownload size={16} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
      </Paper>

      {/* ── Status bar ── */}
      <Group gap="md">
        <Text size="xs" c="dimmed">
          读取 {totalRead} 行 · 匹配 {filteredCount} 条
        </Text>
        {loading && <Loader size="xs" />}
        {refreshInterval !== '0' && (
          <Badge size="sm" variant="dot" color="green">自动刷新 {refreshInterval}s</Badge>
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
                <Table.Th w={60}>模式</Table.Th>
                <Table.Th w={250}>Logger</Table.Th>
                <Table.Th>消息</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {entries.length === 0 && !loading && (
                <Table.Tr>
                  {/* 7 列：展开箭头 / 时间 / 级别 / 请求 / 模式 / Logger / 消息。
                      加「请求」列前这里写的是 5，本来就少一列。 */}
                  <Table.Td colSpan={7}>
                    <Text ta="center" c="dimmed" py="xl">
                      {error ? '加载出错' : '暂无日志条目'}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
              {entries.map((entry, idx) => (
                <Table.Tr
                  key={idx}
                  onClick={() => toggleRow(idx)}
                  style={{ cursor: 'pointer' }}
                >
                  <Table.Td>
                    {expandedRows.has(idx)
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
              ))}
            </Table.Tbody>
          </Table>

          {/* ── Expanded detail rows (rendered outside table for clean layout) ── */}
          {entries.map((entry, idx) => (
            expandedRows.has(idx) && entry.raw ? (
              <Paper key={`detail-${idx}`} p="sm" mx="md" mb="xs" bg="gray.0" radius="sm">
                <Group gap="lg" mb="xs">
                  <Text size="xs"><b>时间:</b> {formatLogDate(entry.ts)} {formatLogTime(entry.ts)}</Text>
                  <Text size="xs" c="dimmed"><b>原始:</b> {entry.ts || '—'}</Text>
                  <Text size="xs"><b>Instrument:</b> {entry.instrument_id}</Text>
                </Group>
                {/* P1-34: 一次请求内的全部日志（audit / runner / HAL / SCPI）
                    带同一个 id。点这里就把这条链单独捞出来。
                    id 为 "-" 的行不是请求产生的（启动期 / 后台任务），无链可串。 */}
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
                      return JSON.stringify(JSON.parse(entry.raw), null, 2)
                    } catch {
                      return entry.raw
                    }
                  })()}
                </Code>
              </Paper>
            ) : null
          ))}
        </ScrollArea>
      </Paper>
    </Stack>
  )
}
