/**
 * Create Report Form Component
 *
 * Form for creating and generating new reports
 */

import { useState } from 'react'
import {
  Card,
  Stack,
  TextInput,
  Textarea,
  Select,
  Switch,
  Button,
  Group,
  Text,
  Divider,
  Alert,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { IconAlertCircle, IconFileTypePdf, IconCheck } from '@tabler/icons-react'
import { ReportsAPI } from '../index'
import type { CreateReportRequest, ReportType, ReportFormat } from '../types'

interface CreateReportFormProps {
  onSuccess?: (reportId: string) => void
  onCancel?: () => void
  testPlanId?: string
  testExecutionIds?: string[]
}

export function CreateReportForm({
  onSuccess,
  onCancel,
  testPlanId,
  testExecutionIds,
}: CreateReportFormProps) {
  const queryClient = useQueryClient()
  const [autoGenerate, setAutoGenerate] = useState(true)

  const form = useForm<CreateReportRequest>({
    initialValues: {
      title: '',
      report_type: 'single_execution',
      format: 'pdf',
      generated_by: 'user', // TODO: Get from auth context
      description: '',
      test_plan_id: testPlanId,
      test_execution_ids: testExecutionIds || [],
      template_id: undefined,
      include_raw_data: false,
      include_charts: true,
      include_statistics: true,
      include_recommendations: true,
      tags: [],
      category: '',
      notes: '',
    },

    validate: {
      title: (value) => (!value ? '请输入报告标题' : null),
      report_type: (value) => (!value ? '请选择报告类型' : null),
      format: (value) => (!value ? '请选择报告格式' : null),
    },
  })

  // Create report mutation
  const createMutation = useMutation({
    mutationFn: ReportsAPI.createReport,
    onSuccess: async (data) => {
      notifications.show({
        title: '成功',
        message: '报告已创建',
        color: 'green',
        icon: <IconCheck />,
      })

      // If auto-generate is enabled, trigger generation
      if (autoGenerate) {
        await ReportsAPI.generateReport(data.id)
        notifications.show({
          title: '报告生成中',
          message: '报告正在后台生成，请稍候查看结果',
          color: 'blue',
        })
      }

      queryClient.invalidateQueries({ queryKey: ['reports'] })

      if (onSuccess) {
        onSuccess(data.id)
      }
    },
    onError: (error: Error) => {
      notifications.show({
        title: '错误',
        message: `创建失败: ${error.message}`,
        color: 'red',
      })
    },
  })

  const handleSubmit = (values: CreateReportRequest) => {
    createMutation.mutate(values)
  }

  return (
    <form onSubmit={form.onSubmit(handleSubmit)}>
      <Stack gap="lg">
        <Card withBorder>
          <Stack gap="md">
            <Text fw={500} size="lg">
              基本信息
            </Text>

            <TextInput
              label="报告标题"
              placeholder="输入报告标题"
              required
              {...form.getInputProps('title')}
            />

            <Textarea
              label="报告描述"
              placeholder="输入报告描述（可选）"
              minRows={3}
              {...form.getInputProps('description')}
            />

            <Group grow>
              <Select
                label="报告类型"
                placeholder="选择报告类型"
                required
                data={[
                  { value: 'single_execution', label: '单次执行报告' },
                  { value: 'multi_execution', label: '多次执行报告' },
                  { value: 'comparison', label: '对比分析报告' },
                  { value: 'summary', label: '汇总报告' },
                  { value: 'regulatory', label: '监管合规报告' },
                ]}
                {...form.getInputProps('report_type')}
              />

              <Select
                label="报告格式"
                placeholder="选择报告格式"
                required
                data={[
                  { value: 'pdf', label: 'PDF' },
                  { value: 'html', label: 'HTML' },
                  { value: 'excel', label: 'Excel' },
                ]}
                {...form.getInputProps('format')}
              />
            </Group>

            <Group grow>
              <TextInput
                label="分类"
                placeholder="报告分类（可选）"
                {...form.getInputProps('category')}
              />

              <TextInput
                label="标签"
                placeholder="用逗号分隔多个标签"
                {...form.getInputProps('tags')}
                onChange={(e) => {
                  const tags = e.currentTarget.value
                    .split(',')
                    .map((t) => t.trim())
                    .filter((t) => t)
                  form.setFieldValue('tags', tags)
                }}
              />
            </Group>
          </Stack>
        </Card>

        <Card withBorder>
          <Stack gap="md">
            <Text fw={500} size="lg">
              报告内容选项
            </Text>

            <Switch
              label="包含图表"
              description="在报告中包含测试结果图表"
              {...form.getInputProps('include_charts', { type: 'checkbox' })}
            />

            <Switch
              label="包含统计分析"
              description="在报告中包含统计分析数据"
              {...form.getInputProps('include_statistics', { type: 'checkbox' })}
            />

            <Switch
              label="包含建议"
              description="在报告中包含改进建议"
              {...form.getInputProps('include_recommendations', {
                type: 'checkbox',
              })}
            />

            <Switch
              label="包含原始数据"
              description="在报告中包含原始测试数据（会增加文件大小）"
              {...form.getInputProps('include_raw_data', { type: 'checkbox' })}
            />
          </Stack>
        </Card>

        {form.values.test_plan_id && (
          <Alert
            icon={<IconAlertCircle size={16} />}
            title="关联的测试计划"
            color="blue"
          >
            <Text size="sm">
              此报告将基于测试计划 ID: {form.values.test_plan_id}
            </Text>
          </Alert>
        )}

        <Divider />

        <Card withBorder>
          <Stack gap="md">
            <Switch
              label="创建后立即生成报告"
              description="勾选后将自动开始生成 PDF/HTML/Excel 文件"
              checked={autoGenerate}
              onChange={(e) => setAutoGenerate(e.currentTarget.checked)}
            />
          </Stack>
        </Card>

        <Group justify="flex-end" gap="md">
          {onCancel && (
            <Button variant="subtle" onClick={onCancel}>
              取消
            </Button>
          )}

          <Button
            type="submit"
            loading={createMutation.isPending}
            leftSection={<IconFileTypePdf size={16} />}
          >
            {autoGenerate ? '创建并生成报告' : '创建报告'}
          </Button>
        </Group>
      </Stack>
    </form>
  )
}
