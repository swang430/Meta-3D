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
      const params: Record<string, any> = {
        filename: selectedFile,
        lines: maxLines,
      }
      if (levelFilter !== 'ALL') {
        params.level = levelFilter
      }
      if (keyword.trim()) {
        params.keyword = keyword.trim()
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
  }, [selectedFile, levelFilter, keyword, maxLines])

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
  const formatTs = (ts: string) => {
    if (!ts) return '—'
    // "2026-04-22T16:00:00.716Z" → "16:00:00.716"
    const match = ts.match(/T(\d{2}:\d{2}:\d{2}\.\d{3})/)
    return match ? match[1] : ts
  }

  const formatDate = (ts: string) => {
    if (!ts) return ''
    const match = ts.match(/^(\d{4}-\d{2}-\d{2})/)
    return match ? match[1] : ''
  }

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

            <Tooltip label="下载原始日志">
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
                <Table.Th w={250}>Logger</Table.Th>
                <Table.Th>消息</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {entries.length === 0 && !loading && (
                <Table.Tr>
                  <Table.Td colSpan={5}>
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
                    <Text size="xs" c="dimmed">{formatTs(entry.ts)}</Text>
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
                    <Text size="xs" c="dimmed" truncate="end" maw={240}>
                      {entry.logger}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" truncate="end" maw={500}>
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
                  <Text size="xs"><b>时间:</b> {entry.ts}</Text>
                  <Text size="xs"><b>Session:</b> {entry.session_id}</Text>
                  <Text size="xs"><b>Instrument:</b> {entry.instrument_id}</Text>
                  <Text size="xs"><b>日期:</b> {formatDate(entry.ts)}</Text>
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
