/**
 * Report List Component
 *
 * Displays a list of generated reports with download and management options
 */

import { useState } from 'react'
import {
  Card,
  Table,
  Badge,
  Button,
  Group,
  Text,
  Stack,
  Select,
  TextInput,
  ActionIcon,
  Tooltip,
  Progress,
} from '@mantine/core'
import {
  IconDownload,
  IconEye,
  IconTrash,
  IconRefresh,
  IconSearch,
  IconFileTypePdf,
  IconFileTypeHtml,
  IconTable,
} from '@tabler/icons-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { ReportsAPI } from '../index'
import type { ReportSummary, ReportStatus, ReportFormat } from '../types'

interface ReportListProps {
  onView?: (reportId: string) => void
  onDownload?: (reportId: string) => void
  onDelete?: (reportId: string) => void
}

export function ReportList({ onView, onDownload, onDelete }: ReportListProps) {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<ReportStatus | ''>('')
  const [formatFilter, setFormatFilter] = useState<ReportFormat | ''>('')

  // Fetch reports
  const { data: reportsData, isLoading, refetch } = useQuery({
    queryKey: ['reports', statusFilter],
    queryFn: () =>
      ReportsAPI.listReports({
        status: statusFilter || undefined,
      }),
    refetchInterval: (query) => {
      // Auto-refresh if any reports are generating
      const hasGenerating = query.state.data?.reports.some(
        (r) => r.status === 'generating',
      )
      return hasGenerating ? 3000 : false
    },
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: ReportsAPI.deleteReport,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reports'] })
      notifications.show({
        title: '成功',
        message: '报告已删除',
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '错误',
        message: `删除失败: ${error.message}`,
        color: 'red',
      })
    },
  })

  // Download mutation
  const downloadMutation = useMutation({
    mutationFn: async (reportId: string) => {
      const blob = await ReportsAPI.downloadReport(reportId)
      const report = reportsData?.reports.find((r) => r.id === reportId)
      const filename = `report_${reportId}.${report?.format || 'pdf'}`

      // Create download link
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    },
    onSuccess: () => {
      notifications.show({
        title: '成功',
        message: '报告已下载',
        color: 'green',
      })
    },
    onError: (error: Error) => {
      notifications.show({
        title: '错误',
        message: `下载失败: ${error.message}`,
        color: 'red',
      })
    },
  })

  // Filter by search query and format
  const filteredReports = reportsData?.reports.filter((report) => {
    const matchesSearch = report.title
      .toLowerCase()
      .includes(searchQuery.toLowerCase())
    const matchesFormat = !formatFilter || report.format === formatFilter
    return matchesSearch && matchesFormat
  })

  const getStatusBadge = (status: ReportStatus) => {
    const configs: Record<
      ReportStatus,
      { color: string; label: string }
    > = {
      pending: { color: 'gray', label: '待生成' },
      generating: { color: 'blue', label: '生成中' },
      completed: { color: 'green', label: '已完成' },
      failed: { color: 'red', label: '失败' },
    }
    const config = configs[status]
    return <Badge color={config.color}>{config.label}</Badge>
  }

  const getFormatIcon = (format: ReportFormat) => {
    const icons: Record<ReportFormat, JSX.Element> = {
      pdf: <IconFileTypePdf size={18} />,
      html: <IconFileTypeHtml size={18} />,
      excel: <IconTable size={18} />,
    }
    return icons[format]
  }

  const handleDownload = (reportId: string) => {
    if (onDownload) {
      onDownload(reportId)
    } else {
      downloadMutation.mutate(reportId)
    }
  }

  const handleDelete = (reportId: string) => {
    if (onDelete) {
      onDelete(reportId)
    } else {
      if (confirm('确定要删除此报告吗？')) {
        deleteMutation.mutate(reportId)
      }
    }
  }

  return (
    <Stack gap="md">
      {/* Filters */}
      <Card withBorder>
        <Group gap="md">
          <TextInput
            placeholder="搜索报告标题..."
            leftSection={<IconSearch size={16} />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.currentTarget.value)}
            style={{ flex: 1 }}
          />

          <Select
            placeholder="状态筛选"
            value={statusFilter}
            onChange={(value) => setStatusFilter(value as ReportStatus | '')}
            data={[
              { value: '', label: '全部状态' },
              { value: 'pending', label: '待生成' },
              { value: 'generating', label: '生成中' },
              { value: 'completed', label: '已完成' },
              { value: 'failed', label: '失败' },
            ]}
            style={{ width: 150 }}
            clearable
          />

          <Select
            placeholder="格式筛选"
            value={formatFilter}
            onChange={(value) => setFormatFilter(value as ReportFormat | '')}
            data={[
              { value: '', label: '全部格式' },
              { value: 'pdf', label: 'PDF' },
              { value: 'html', label: 'HTML' },
              { value: 'excel', label: 'Excel' },
            ]}
            style={{ width: 150 }}
            clearable
          />

          <Button
            leftSection={<IconRefresh size={16} />}
            variant="light"
            onClick={() => refetch()}
          >
            刷新
          </Button>
        </Group>
      </Card>

      {/* Report List */}
      <Card withBorder>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>报告标题</Table.Th>
              <Table.Th>类型</Table.Th>
              <Table.Th>格式</Table.Th>
              <Table.Th>状态</Table.Th>
              <Table.Th>文件大小</Table.Th>
              <Table.Th>生成者</Table.Th>
              <Table.Th>生成时间</Table.Th>
              <Table.Th>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {isLoading ? (
              <Table.Tr>
                <Table.Td colSpan={8} style={{ textAlign: 'center' }}>
                  <Text c="dimmed">加载中...</Text>
                </Table.Td>
              </Table.Tr>
            ) : filteredReports && filteredReports.length > 0 ? (
              filteredReports.map((report) => (
                <Table.Tr key={report.id}>
                  <Table.Td>
                    <Text fw={500}>{report.title}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{report.report_type}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      {getFormatIcon(report.format)}
                      <Text size="sm" tt="uppercase">
                        {report.format}
                      </Text>
                    </Group>
                  </Table.Td>
                  <Table.Td>{getStatusBadge(report.status)}</Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {report.file_size_bytes
                        ? `${(report.file_size_bytes / 1024).toFixed(1)} KB`
                        : '-'}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{report.generated_by}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {new Date(report.generated_at).toLocaleString('zh-CN')}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      {onView && (
                        <Tooltip label="查看详情">
                          <ActionIcon
                            variant="subtle"
                            color="blue"
                            onClick={() => onView(report.id)}
                          >
                            <IconEye size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}

                      {report.status === 'completed' && (
                        <Tooltip label="下载报告">
                          <ActionIcon
                            variant="subtle"
                            color="green"
                            onClick={() => handleDownload(report.id)}
                            loading={downloadMutation.isPending}
                          >
                            <IconDownload size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}

                      <Tooltip label="删除">
                        <ActionIcon
                          variant="subtle"
                          color="red"
                          onClick={() => handleDelete(report.id)}
                          loading={deleteMutation.isPending}
                        >
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))
            ) : (
              <Table.Tr>
                <Table.Td colSpan={8} style={{ textAlign: 'center' }}>
                  <Text c="dimmed">暂无报告</Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>

        {/* Summary */}
        {reportsData && (
          <Group justify="apart" mt="md">
            <Text size="sm" c="dimmed">
              共 {reportsData.total} 个报告
            </Text>
          </Group>
        )}
      </Card>
    </Stack>
  )
}
