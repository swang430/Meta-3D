/**
 * Reports Management Page
 *
 * Main page for report generation, template management, and system log viewing
 */

import { useState, useEffect } from 'react'
import { Container, Title, Tabs, Button, Modal, Stack } from '@mantine/core'
import {
  IconFileReport,
  IconTemplate,
  IconPlus,
  IconClockHour4,
  IconTerminal2,
} from '@tabler/icons-react'
import { ReportList, TemplateList, CreateReportWizard, PendingExecutionsList, SystemLogViewer } from '../components'

interface ReportsPageProps {
  /**
   * P1-39: 从执行历史「查看日志」跳进来时携带的**完整 `execution_id`**。
   * 有值时自动切到「系统日志」页签并预填过滤，**消费后立即经
   * `onPendingLogConsumed` 交还**（内审 F1：留着会永久劫持本页页签）。
   */
  pendingLogExecutionId?: string | null
  /** 内审 F1: 消费完成回调 —— 由 App 清空 state，保证这是一次性交接。 */
  onPendingLogConsumed?: () => void
}

export function ReportsPage({
  pendingLogExecutionId,
  onPendingLogConsumed,
}: ReportsPageProps = {}) {
  const [createReportOpened, setCreateReportOpened] = useState(false)
  // P1-39: 页签受控 —— 从执行历史「查看日志」跳进来时要落在「系统日志」上。
  // ⚠ 浏览器实测发现的缺口: 只把 execution_id 传给 SystemLogViewer 是**不够**的,
  //   Tabs 仍停在默认的 'pending'，用户落在「报告列表」还得自己点一下,
  //   「一键」就不成立了。
  const [activeTab, setActiveTab] = useState<string | null>('pending')
  // 内审 F1: 切页签 + 把值往下交, 然后**立刻交还** —— 本 state 只活一次事件。
  // ⚠ 先把值存进本地 state 再交还, 否则清空会连带把 SystemLogViewer 的
  //   initialExecutionFilter 抹成 null（那样过滤根本来不及应用）。
  const [logExecutionFilter, setLogExecutionFilter] = useState<string | null>(null)
  useEffect(() => {
    if (!pendingLogExecutionId) return
    setActiveTab('systemLogs')
    setLogExecutionFilter(pendingLogExecutionId)
    onPendingLogConsumed?.()
  }, [pendingLogExecutionId, onPendingLogConsumed])

  return (
    <Container size="xl" py="xl">
      <Stack gap="lg">
        <Title order={1}>数据归档与报告</Title>

        <Tabs value={activeTab} onChange={setActiveTab}>
          <Tabs.List>
            <Tabs.Tab value="pending" leftSection={<IconClockHour4 size={16} />}>
              待归档执行
            </Tabs.Tab>
            <Tabs.Tab value="reports" leftSection={<IconFileReport size={16} />}>
              我的报告
            </Tabs.Tab>
            <Tabs.Tab value="templates" leftSection={<IconTemplate size={16} />}>
              报告模板
            </Tabs.Tab>
            <Tabs.Tab value="systemLogs" leftSection={<IconTerminal2 size={16} />}>
              系统日志
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="pending" pt="lg">
            <PendingExecutionsList />
          </Tabs.Panel>

          <Tabs.Panel value="reports" pt="lg">
            <Stack gap="md">
              <Button
                leftSection={<IconPlus size={16} />}
                onClick={() => setCreateReportOpened(true)}
              >
                创建新报告
              </Button>

              <ReportList />
            </Stack>
          </Tabs.Panel>

          <Tabs.Panel value="templates" pt="lg">
            <TemplateList />
          </Tabs.Panel>

          <Tabs.Panel value="systemLogs" pt="lg">
            <SystemLogViewer initialExecutionFilter={logExecutionFilter} />
          </Tabs.Panel>
        </Tabs>

        {/* Create Report Wizard Modal */}
        <Modal
          opened={createReportOpened}
          onClose={() => setCreateReportOpened(false)}
          title="创建新报告"
          size="xl"
          centered
        >
          <CreateReportWizard
            onSuccess={() => setCreateReportOpened(false)}
            onCancel={() => setCreateReportOpened(false)}
          />
        </Modal>
      </Stack>
    </Container>
  )
}
