/**
 * Execution Selector Component
 *
 * Allows users to select test executions for report generation.
 * Shows execution details including pass/fail status and duration.
 */

import { useState } from 'react'
import {
  Stack,
  Paper,
  Text,
  Group,
  Badge,
  Checkbox,
  Loader,
  Center,
  Alert,
  ScrollArea,
  Button,
} from '@mantine/core'
import {
  IconAlertCircle,
  IconCheck,
  IconX,
  IconClock,
  IconSelectAll,
} from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import client from '../../../api/client'

export interface ExecutionOption {
  id: string
  execution_order: number
  status: string
  validation_pass: boolean | null
  started_at?: string
  completed_at?: string
  duration_sec?: number
  measurement_count?: number
}

interface ExecutionSelectorProps {
  testPlanId?: string
  value: string[]
  onChange: (executionIds: string[]) => void
  disabled?: boolean
}

// Fetch executions for a test plan
async function fetchExecutions(planId: string): Promise<ExecutionOption[]> {
  const response = await client.get(`/test-plans/${planId}/executions`)
  const executions = response.data.items || response.data || []

  return executions.map((exec: any) => ({
    id: exec.id,
    execution_order: exec.execution_order || 1,
    status: exec.status,
    validation_pass: exec.validation_pass,
    started_at: exec.started_at,
    completed_at: exec.completed_at,
    duration_sec: exec.duration_sec,
    measurement_count: exec.measurements
      ? Object.keys(exec.measurements).length
      : 0,
  }))
}

export function ExecutionSelector({
  testPlanId,
  value,
  onChange,
  disabled = false,
}: ExecutionSelectorProps) {
  const {
    data: executions,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['plan-executions', testPlanId],
    queryFn: () => fetchExecutions(testPlanId!),
    enabled: !!testPlanId,
  })

  const handleToggle = (executionId: string) => {
    if (disabled) return

    if (value.includes(executionId)) {
      onChange(value.filter((id) => id !== executionId))
    } else {
      onChange([...value, executionId])
    }
  }

  const handleSelectAll = () => {
    if (!executions || disabled) return

    if (value.length === executions.length) {
      onChange([])
    } else {
      onChange(executions.map((e) => e.id))
    }
  }

  const formatDuration = (seconds?: number): string => {
    if (!seconds) return '-'
    if (seconds < 60) return `${seconds}秒`
    if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
    return `${(seconds / 3600).toFixed(1)}小时`
  }

  const getStatusIcon = (pass: boolean | null) => {
    if (pass === true) return <IconCheck size={14} color="green" />
    if (pass === false) return <IconX size={14} color="red" />
    return null
  }

  const getStatusBadge = (status: string, pass: boolean | null) => {
    if (status === 'completed') {
      return pass ? (
        <Badge size="xs" color="green" variant="light">
          通过
        </Badge>
      ) : (
        <Badge size="xs" color="red" variant="light">
          失败
        </Badge>
      )
    }
    if (status === 'running') {
      return (
        <Badge size="xs" color="blue" variant="light">
          执行中
        </Badge>
      )
    }
    if (status === 'pending') {
      return (
        <Badge size="xs" color="gray" variant="light">
          待执行
        </Badge>
      )
    }
    return (
      <Badge size="xs" color="gray" variant="light">
        {status}
      </Badge>
    )
  }

  if (!testPlanId) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} color="blue">
        请先选择测试计划
      </Alert>
    )
  }

  if (isLoading) {
    return (
      <Center p="xl">
        <Loader size="sm" />
        <Text ml="sm" size="sm" c="dimmed">
          加载执行记录...
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
        无法加载执行记录，请稍后重试
      </Alert>
    )
  }

  if (!executions || executions.length === 0) {
    return (
      <Alert
        icon={<IconAlertCircle size={16} />}
        title="暂无执行记录"
        color="yellow"
      >
        该测试计划没有执行记录。请先执行测试计划后再生成报告。
      </Alert>
    )
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          共 {executions.length} 条执行记录，已选择 {value.length} 条
        </Text>
        <Button
          variant="subtle"
          size="xs"
          leftSection={<IconSelectAll size={14} />}
          onClick={handleSelectAll}
          disabled={disabled}
        >
          {value.length === executions.length ? '取消全选' : '全选'}
        </Button>
      </Group>

      <ScrollArea h={300} type="auto">
        <Stack gap="xs">
          {executions.map((exec) => (
            <Paper
              key={exec.id}
              p="sm"
              withBorder
              style={{
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.6 : 1,
                backgroundColor: value.includes(exec.id)
                  ? 'var(--mantine-color-blue-light)'
                  : undefined,
              }}
              onClick={() => handleToggle(exec.id)}
            >
              <Group justify="space-between" wrap="nowrap">
                <Group gap="sm" wrap="nowrap">
                  <Checkbox
                    checked={value.includes(exec.id)}
                    onChange={() => handleToggle(exec.id)}
                    disabled={disabled}
                    styles={{
                      input: { cursor: disabled ? 'not-allowed' : 'pointer' },
                    }}
                  />
                  <Stack gap={2}>
                    <Group gap="xs">
                      <Text size="sm" fw={500}>
                        执行 #{exec.execution_order}
                      </Text>
                      {getStatusBadge(exec.status, exec.validation_pass)}
                    </Group>
                    <Group gap="xs">
                      {exec.started_at && (
                        <Text size="xs" c="dimmed">
                          {new Date(exec.started_at).toLocaleString('zh-CN')}
                        </Text>
                      )}
                    </Group>
                  </Stack>
                </Group>

                <Group gap="md">
                  <Stack gap={0} align="flex-end">
                    <Group gap={4}>
                      <IconClock size={12} />
                      <Text size="xs">{formatDuration(exec.duration_sec)}</Text>
                    </Group>
                    {exec.measurement_count !== undefined && (
                      <Text size="xs" c="dimmed">
                        {exec.measurement_count} 个测量值
                      </Text>
                    )}
                  </Stack>
                </Group>
              </Group>
            </Paper>
          ))}
        </Stack>
      </ScrollArea>

      {value.length > 0 && (
        <Paper p="xs" withBorder bg="blue.0">
          <Text size="sm">
            已选择 {value.length} 条执行记录用于报告生成
          </Text>
        </Paper>
      )}
    </Stack>
  )
}

export default ExecutionSelector
