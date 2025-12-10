/**
 * Create Report Wizard Component
 *
 * A step-by-step wizard for creating reports with data source selection.
 * Steps:
 * 1. Basic Info - Report title, type, format
 * 2. Data Source - Select test plan and executions
 * 3. Options - Configure charts, statistics, etc.
 * 4. Preview & Generate - Review and create
 */

import { useState } from 'react'
import {
  Stack,
  Stepper,
  Group,
  Button,
  TextInput,
  Textarea,
  Select,
  Switch,
  Paper,
  Text,
  Alert,
  Divider,
  Badge,
  Card,
  SimpleGrid,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import {
  IconFileTypePdf,
  IconCheck,
  IconAlertCircle,
  IconArrowRight,
  IconArrowLeft,
  IconFileAnalytics,
  IconChartBar,
  IconTable,
  IconBulb,
} from '@tabler/icons-react'
import { ReportsAPI } from '../index'
import { TestPlanSelector } from './TestPlanSelector'
import { ExecutionSelector } from './ExecutionSelector'
import type { CreateReportRequest, ReportType, ReportFormat } from '../types'

interface CreateReportWizardProps {
  onSuccess?: (reportId: string) => void
  onCancel?: () => void
}

interface WizardFormData extends CreateReportRequest {
  auto_generate: boolean
}

export function CreateReportWizard({
  onSuccess,
  onCancel,
}: CreateReportWizardProps) {
  const [active, setActive] = useState(0)
  const queryClient = useQueryClient()

  const form = useForm<WizardFormData>({
    initialValues: {
      title: '',
      report_type: 'single_execution',
      format: 'pdf',
      generated_by: 'user',
      description: '',
      test_plan_id: undefined,
      test_execution_ids: [],
      comparison_plan_ids: [],
      template_id: undefined,
      include_raw_data: false,
      include_charts: true,
      include_statistics: true,
      include_recommendations: true,
      tags: [],
      category: '',
      notes: '',
      auto_generate: true,
    },

    validate: {
      title: (value) => (!value ? '请输入报告标题' : null),
      report_type: (value) => (!value ? '请选择报告类型' : null),
      format: (value) => (!value ? '请选择报告格式' : null),
      test_plan_id: (value, values) => {
        if (active >= 1 && !value && values.report_type !== 'comparison') {
          return '请选择测试计划'
        }
        return null
      },
    },
  })

  // Create report mutation
  const createMutation = useMutation({
    mutationFn: async (values: WizardFormData) => {
      const { auto_generate, ...reportData } = values
      const report = await ReportsAPI.createReport(reportData)

      if (auto_generate) {
        await ReportsAPI.generateReport(report.id)
      }

      return report
    },
    onSuccess: (data) => {
      notifications.show({
        title: '成功',
        message: form.values.auto_generate
          ? '报告已创建，正在后台生成...'
          : '报告已创建',
        color: 'green',
        icon: <IconCheck />,
      })

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

  const nextStep = () => {
    // Validate current step
    if (active === 0) {
      const titleError = form.validateField('title')
      const typeError = form.validateField('report_type')
      const formatError = form.validateField('format')
      if (titleError.hasError || typeError.hasError || formatError.hasError) {
        return
      }
    }

    if (active === 1) {
      if (!form.values.test_plan_id && form.values.report_type !== 'comparison') {
        notifications.show({
          title: '请选择数据源',
          message: '请选择一个测试计划作为报告数据来源',
          color: 'yellow',
        })
        return
      }
    }

    setActive((current) => Math.min(current + 1, 3))
  }

  const prevStep = () => setActive((current) => Math.max(current - 1, 0))

  const handleSubmit = () => {
    createMutation.mutate(form.values)
  }

  const getReportTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      single_execution: '单次执行报告',
      multi_execution: '多次执行报告',
      comparison: '对比分析报告',
      summary: '汇总报告',
      regulatory: '监管合规报告',
    }
    return labels[type] || type
  }

  const getFormatLabel = (format: string) => {
    const labels: Record<string, string> = {
      pdf: 'PDF',
      html: 'HTML',
      excel: 'Excel',
    }
    return labels[format] || format
  }

  return (
    <Stack gap="lg">
      <Stepper
        active={active}
        onStepClick={setActive}
        allowNextStepsSelect={false}
      >
        {/* Step 1: Basic Info */}
        <Stepper.Step
          label="基本信息"
          description="报告标题和类型"
          icon={<IconFileAnalytics size={18} />}
        >
          <Paper p="md" withBorder mt="md">
            <Stack gap="md">
              <TextInput
                label="报告标题"
                placeholder="输入报告标题"
                required
                {...form.getInputProps('title')}
              />

              <Textarea
                label="报告描述"
                placeholder="输入报告描述（可选）"
                minRows={2}
                {...form.getInputProps('description')}
              />

              <SimpleGrid cols={2}>
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
                  label="输出格式"
                  placeholder="选择输出格式"
                  required
                  data={[
                    { value: 'pdf', label: 'PDF 文档' },
                    { value: 'html', label: 'HTML 网页' },
                    { value: 'excel', label: 'Excel 表格' },
                  ]}
                  {...form.getInputProps('format')}
                />
              </SimpleGrid>

              <SimpleGrid cols={2}>
                <TextInput
                  label="分类"
                  placeholder="报告分类（可选）"
                  {...form.getInputProps('category')}
                />

                <TextInput
                  label="标签"
                  placeholder="用逗号分隔多个标签"
                  onChange={(e) => {
                    const tags = e.currentTarget.value
                      .split(',')
                      .map((t) => t.trim())
                      .filter((t) => t)
                    form.setFieldValue('tags', tags)
                  }}
                />
              </SimpleGrid>
            </Stack>
          </Paper>
        </Stepper.Step>

        {/* Step 2: Data Source */}
        <Stepper.Step
          label="选择数据"
          description="测试计划和执行记录"
          icon={<IconTable size={18} />}
        >
          <Paper p="md" withBorder mt="md">
            <Stack gap="lg">
              <div>
                <Text fw={500} mb="xs">
                  选择测试计划
                </Text>
                <Text size="sm" c="dimmed" mb="md">
                  选择一个已完成的测试计划作为报告数据来源
                </Text>
                <TestPlanSelector
                  value={form.values.test_plan_id}
                  onChange={(id) => {
                    form.setFieldValue('test_plan_id', id)
                    form.setFieldValue('test_execution_ids', [])
                  }}
                />
              </div>

              <Divider />

              <div>
                <Text fw={500} mb="xs">
                  选择执行记录（可选）
                </Text>
                <Text size="sm" c="dimmed" mb="md">
                  选择要包含在报告中的执行记录。不选择则使用所有记录。
                </Text>
                <ExecutionSelector
                  testPlanId={form.values.test_plan_id}
                  value={form.values.test_execution_ids || []}
                  onChange={(ids) =>
                    form.setFieldValue('test_execution_ids', ids)
                  }
                />
              </div>
            </Stack>
          </Paper>
        </Stepper.Step>

        {/* Step 3: Options */}
        <Stepper.Step
          label="配置选项"
          description="图表和内容"
          icon={<IconChartBar size={18} />}
        >
          <Paper p="md" withBorder mt="md">
            <Stack gap="md">
              <Text fw={500}>报告内容选项</Text>

              <Switch
                label="包含图表"
                description="在报告中包含时间序列图、统计对比图等可视化图表"
                {...form.getInputProps('include_charts', { type: 'checkbox' })}
              />

              <Switch
                label="包含统计分析"
                description="在报告中包含均值、标准差、百分位数等统计数据"
                {...form.getInputProps('include_statistics', {
                  type: 'checkbox',
                })}
              />

              <Switch
                label="包含建议"
                description="在报告中包含基于测试结果的改进建议"
                {...form.getInputProps('include_recommendations', {
                  type: 'checkbox',
                })}
              />

              <Switch
                label="包含原始数据"
                description="在报告中包含原始测试数据（会增加文件大小）"
                {...form.getInputProps('include_raw_data', {
                  type: 'checkbox',
                })}
              />

              <Divider my="sm" />

              <Switch
                label="创建后立即生成报告"
                description="勾选后将自动开始生成 PDF/HTML/Excel 文件"
                {...form.getInputProps('auto_generate', { type: 'checkbox' })}
              />
            </Stack>
          </Paper>
        </Stepper.Step>

        {/* Step 4: Preview & Generate */}
        <Stepper.Step
          label="预览确认"
          description="检查并生成"
          icon={<IconBulb size={18} />}
        >
          <Paper p="md" withBorder mt="md">
            <Stack gap="md">
              <Text fw={500} size="lg">
                报告摘要
              </Text>

              <Card withBorder>
                <Stack gap="xs">
                  <Group justify="space-between">
                    <Text c="dimmed" size="sm">
                      报告标题
                    </Text>
                    <Text fw={500}>{form.values.title || '未设置'}</Text>
                  </Group>

                  <Group justify="space-between">
                    <Text c="dimmed" size="sm">
                      报告类型
                    </Text>
                    <Badge variant="light">
                      {getReportTypeLabel(form.values.report_type)}
                    </Badge>
                  </Group>

                  <Group justify="space-between">
                    <Text c="dimmed" size="sm">
                      输出格式
                    </Text>
                    <Badge variant="outline">
                      {getFormatLabel(form.values.format)}
                    </Badge>
                  </Group>

                  <Divider my="xs" />

                  <Group justify="space-between">
                    <Text c="dimmed" size="sm">
                      数据来源
                    </Text>
                    <Text size="sm">
                      {form.values.test_plan_id
                        ? '已选择测试计划'
                        : '未选择'}
                    </Text>
                  </Group>

                  <Group justify="space-between">
                    <Text c="dimmed" size="sm">
                      执行记录
                    </Text>
                    <Text size="sm">
                      {form.values.test_execution_ids?.length || 0} 条已选择
                    </Text>
                  </Group>

                  <Divider my="xs" />

                  <Group gap="xs" wrap="wrap">
                    {form.values.include_charts && (
                      <Badge size="sm" variant="dot" color="blue">
                        图表
                      </Badge>
                    )}
                    {form.values.include_statistics && (
                      <Badge size="sm" variant="dot" color="green">
                        统计分析
                      </Badge>
                    )}
                    {form.values.include_recommendations && (
                      <Badge size="sm" variant="dot" color="orange">
                        建议
                      </Badge>
                    )}
                    {form.values.include_raw_data && (
                      <Badge size="sm" variant="dot" color="gray">
                        原始数据
                      </Badge>
                    )}
                  </Group>
                </Stack>
              </Card>

              {!form.values.test_plan_id && (
                <Alert
                  icon={<IconAlertCircle size={16} />}
                  title="未选择数据源"
                  color="yellow"
                >
                  您没有选择测试计划，报告将不包含测试数据。
                </Alert>
              )}

              {form.values.auto_generate && (
                <Alert
                  icon={<IconFileTypePdf size={16} />}
                  title="自动生成"
                  color="blue"
                >
                  报告创建后将自动在后台生成{' '}
                  {getFormatLabel(form.values.format)} 文件。
                </Alert>
              )}
            </Stack>
          </Paper>
        </Stepper.Step>

        <Stepper.Completed>
          <Alert
            icon={<IconCheck size={16} />}
            title="完成"
            color="green"
            mt="md"
          >
            报告已成功创建！
          </Alert>
        </Stepper.Completed>
      </Stepper>

      {/* Navigation Buttons */}
      <Group justify="space-between" mt="xl">
        <Group>
          {onCancel && (
            <Button variant="subtle" onClick={onCancel}>
              取消
            </Button>
          )}
        </Group>

        <Group>
          {active > 0 && (
            <Button
              variant="default"
              onClick={prevStep}
              leftSection={<IconArrowLeft size={16} />}
            >
              上一步
            </Button>
          )}

          {active < 3 ? (
            <Button
              onClick={nextStep}
              rightSection={<IconArrowRight size={16} />}
            >
              下一步
            </Button>
          ) : (
            <Button
              onClick={handleSubmit}
              loading={createMutation.isPending}
              leftSection={<IconFileTypePdf size={16} />}
              color="green"
            >
              {form.values.auto_generate ? '创建并生成报告' : '创建报告'}
            </Button>
          )}
        </Group>
      </Group>
    </Stack>
  )
}

export default CreateReportWizard
