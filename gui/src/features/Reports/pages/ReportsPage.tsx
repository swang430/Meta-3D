/**
 * Reports Management Page
 *
 * Main page for report generation, template management, and system log viewing
 */

import { useState } from 'react'
import { Container, Title, Tabs, Button, Modal, Stack } from '@mantine/core'
import {
  IconFileReport,
  IconTemplate,
  IconPlus,
  IconClockHour4,
  IconTerminal2,
} from '@tabler/icons-react'
import { ReportList, TemplateList, CreateReportWizard, PendingExecutionsList, SystemLogViewer } from '../components'

export function ReportsPage() {
  const [createReportOpened, setCreateReportOpened] = useState(false)

  return (
    <Container size="xl" py="xl">
      <Stack gap="lg">
        <Title order={1}>数据归档与报告</Title>

        <Tabs defaultValue="pending">
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
            <SystemLogViewer />
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
