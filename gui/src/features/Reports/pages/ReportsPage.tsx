/**
 * Reports Management Page
 *
 * Main page for report generation and template management
 */

import { useState } from 'react'
import { Container, Title, Tabs, Button, Modal, Stack } from '@mantine/core'
import {
  IconFileReport,
  IconTemplate,
  IconPlus,
} from '@tabler/icons-react'
import { ReportList, TemplateList, CreateReportWizard } from '../components'

export function ReportsPage() {
  const [createReportOpened, setCreateReportOpened] = useState(false)

  return (
    <Container size="xl" py="xl">
      <Stack gap="lg">
        <Title order={1}>报告管理</Title>

        <Tabs defaultValue="reports">
          <Tabs.List>
            <Tabs.Tab value="reports" leftSection={<IconFileReport size={16} />}>
              我的报告
            </Tabs.Tab>
            <Tabs.Tab value="templates" leftSection={<IconTemplate size={16} />}>
              报告模板
            </Tabs.Tab>
          </Tabs.List>

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
