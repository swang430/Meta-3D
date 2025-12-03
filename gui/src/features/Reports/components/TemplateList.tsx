/**
 * Report Template List Component
 *
 * Displays a list of report templates with filtering and selection
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
} from '@mantine/core'
import {
  IconEye,
  IconEdit,
  IconTrash,
  IconCopy,
  IconStar,
  IconSearch,
} from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { ReportsAPI } from '../index'
import type { ReportTemplateSummary, TemplateType } from '../types'

interface TemplateListProps {
  onSelect?: (template: ReportTemplateSummary) => void
  onView?: (templateId: string) => void
  onEdit?: (templateId: string) => void
  onDelete?: (templateId: string) => void
  onClone?: (templateId: string) => void
  selectable?: boolean
}

export function TemplateList({
  onSelect,
  onView,
  onEdit,
  onDelete,
  onClone,
  selectable = false,
}: TemplateListProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [templateType, setTemplateType] = useState<TemplateType | ''>('')
  const [activeFilter, setActiveFilter] = useState<'all' | 'active' | 'inactive'>('active')

  // Fetch templates
  const { data: templatesData, isLoading } = useQuery({
    queryKey: ['templates', templateType, activeFilter, searchQuery],
    queryFn: () =>
      ReportsAPI.listTemplates({
        template_type: templateType || undefined,
        is_active: activeFilter === 'all' ? undefined : activeFilter === 'active',
      }),
  })

  // Filter by search query locally
  const filteredTemplates = templatesData?.templates.filter((template) =>
    template.name.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  const handleSelectTemplate = (template: ReportTemplateSummary) => {
    if (selectable && onSelect) {
      onSelect(template)
    }
  }

  const getTemplateTypeBadge = (type: TemplateType) => {
    const colors: Record<TemplateType, string> = {
      standard: 'blue',
      regulatory: 'orange',
      custom: 'green',
    }
    return <Badge color={colors[type]}>{type}</Badge>
  }

  return (
    <Stack gap="md">
      {/* Filters */}
      <Card withBorder>
        <Group gap="md">
          <TextInput
            placeholder="搜索模板名称..."
            leftSection={<IconSearch size={16} />}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.currentTarget.value)}
            style={{ flex: 1 }}
          />

          <Select
            placeholder="模板类型"
            value={templateType}
            onChange={(value) => setTemplateType(value as TemplateType | '')}
            data={[
              { value: '', label: '全部类型' },
              { value: 'standard', label: '标准模板' },
              { value: 'regulatory', label: '监管模板' },
              { value: 'custom', label: '自定义模板' },
            ]}
            style={{ width: 180 }}
            clearable
          />

          <Select
            placeholder="状态筛选"
            value={activeFilter}
            onChange={(value) =>
              setActiveFilter(value as 'all' | 'active' | 'inactive')
            }
            data={[
              { value: 'all', label: '全部' },
              { value: 'active', label: '启用' },
              { value: 'inactive', label: '禁用' },
            ]}
            style={{ width: 150 }}
          />
        </Group>
      </Card>

      {/* Template List */}
      <Card withBorder>
        <Table highlightOnHover={selectable}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>模板名称</Table.Th>
              <Table.Th>类型</Table.Th>
              <Table.Th>状态</Table.Th>
              <Table.Th>使用次数</Table.Th>
              <Table.Th>创建者</Table.Th>
              <Table.Th>创建时间</Table.Th>
              <Table.Th>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {isLoading ? (
              <Table.Tr>
                <Table.Td colSpan={7} style={{ textAlign: 'center' }}>
                  <Text c="dimmed">加载中...</Text>
                </Table.Td>
              </Table.Tr>
            ) : filteredTemplates && filteredTemplates.length > 0 ? (
              filteredTemplates.map((template) => (
                <Table.Tr
                  key={template.id}
                  onClick={() => handleSelectTemplate(template)}
                  style={{ cursor: selectable ? 'pointer' : 'default' }}
                >
                  <Table.Td>
                    <Group gap="xs">
                      {template.is_default && (
                        <Tooltip label="默认模板">
                          <IconStar size={16} fill="gold" color="gold" />
                        </Tooltip>
                      )}
                      <Text fw={template.is_default ? 500 : 400}>
                        {template.name}
                      </Text>
                    </Group>
                  </Table.Td>
                  <Table.Td>{getTemplateTypeBadge(template.template_type)}</Table.Td>
                  <Table.Td>
                    <Badge color={template.is_active ? 'green' : 'gray'}>
                      {template.is_active ? '启用' : '禁用'}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{template.usage_count}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{template.created_by}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {new Date(template.created_at).toLocaleDateString('zh-CN')}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs">
                      {onView && (
                        <Tooltip label="查看详情">
                          <ActionIcon
                            variant="subtle"
                            color="blue"
                            onClick={(e) => {
                              e.stopPropagation()
                              onView(template.id)
                            }}
                          >
                            <IconEye size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}

                      {onEdit && (
                        <Tooltip label="编辑">
                          <ActionIcon
                            variant="subtle"
                            color="blue"
                            onClick={(e) => {
                              e.stopPropagation()
                              onEdit(template.id)
                            }}
                          >
                            <IconEdit size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}

                      {onClone && (
                        <Tooltip label="克隆">
                          <ActionIcon
                            variant="subtle"
                            color="green"
                            onClick={(e) => {
                              e.stopPropagation()
                              onClone(template.id)
                            }}
                          >
                            <IconCopy size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}

                      {onDelete && !template.is_default && (
                        <Tooltip label="删除">
                          <ActionIcon
                            variant="subtle"
                            color="red"
                            onClick={(e) => {
                              e.stopPropagation()
                              onDelete(template.id)
                            }}
                          >
                            <IconTrash size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))
            ) : (
              <Table.Tr>
                <Table.Td colSpan={7} style={{ textAlign: 'center' }}>
                  <Text c="dimmed">暂无模板</Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>

        {/* Summary */}
        {templatesData && (
          <Group justify="apart" mt="md">
            <Text size="sm" c="dimmed">
              共 {templatesData.total} 个模板
            </Text>
          </Group>
        )}
      </Card>
    </Stack>
  )
}
