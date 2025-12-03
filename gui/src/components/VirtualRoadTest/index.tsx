/**
 * VirtualRoadTest - 虚拟路测主组件
 * 统一管理三种测试模式的入口
 */

import { useState } from 'react'
import { Stack, Alert, Text, Tabs, Button, Group } from '@mantine/core'
import { IconInfoCircle, IconFlask, IconRefresh, IconMapPin } from '@tabler/icons-react'
import { ModeSelector } from './ModeSelector'
import ScenarioLibrary from './ScenarioLibrary'
import { OTAMapper } from '../OTAMapper'
import { TestMode } from '../../types/roadTest'

export function VirtualRoadTest() {
  const [selectedMode, setSelectedMode] = useState<TestMode | null>(null)
  const [activeTab, setActiveTab] = useState<string>('main')

  const handleModeSelected = (mode: TestMode) => {
    setSelectedMode(mode)
    setActiveTab('test')  // 自动切换到场景库测试标签
    console.log('选择的测试模式:', mode)
  }

  const handleReset = () => {
    setSelectedMode(null)
    setActiveTab('main')
  }

  return (
    <Stack gap="xl">
      <Alert variant="light" color="blue" icon={<IconInfoCircle />}>
        <Group justify="space-between">
          <div>
            <Text size="sm" fw={600}>
              虚拟路测平台 (Phase 2 - 场景库开发)
            </Text>
            <Text size="sm" mt={4}>
              支持三种测试模式：全数字仿真（数字孪生）、传导测试（仪表-DUT直连）、OTA辐射测试（MPAC暗室）
            </Text>
          </div>
          {selectedMode && (
            <Button
              variant="light"
              size="xs"
              leftSection={<IconRefresh size={14} />}
              onClick={handleReset}
            >
              重置
            </Button>
          )}
        </Group>
      </Alert>

      <Tabs value={activeTab} onChange={(value) => setActiveTab(value || 'main')}>
        <Tabs.List>
          <Tabs.Tab value="main">模式选择</Tabs.Tab>
          <Tabs.Tab value="test" leftSection={<IconFlask size={14} />}>
            场景库测试
          </Tabs.Tab>
          <Tabs.Tab value="ota-mapper" leftSection={<IconMapPin size={14} />}>
            OTA映射器
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="main" pt="lg">
          {!selectedMode ? (
            <ModeSelector onModeSelected={handleModeSelected} />
          ) : (
            <Stack>
              <Alert variant="light" color="green">
                <Text size="sm" fw={600}>
                  已选择模式：
                  {selectedMode === TestMode.DIGITAL_TWIN && '全数字仿真（数字孪生）'}
                  {selectedMode === TestMode.CONDUCTED && '传导测试（仪表-DUT直连）'}
                  {selectedMode === TestMode.OTA && 'OTA辐射测试（MPAC暗室）'}
                </Text>
                <Text size="sm" mt={4} c="dimmed">
                  请点击"场景库测试"标签查看和管理测试场景，选择场景后可创建和执行测试。
                </Text>
              </Alert>
            </Stack>
          )}
        </Tabs.Panel>

        <Tabs.Panel value="test" pt="lg">
          <ScenarioLibrary />
        </Tabs.Panel>

        <Tabs.Panel value="ota-mapper" pt="lg">
          <OTAMapper />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}
