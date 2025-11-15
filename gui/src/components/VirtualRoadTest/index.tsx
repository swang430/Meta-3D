/**
 * VirtualRoadTest - 虚拟路测主组件
 * 统一管理三种测试模式的入口
 */

import { useState } from 'react'
import { Stack, Alert, Text } from '@mantine/core'
import { IconInfoCircle } from '@tabler/icons-react'
import { ModeSelector } from './ModeSelector'
import { TestMode } from '../../types/roadTest'

export function VirtualRoadTest() {
  const [selectedMode, setSelectedMode] = useState<TestMode | null>(null)

  const handleModeSelected = (mode: TestMode) => {
    setSelectedMode(mode)
    console.log('选择的测试模式:', mode)
  }

  return (
    <Stack gap="xl">
      <Alert variant="light" color="blue" icon={<IconInfoCircle />}>
        <Text size="sm" fw={600}>
          虚拟路测平台 (Phase 1 - 基础架构)
        </Text>
        <Text size="sm" mt={4}>
          支持三种测试模式：全数字仿真（数字孪生）、传导测试（仪表-DUT直连）、OTA辐射测试（MPAC暗室）
        </Text>
      </Alert>

      {!selectedMode ? (
        <ModeSelector onModeSelected={handleModeSelected} />
      ) : (
        <Stack>
          <Alert variant="light" color="green">
            <Text size="sm">
              已选择模式：
              {selectedMode === TestMode.DIGITAL_TWIN && '全数字仿真'}
              {selectedMode === TestMode.CONDUCTED && '传导测试'}
              {selectedMode === TestMode.OTA && 'OTA辐射测试'}
            </Text>
            <Text size="sm" mt={4} c="dimmed">
              场景库和执行流程正在开发中，敬请期待...
            </Text>
          </Alert>
        </Stack>
      )}
    </Stack>
  )
}
