/**
 * Test Plan Management Main Component
 *
 * Container component for test plan management functionality
 */
import { useState } from 'react';
import { Container, Tabs } from '@mantine/core';
import { IconList, IconClock, IconChartBar } from '@tabler/icons-react';
import { TestPlanList } from './TestPlanList';
import { CreateTestPlanWizard } from './CreateTestPlanWizard';
import { TestQueue } from './TestQueue';

export function TestPlanManagement() {
  const [createWizardOpened, setCreateWizardOpened] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleCreateNew = () => {
    setCreateWizardOpened(true);
  };

  const handleEdit = (_id: string) => {
    // TODO: Implement edit functionality
  };

  const handleCreated = () => {
    setRefreshTrigger((prev) => prev + 1);
  };

  return (
    <Container size="xl" py="md">
      <Tabs defaultValue="plans">
        <Tabs.List>
          <Tabs.Tab value="plans" leftSection={<IconList size={16} />}>
            测试计划
          </Tabs.Tab>
          <Tabs.Tab value="queue" leftSection={<IconClock size={16} />}>
            执行队列
          </Tabs.Tab>
          <Tabs.Tab value="history" leftSection={<IconChartBar size={16} />}>
            执行历史
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="plans" pt="md">
          <TestPlanList
            key={refreshTrigger}
            onCreateNew={handleCreateNew}
            onEdit={handleEdit}
          />
        </Tabs.Panel>

        <Tabs.Panel value="queue" pt="md">
          <TestQueue />
        </Tabs.Panel>

        <Tabs.Panel value="history" pt="md">
          {/* TODO: Implement execution history */}
          <div>执行历史功能即将推出...</div>
        </Tabs.Panel>
      </Tabs>

      <CreateTestPlanWizard
        opened={createWizardOpened}
        onClose={() => setCreateWizardOpened(false)}
        onCreated={handleCreated}
      />
    </Container>
  );
}
