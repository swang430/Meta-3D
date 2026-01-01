/**
 * Scenario Card Component
 *
 * Display scenario summary in card format with edit/delete actions
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, Text, Badge, Group, Button, Stack, Tooltip, ActionIcon, Menu } from '@mantine/core'
import { modals } from '@mantine/modals'
import {
  IconMapPin,
  IconClock,
  IconRuler,
  IconPlayerPlay,
  IconInfoCircle,
  IconTransform,
  IconSettings,
  IconDotsVertical,
  IconEdit,
  IconTrash,
} from '@tabler/icons-react'
import { notifications } from '@mantine/notifications'
import type { ScenarioSummary } from '../../types/roadTest'
import { TestExecutionModal } from './TestExecutionModal'
import { ScenarioDetailModal } from './ScenarioDetailModal'
import { EditScenarioDialog } from './EditScenarioDialog'
import { generateTestPlanFromScenario, canConvertToTestPlan } from '../../utils/scenarioToTestPlan'
import { createTestPlan } from '../../api/service'
import { deleteScenario } from '../../api/roadTestService'

interface Props {
  scenario: ScenarioSummary
  testMode?: import('../../types/roadTest').TestMode
  onRefresh?: () => void
}

const CATEGORY_COLORS: Record<string, string> = {
  standard: 'blue',
  functional: 'green',
  performance: 'orange',
  environment: 'teal',
  extreme: 'red',
  custom: 'violet',
}

const CATEGORY_LABELS: Record<string, string> = {
  standard: '标准认证',
  functional: '功能测试',
  performance: '性能测试',
  environment: '环境测试',
  extreme: '极端场景',
  custom: '自定义',
}

// 统计配置了多少个步骤 (共8步)
const countConfiguredSteps = (scenario: ScenarioSummary): number => {
  if (!scenario.step_configuration) return 0
  const config = scenario.step_configuration
  let count = 0
  if (config.chamber_init) count++
  if (config.network_config) count++
  if (config.base_station_setup) count++
  if (config.ota_mapper) count++
  if (config.route_execution) count++
  if (config.kpi_validation) count++
  if (config.report_generation) count++
  if (config.environment_setup) count++  // Step 8: 环境配置
  return count
}

export default function ScenarioCard({ scenario, testMode, onRefresh }: Props) {
  const queryClient = useQueryClient()
  const configuredStepsCount = countConfiguredSteps(scenario)
  const [executionModalOpened, setExecutionModalOpened] = useState(false)
  const [detailModalOpened, setDetailModalOpened] = useState(false)
  const [editModalOpened, setEditModalOpened] = useState(false)
  const [converting, setConverting] = useState(false)

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: () => deleteScenario(scenario.id),
    onSuccess: () => {
      notifications.show({
        title: '删除成功',
        message: `场景 "${scenario.name}" 已删除`,
        color: 'green',
      })
      queryClient.invalidateQueries({ queryKey: ['scenarios'] })
      if (onRefresh) {
        onRefresh()
      }
    },
    onError: (error: any) => {
      notifications.show({
        title: '删除失败',
        message: error?.response?.data?.detail || error?.message || '删除场景失败',
        color: 'red',
      })
    },
  })

  const handleRun = () => {
    setExecutionModalOpened(true)
  }

  const handleViewDetails = () => {
    setDetailModalOpened(true)
  }

  const handleEdit = () => {
    setEditModalOpened(true)
  }

  const handleDelete = () => {
    modals.openConfirmModal({
      title: '确认删除',
      centered: true,
      children: (
        <Text size="sm">
          确定要删除场景 <strong>"{scenario.name}"</strong> 吗？此操作不可撤销。
        </Text>
      ),
      labels: { confirm: '删除', cancel: '取消' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteMutation.mutate(),
    })
  }

  const handleConvertToTestPlan = async () => {
    // 验证场景是否可转换
    const validation = canConvertToTestPlan(scenario)
    if (!validation.canConvert) {
      notifications.show({
        title: '无法转换',
        message: validation.reason || '该场景无法转换为测试计划',
        color: 'red',
      })
      return
    }

    setConverting(true)
    try {
      // 从场景生成测试计划
      const testPlanPayload = generateTestPlanFromScenario(scenario)

      // 调用API创建测试计划
      const response = await createTestPlan(testPlanPayload)

      // 后端直接返回plan对象
      const planName = (response as any).plan?.name || (response as any).name || '测试计划'

      notifications.show({
        title: '创建成功',
        message: `测试计划 "${planName}" 已创建`,
        color: 'green',
      })

      // 刷新父组件
      if (onRefresh) {
        onRefresh()
      }
    } catch (error: any) {
      console.error('转换场景失败:', error)
      notifications.show({
        title: '转换失败',
        message: error?.response?.data?.detail || '创建测试计划失败',
        color: 'red',
      })
    } finally {
      setConverting(false)
    }
  }

  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder>
      {/* Header */}
      <Group justify="space-between" mb="xs">
        <Group gap="xs">
          <Badge color={CATEGORY_COLORS[scenario.category]} variant="light" size="sm">
            {CATEGORY_LABELS[scenario.category]}
          </Badge>
          {configuredStepsCount > 0 && (
            <Tooltip label={`已配置 ${configuredStepsCount}/8 个测试步骤`}>
              <Badge color="cyan" variant="dot" size="sm" leftSection={<IconSettings size={12} />}>
                自定义步骤
              </Badge>
            </Tooltip>
          )}
        </Group>
        <Group gap="xs">
          <Badge color="gray" variant="outline" size="xs">
            {scenario.source}
          </Badge>
          {/* Actions Menu */}
          <Menu shadow="md" width={140} position="bottom-end">
            <Menu.Target>
              <ActionIcon variant="subtle" color="gray" size="sm">
                <IconDotsVertical size={16} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item
                leftSection={<IconEdit size={14} />}
                onClick={handleEdit}
              >
                编辑
              </Menu.Item>
              <Menu.Divider />
              <Menu.Item
                color="red"
                leftSection={<IconTrash size={14} />}
                onClick={handleDelete}
              >
                删除
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </Group>

      {/* Title */}
      <Text fw={600} size="lg" mb="xs">
        {scenario.name}
      </Text>

      {/* Description */}
      <Text size="sm" c="dimmed" lineClamp={2} mb="md">
        {scenario.description || '暂无描述'}
      </Text>

      {/* Tags */}
      {scenario.tags.length > 0 && (
        <Group gap="xs" mb="md">
          {scenario.tags.slice(0, 3).map((tag) => (
            <Badge key={tag} size="xs" variant="dot" color="gray">
              {tag}
            </Badge>
          ))}
          {scenario.tags.length > 3 && (
            <Badge size="xs" variant="dot" color="gray">
              +{scenario.tags.length - 3} more
            </Badge>
          )}
        </Group>
      )}

      {/* Stats */}
      <Stack gap="xs" mb="md">
        <Group gap="xs">
          <IconClock size={14} />
          <Text size="xs" c="dimmed">
            时长: {Math.round(scenario.duration_s)}秒 (~{Math.round(scenario.duration_s / 60)}分钟)
          </Text>
        </Group>

        <Group gap="xs">
          <IconRuler size={14} />
          <Text size="xs" c="dimmed">
            距离: {Math.round(scenario.distance_m)}米 (~{(scenario.distance_m / 1000).toFixed(1)}公里)
          </Text>
        </Group>

        {scenario.created_at && (
          <Group gap="xs">
            <IconMapPin size={14} />
            <Text size="xs" c="dimmed">
              创建: {new Date(scenario.created_at).toLocaleDateString('zh-CN')}
            </Text>
          </Group>
        )}
      </Stack>

      {/* Actions */}
      <Stack gap="xs">
        <Group gap="xs">
          <Button
            flex={1}
            variant="light"
            leftSection={<IconPlayerPlay size={16} />}
            onClick={handleRun}
          >
            执行测试
          </Button>
          <Button
            variant="subtle"
            size="sm"
            onClick={handleViewDetails}
            leftSection={<IconInfoCircle size={14} />}
          >
            详情
          </Button>
        </Group>

        <Button
          fullWidth
          variant="outline"
          color="blue"
          size="sm"
          leftSection={<IconTransform size={14} />}
          onClick={handleConvertToTestPlan}
          loading={converting}
        >
          转为测试计划
        </Button>
      </Stack>

      {/* Test Execution Modal */}
      <TestExecutionModal
        opened={executionModalOpened}
        onClose={() => setExecutionModalOpened(false)}
        scenario={scenario}
      />

      {/* Scenario Detail Modal */}
      <ScenarioDetailModal
        opened={detailModalOpened}
        onClose={() => setDetailModalOpened(false)}
        scenario={scenario}
      />

      {/* Edit Scenario Dialog */}
      <EditScenarioDialog
        opened={editModalOpened}
        onClose={() => {
          setEditModalOpened(false)
          if (onRefresh) {
            onRefresh()
          }
        }}
        scenario={scenario}
        testMode={testMode}
      />
    </Card>
  )
}
