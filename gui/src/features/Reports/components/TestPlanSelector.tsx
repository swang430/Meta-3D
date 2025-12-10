/**
 * Test Plan Selector Component
 *
 * Allows users to select a test plan for report generation.
 * Shows test plan details including execution count and status.
 */

import { useState, useEffect } from 'react'
import {
  Stack,
  Paper,
  Text,
  TextInput,
  Group,
  Badge,
  Radio,
  Loader,
  Center,
  Alert,
  ScrollArea,
} from '@mantine/core'
import { IconSearch, IconAlertCircle, IconFileAnalytics } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import client from '../../../api/client'

export interface TestPlanOption {
  id: string
  name: string
  status: string
  description?: string
  execution_count: number
  last_execution?: string
  dut_model?: string
  created_by: string
  created_at: string
}

interface TestPlanSelectorProps {
  value?: string
  onChange: (planId: string | undefined) => void
  disabled?: boolean
}

// Fetch available test plans for reports
async function fetchAvailablePlans(): Promise<TestPlanOption[]> {
  // Use the test plans endpoint with completed status filter
  const response = await client.get('/test-plans', {
    params: {
      status: 'completed',
      limit: 100,
    },
  })

  // Transform the response to include execution info
  const plans = response.data.items || response.data || []

  return plans.map((plan: any) => ({
    id: plan.id,
    name: plan.name,
    status: plan.status,
    description: plan.description,
    execution_count: plan.completed_test_cases || 0,
    last_execution: plan.completed_at,
    dut_model: plan.dut_info?.model,
    created_by: plan.created_by,
    created_at: plan.created_at,
  }))
}

export function TestPlanSelector({
  value,
  onChange,
  disabled = false,
}: TestPlanSelectorProps) {
  const [searchQuery, setSearchQuery] = useState('')

  const {
    data: plans,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['available-plans-for-report'],
    queryFn: fetchAvailablePlans,
  })

  // Filter plans based on search
  const filteredPlans = plans?.filter(
    (plan) =>
      plan.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      plan.dut_model?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      plan.created_by.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'green'
      case 'failed':
        return 'red'
      case 'running':
        return 'blue'
      default:
        return 'gray'
    }
  }

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'completed':
        return '已完成'
      case 'failed':
        return '失败'
      case 'running':
        return '执行中'
      case 'draft':
        return '草稿'
      case 'ready':
        return '就绪'
      default:
        return status
    }
  }

  if (isLoading) {
    return (
      <Center p="xl">
        <Loader size="sm" />
        <Text ml="sm" size="sm" c="dimmed">
          加载测试计划列表...
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
        无法加载测试计划列表，请稍后重试
      </Alert>
    )
  }

  if (!plans || plans.length === 0) {
    return (
      <Alert
        icon={<IconFileAnalytics size={16} />}
        title="暂无可用数据"
        color="yellow"
      >
        没有已完成的测试计划。请先执行测试计划后再生成报告。
      </Alert>
    )
  }

  return (
    <Stack gap="md">
      <TextInput
        placeholder="搜索测试计划..."
        leftSection={<IconSearch size={16} />}
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        disabled={disabled}
      />

      <ScrollArea h={350} type="auto">
        <Radio.Group value={value} onChange={onChange}>
          <Stack gap="xs">
            {filteredPlans?.map((plan) => (
              <Paper
                key={plan.id}
                p="sm"
                withBorder
                style={{
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  opacity: disabled ? 0.6 : 1,
                  backgroundColor:
                    value === plan.id
                      ? 'var(--mantine-color-blue-light)'
                      : undefined,
                }}
                onClick={() => !disabled && onChange(plan.id)}
              >
                <Group justify="space-between" wrap="nowrap">
                  <Group gap="sm" wrap="nowrap" style={{ flex: 1 }}>
                    <Radio
                      value={plan.id}
                      disabled={disabled}
                      styles={{ radio: { cursor: disabled ? 'not-allowed' : 'pointer' } }}
                    />
                    <Stack gap={2} style={{ flex: 1 }}>
                      <Group gap="xs">
                        <Text size="sm" fw={500} lineClamp={1}>
                          {plan.name}
                        </Text>
                        <Badge
                          size="xs"
                          color={getStatusColor(plan.status)}
                          variant="light"
                        >
                          {getStatusLabel(plan.status)}
                        </Badge>
                      </Group>
                      <Group gap="xs">
                        {plan.dut_model && (
                          <Text size="xs" c="dimmed">
                            设备: {plan.dut_model}
                          </Text>
                        )}
                        <Text size="xs" c="dimmed">
                          创建者: {plan.created_by}
                        </Text>
                      </Group>
                    </Stack>
                  </Group>
                  <Stack gap={2} align="flex-end">
                    <Badge size="xs" variant="outline" color="blue">
                      {plan.execution_count} 次执行
                    </Badge>
                    {plan.last_execution && (
                      <Text size="xs" c="dimmed">
                        {new Date(plan.last_execution).toLocaleDateString('zh-CN')}
                      </Text>
                    )}
                  </Stack>
                </Group>
              </Paper>
            ))}
          </Stack>
        </Radio.Group>
      </ScrollArea>

      {value && (
        <Paper p="xs" withBorder bg="blue.0">
          <Group gap="xs">
            <IconFileAnalytics size={16} />
            <Text size="sm">
              已选择: {plans?.find((p) => p.id === value)?.name}
            </Text>
          </Group>
        </Paper>
      )}
    </Stack>
  )
}

export default TestPlanSelector
