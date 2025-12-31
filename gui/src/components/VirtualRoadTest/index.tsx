/**
 * VirtualRoadTest - 虚拟路测主组件
 * 简化的工作流：场景库 + 执行历史 + OTA映射器
 */

import { useState } from 'react'
import { Stack, Alert, Text, Tabs, SegmentedControl, Group, Badge, Paper } from '@mantine/core'
import {
  IconInfoCircle,
  IconBooks,
  IconHistory,
  IconMapPin,
  IconCpu,
  IconPlugConnected,
  IconRadar2,
} from '@tabler/icons-react'
import ScenarioLibrary from './ScenarioLibrary'
import { OTAMapper } from '../OTAMapper'
import { TestMode } from '../../types/roadTest'

// 测试模式配置
const TEST_MODES = [
  {
    value: TestMode.DIGITAL_TWIN,
    label: '数字孪生',
    icon: IconCpu,
    color: 'blue',
    description: '纯软件仿真，成本最低',
  },
  {
    value: TestMode.CONDUCTED,
    label: '传导测试',
    icon: IconPlugConnected,
    color: 'green',
    description: '仪表直连，精度较高',
  },
  {
    value: TestMode.OTA,
    label: 'OTA测试',
    icon: IconRadar2,
    color: 'orange',
    description: 'MPAC暗室，精度最高',
  },
]

export function VirtualRoadTest() {
  const [activeTab, setActiveTab] = useState<string>('library')
  const [selectedMode, setSelectedMode] = useState<TestMode>(TestMode.OTA)

  const currentMode = TEST_MODES.find((m) => m.value === selectedMode)

  return (
    <Stack gap="md">
      {/* 顶部信息栏 */}
      <Alert variant="light" color="blue" icon={<IconInfoCircle />}>
        <Text size="sm">
          <strong>虚拟路测平台</strong> - 在实验室环境中复现真实道路测试场景，支持三种测试模式：数字孪生、传导测试、OTA辐射测试
        </Text>
      </Alert>

      {/* 测试模式选择器 */}
      <Paper p="md" withBorder>
        <Group justify="space-between" align="center">
          <Group gap="md">
            <Text size="sm" fw={500} c="dimmed">
              测试模式：
            </Text>
            <SegmentedControl
              value={selectedMode}
              onChange={(value) => setSelectedMode(value as TestMode)}
              data={TEST_MODES.map((mode) => ({
                value: mode.value,
                label: (
                  <Group gap="xs">
                    <mode.icon size={16} />
                    <span>{mode.label}</span>
                  </Group>
                ),
              }))}
            />
          </Group>
          {currentMode && (
            <Badge color={currentMode.color} variant="light" size="lg">
              {currentMode.description}
            </Badge>
          )}
        </Group>
      </Paper>

      {/* 标签页 */}
      <Tabs value={activeTab} onChange={(value) => setActiveTab(value || 'library')}>
        <Tabs.List>
          <Tabs.Tab value="library" leftSection={<IconBooks size={16} />}>
            场景库
          </Tabs.Tab>
          <Tabs.Tab value="history" leftSection={<IconHistory size={16} />}>
            执行历史
          </Tabs.Tab>
          <Tabs.Tab value="ota-mapper" leftSection={<IconMapPin size={16} />}>
            OTA映射器
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="library" pt="md">
          <ScenarioLibrary testMode={selectedMode} />
        </Tabs.Panel>

        <Tabs.Panel value="history" pt="md">
          <ExecutionHistory />
        </Tabs.Panel>

        <Tabs.Panel value="ota-mapper" pt="md">
          <OTAMapper />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}

/**
 * 执行历史组件 - 显示虚拟路测的执行记录
 */
function ExecutionHistory() {
  // TODO: 复用 TestManagement 的 HistoryTab 或创建专用组件
  return (
    <Paper p="xl" withBorder>
      <Stack align="center" gap="md">
        <IconHistory size={48} stroke={1.5} color="gray" />
        <Text c="dimmed" ta="center">
          执行历史功能开发中
        </Text>
        <Text size="sm" c="dimmed" ta="center">
          此处将显示虚拟路测的执行记录，包括：
          <br />
          - 测试场景名称和模式
          <br />
          - 执行时间和持续时长
          <br />
          - 测试结果和KPI达成情况
        </Text>
      </Stack>
    </Paper>
  )
}
