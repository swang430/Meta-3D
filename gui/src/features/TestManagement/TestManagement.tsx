/**
 * Unified Test Management Main Component
 *
 * ARCH-1 S4a: 计划链拆除。测试管理的基础单元是 TestCase, 不再有 TestPlan ——
 * 「计划管理」「步骤编排」「执行队列」三个 Tab 连同它们背后的组件树一并删除。
 *
 * 剩下三个 Tab, 覆盖完整闭环:
 * - CaseLibrary: 改用例 / 配仪表参数 / 直接执行 (执行入口 = ARCH-1 S1)
 *
 * ⚠️ **能力缺口 (S4a 显式申报)**: GUI 目前**没有建新用例的入口**。
 * 原先唯一的入口是 StepsTab 的 SaveAsTestCaseModal (要先有计划和步骤),
 * 随计划链一并删除。TestCaseLibrary 的「新建用例」按钮由 onCreateNew 守着,
 * 本片没有传 —— 因为真接上它需要新写一个建用例对话框, 那是**加机制**,
 * 不该混在纯删除片里。现状: 用例来自 bootstrap 种子, 可改可执行, 不可新建。
 * 建用例对话框单独立项 (roadmap backlog)。
 * - History:     执行历史 (数据源 = test_executions 本表, ARCH-1 S2)
 * - VirtualRoadTest: VRT (TestCase 的复杂领域衍生)
 *
 * MIMO_OTA 的仪表参数配置原先只能从「步骤编排」进去(要先选一个计划),
 * 现在挂在用例编辑弹窗里 (TestCaseEditModal → MIMOOTAConfigForm)。
 *
 * @version 4.0.0
 * @date 2026-07-28
 */

import { useState } from 'react'
import { Container, Tabs, Title, Stack, Text } from '@mantine/core'
import { IconChecklist, IconChartBar, IconRoute } from '@tabler/icons-react'
import { TestCaseLibrary } from '../../components/TestPlanManagement/TestCaseLibrary'
import { HistoryTab } from './components/HistoryTab'
import { VirtualRoadTest } from '../../components/VirtualRoadTest'

export function TestManagement() {
  const [activeTab, setActiveTab] = useState<string | null>('caseLibrary')

  return (
    <Container size="xl" py="md">
      <Stack gap="md">
        {/* Header */}
        <div>
          <Title order={2}>测试管理</Title>
          <Text size="sm" c="dimmed">
            以测试用例为基础的统一测试管理与编排系统
          </Text>
        </div>

        {/* Main Tabs */}
        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab value="caseLibrary" leftSection={<IconChecklist size={16} />}>
              测试用例库
            </Tabs.Tab>
            <Tabs.Tab value="history" leftSection={<IconChartBar size={16} />}>
              执行历史
            </Tabs.Tab>
            <Tabs.Tab value="virtualRoadTest" leftSection={<IconRoute size={16} />}>
              虚拟路测
            </Tabs.Tab>
          </Tabs.List>

          {/* Test Case Library Tab — Foundation, 含配置与执行入口 */}
          <Tabs.Panel value="caseLibrary" pt="md">
            <TestCaseLibrary enableExecute={true} />
          </Tabs.Panel>

          {/* History Tab */}
          <Tabs.Panel value="history" pt="md">
            <HistoryTab />
          </Tabs.Panel>

          {/* Virtual Road Test Tab — VRT consolidated as TestCase derivative */}
          <Tabs.Panel value="virtualRoadTest" pt="md">
            <VirtualRoadTest />
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </Container>
  )
}

export default TestManagement
