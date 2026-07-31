/**
 * Unified Test Management Main Component
 *
 * ARCH-1 S4a: 计划链拆除。测试管理的基础单元是 TestCase, 不再有 TestPlan ——
 * 「计划管理」「步骤编排」「执行队列」三个 Tab 连同它们背后的组件树一并删除。
 *
 * 剩下三个 Tab, 覆盖完整闭环:
 * - CaseLibrary: 建用例 / 改用例 / 配仪表参数 / 直接执行 (执行入口 = ARCH-1 S1)
 * - History:     执行历史 (数据源 = test_executions 本表, ARCH-1 S2)
 * - VirtualRoadTest: VRT (TestCase 的复杂领域衍生)
 *
 * 「新建用例」入口 (S4a 申报的能力缺口, 本片补齐 — 设计稿
 * docs/design/gui-create-test-case-entry.md): 两步流 = TestCaseCreateModal
 * 建壳 → 本组件自渲染的 TestCaseEditModal 填参数。编辑弹窗另有一个实例挂在
 * TestCaseLibrary 内部(卡片"编辑"入口), 两实例同时最多开一个, 闭态零开销;
 * 列表刷新走 key={libraryEpoch} 重挂载 (activeRun 有挂载时恢复路径 S2 #237-C3,
 * 重挂载安全; epoch 递增可重复触发, 不是一次性 latch)。
 *
 * MIMO_OTA 的仪表参数配置原先只能从「步骤编排」进去(要先选一个计划),
 * 现在挂在用例编辑弹窗里 (TestCaseEditModal → MIMOOTAConfigForm)。
 *
 * @version 4.1.0
 * @date 2026-07-31
 */

import { useState } from 'react'
import { Container, Tabs, Title, Stack, Text } from '@mantine/core'
import { IconChecklist, IconChartBar, IconRoute } from '@tabler/icons-react'
import { TestCaseLibrary } from '../../components/TestPlanManagement/TestCaseLibrary'
import { TestCaseCreateModal } from '../../components/TestPlanManagement/TestCaseCreateModal'
import { TestCaseEditModal } from '../../components/TestPlanManagement/TestCaseEditModal'
import { HistoryTab } from './components/HistoryTab'
import { VirtualRoadTest } from '../../components/VirtualRoadTest'

export function TestManagement() {
  const [activeTab, setActiveTab] = useState<string | null>('caseLibrary')
  // 「新建用例」两步流状态: 创建弹窗开关 / 建完待编辑的新用例 id / 库刷新纪元
  const [creating, setCreating] = useState(false)
  const [newCaseId, setNewCaseId] = useState<string | null>(null)
  const [libraryEpoch, setLibraryEpoch] = useState(0)

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

          {/* Test Case Library Tab — Foundation, 含新建/配置/执行入口 */}
          <Tabs.Panel value="caseLibrary" pt="md">
            <TestCaseLibrary
              key={libraryEpoch}
              enableExecute={true}
              onCreateNew={() => setCreating(true)}
            />
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

        {/* 「新建用例」两步流: 建壳 → 直接进编辑填参数 */}
        <TestCaseCreateModal
          opened={creating}
          onClose={() => setCreating(false)}
          onCreated={(id) => {
            setCreating(false)
            setLibraryEpoch((e) => e + 1) // 新行落库, 重挂载库列表让它可见
            setNewCaseId(id)
          }}
        />
        <TestCaseEditModal
          opened={newCaseId !== null}
          testCaseId={newCaseId}
          onClose={() => setNewCaseId(null)}
          onSaved={() => {
            setNewCaseId(null)
            setLibraryEpoch((e) => e + 1) // 参数保存后再刷一次
          }}
        />
      </Stack>
    </Container>
  )
}

export default TestManagement
